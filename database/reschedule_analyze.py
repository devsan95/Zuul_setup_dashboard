import ast
import re
import sys
import traceback

import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from api import log_api
from model import LogAction
from model import get_reschedule_statistics_model

log = log_api.get_console_logger('RESCH_ANALYSIS')

re_merging = re.compile(r'Resetting builds for change <QueueItem .* for <Change .* \d*,\d*> in .*> because the item ahead, '
                        r'<QueueItem (?P<queueitem>.*) for <Change .* (?P<change>\d*),(?P<patchset>\d*)> in .*>, failed to merge')

re_failing = re.compile(r'Resetting builds for change <QueueItem .* for <Change .* \d*,\d*> in .*> because the item ahead, '
                        r'<QueueItem (?P<queueitem>.*) for <Change .* (?P<change>\d*),(?P<patchset>\d*)> in .*>, '
                        r'is not the nearest non-failing item, (<QueueItem .* for <Change .* \d*,\d*> in .*>|None)')

result_list = ['remove for replace', 'remove for abandon',
               'remove for dequeue command', 'remove for cannot merge',
               'finish with no job', 'finish with merge fail', 'success', 'fail', 'cancel jobs for promotion']

reg_cancel_job_new = re.compile(r'Reason for cancel jobs for change '
                                r'<QueueItem (?P<queue_item>.*?) for <Change (?P<item>.*?) (?P<change>\d*?),(?P<patchset>\d*?)> in (?P<pipeline>.*?)> '
                                r'is (?P<reason>.*)')

reg_reason_nnfi = re.compile(
    r'reschedule for <QueueItem (?P<queue_item>.*) for <Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in (?P<pipeline>.*)> is not nnfi, '
    r'failing reason is (?P<reason>.*)')

reg_reason_merge_error = re.compile(
    r'reschedule for item '
    r'<QueueItem (?P<queue_item>.*) for <Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in (?P<pipeline>.*)>'
    r' fail to merge, reason is (?P<reason>.*)')

reg_submit_error = re.compile(r'it did not merge, because Change '
                              r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)>'
                              r' failed to merge, because of submit error, (?P<reason>.*)')


class DbHandler(object):
    start_strings = ['added to queue', 'cancel job']
    end_strings = ['remove from queue', 'resetting for nnfi',
                   'resetting for not merge']
    break_strings = ['resetting for nnfi', 'resetting for not merge']

    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.RescheduleStatistics = None

    def init_db(self, table_name=None):
        if table_name:
            self.RescheduleStatistics = get_reschedule_statistics_model(table_name)
        else:
            self.RescheduleStatistics = get_reschedule_statistics_model()
        self.RescheduleStatistics.metadata.create_all(self.engine)

    def get_last_end_no(self):
        query = self.session.query(self.RescheduleStatistics.item_finish_id, self.RescheduleStatistics.end_time) \
            .order_by(sa.desc(self.RescheduleStatistics.item_finish_id))
        result = query.first()
        if not result:
            return -1, -1
        return result.item_finish_id, result.end_time

    def get_end_list(self, begin, limit):
        query = self.session.query(LogAction) \
            .filter(LogAction.type == 'remove from queue',
                    LogAction.id > begin,
                    sa.or_(LogAction.pipeline == 'gate', LogAction.pipeline == 'gate_branches'),
                    LogAction.queue_item.isnot(None)) \
            .order_by(LogAction.id) \
            .limit(limit) \
            .all()

        rd = []
        for row in query:
            ri = {'id': row.id, 'change_item': row.change_item, 'queue_item': row.queue_item}
            rd.append(ri)

        return rd

    def get_op_list_from_end(self, end_item):
        query = self.session.query(LogAction) \
            .filter(LogAction.change_item == end_item['change_item'],
                    LogAction.queue_item == end_item['queue_item']) \
            .order_by(LogAction.id)
        result = query.all()
        begin_index = 0
        end_index = len(result) - 1
        for idx, item in enumerate(result):
            if item.type == 'added to queue':
                if item.id < end_item['id']:
                    begin_index = idx
                else:
                    end_index = idx - 1
                    break
            elif item.type == 'remove from queue':
                if item.id < end_item['id']:
                    begin_index = idx + 1
                elif item.id > end_item['id']:
                    end_index = idx - 1
                    break
        oplist = []
        for item in result[begin_index:end_index - begin_index + 1]:
            dictrow = dict(item.__dict__)
            dictrow.pop('_sa_instance_state', None)
            oplist.append(dictrow)
        return oplist

    def find_string_index(self, list_, start_no, string_list):
        for i in range(start_no, len(list_)):
            item = list_[i]
            if item['type'] in string_list:
                return i
        return -1

    def process_op_list(self, list_, db):
        if not list_:
            log.debug('Empty list')
            return

        reschedule_lists = []
        begin = -1
        end = -1
        end_id = list_[-1]['id']
        new_type = False

        for index, item in enumerate(list_):
            if item['type'] == 'go in window':
                new_type = True
            if item['type'] == 'prepare ref':
                if begin == -1:
                    begin = index
            if not new_type:
                if item['type'].startswith('resetting'):
                    end = index
                    if begin >= 0:
                        reschedule_lists.append(list_[begin:(end + 1)])
                        begin = index + 1

            if new_type:
                if item['type'].startswith('cancel jobs for reschedule'):
                    end = index
                    if begin >= 0:
                        reschedule_lists.append(list_[begin:(end + 1)])
                        begin = index + 1

            # if item['type'] == 'remove from queue':
            #     end = index
            #     if begin >= 0:
            #         reschedule_lists.append(list_[begin:(end + 1)])
            #         begin = index + 1

        for list__ in reschedule_lists:
            if not new_type:
                self.process_reschedule_list(list__, end_id, db)
            else:
                self.process_reschedule_list_new(list__, end_id, db)

    def process_reschedule_list(self, list_, end_id, db):
        # print('---')
        c_change = None
        c_patchset = None
        c_queue_item = None
        c_status = None
        c_finish_id = None
        c_end_time = None
        status = None
        for index, item in enumerate(list_):
            re_match = None
            if item['type'] == 'resetting for nnfi':
                re_match = re_failing
            elif item['type'] == 'resetting for not merge':
                re_match = re_merging
            elif item['type'] in result_list:
                status = item['type']
            if re_match:
                status = item['type']
                m = re_match.match(item['text'])
                if not m:
                    log.error('Cannot match re_failing')
                    log.error(item['text'])
                else:
                    c_change = int(m.group('change'))
                    c_patchset = int(m.group('patchset'))
                    c_queue_item = m.group('queueitem')
                    c_status, c_finish_id, c_end_time = \
                        db.get_cause_info(c_queue_item,
                                          c_change,
                                          c_patchset,
                                          item['datetime'],
                                          item['id'])
                    # log.debug('%s %s %s', c_status, c_finish_id, c_end_time)
        r_status = ''
        if status == 'resetting for not merge':
            r_status = 'Merge Error'
        elif status == 'resetting for nnfi':
            if c_status == 'finish with merge fail':
                r_status = 'Merger Failure'
            elif c_status == 'success':
                r_status = 'Non-head Failure'
            elif c_status == 'Dequeued by promotion':
                r_status = 'Dequeued by Promotion'
            elif c_status == 'fail':
                r_status = 'Job Failure'
            elif c_status == 'remove for replace':
                r_status = 'Dequeued by New Patchset'
            elif c_status == 'remove for abandon':
                r_status = 'Dequeued by Abandon'
            elif c_status == 'finish with no job':
                r_status = 'No Jobs to Run'
        obj = self.RescheduleStatistics(change=list_[0]['change'],
                                        patchset=list_[0]['patchset'],
                                        queue_item=list_[0]['queue_item'],
                                        pipeline=list_[0]['pipeline'],
                                        project=None,
                                        branch=None,
                                        begin_id=list_[0]['id'],
                                        finish_id=list_[-1]['id'],
                                        item_finish_id=end_id,
                                        start_time=list_[0]['datetime'],
                                        end_time=list_[-1]['datetime'],
                                        duration=(list_[-1]['datetime'] - list_[0]['datetime']).total_seconds() * 1000,
                                        status=status,
                                        c_change=c_change,
                                        c_patchset=c_patchset,
                                        c_queue_item=c_queue_item,
                                        c_project=None,
                                        c_branch=None,
                                        c_status=c_status,
                                        c_job=None,
                                        c_end_time=c_end_time,
                                        c_finish_id=c_finish_id,
                                        reschedule_reason=r_status)
        self.session.add(obj)

    def get_cause_info(self, queue_item, change, patchset, time, iid):
        del time, iid
        # log.debug('%s %s %s %s %s', queue_item, change, patchset, time, iid)
        query = self.session.query(LogAction).filter(LogAction.queue_item == queue_item,
                                                     LogAction.change == change,
                                                     LogAction.patchset == patchset).order_by(sa.desc(LogAction.id))
        status = 'Dequeued by promotion'
        result = query.all()
        for item in result:
            # print item.type
            if item.type in result_list:
                status = item.type
                break

        return status, result[-1].id, result[-1].datetime

    def process_reschedule_list_new(self, list_, end_id, db):
        # print('---')
        c_change = None
        c_patchset = None
        c_queue_item = None
        c_status = None
        c_finish_id = None
        c_end_time = None
        status = None
        c_job = None

        for index, item in enumerate(list_):
            re_match = None
            if item['type'] == 'cancel jobs for reschedule of nnfi':
                re_match = reg_reason_nnfi
            elif item['type'] == 'cancel jobs for reschedule of merge error':
                re_match = reg_reason_merge_error
            elif item['type'] in result_list:
                status = item['type']
            if re_match:
                status = item['type']
                m = reg_cancel_job_new.match(item['text'])
                if not m:
                    log.error('Cannot match reg_cancel_job_new')
                    log.error(item['text'])
                else:
                    reason = m.group('reason')
                    m1 = re_match.match(reason)
                    if not m1:
                        log.error('Cannot match re_match')
                        log.error(reason)
                    else:
                        c_change = int(m1.group('change'))
                        c_patchset = int(m1.group('patchset'))
                        c_queue_item = m1.group('queue_item')
                        c_reason = m1.group('reason')
                        c_reason_list = ast.literal_eval(c_reason)
                        reason_action, reason_cause = self.analyze_reason_list(c_reason_list)
                        c_status, c_finish_id, c_end_time = db.get_cause_info(
                            c_queue_item, c_change, c_patchset,
                            item['datetime'], item['id'])
        r_status = ''
        if status == 'cancel jobs for reschedule of merge error':
            r_status = 'Merge Error'
        elif status == 'cancel jobs for reschedule of nnfi':
            if c_status == 'finish with merge fail':
                r_status = 'Merger Failure'
            elif c_status == 'success':
                r_status = 'Non-head Failure'
            elif c_status == 'Dequeued by promotion':
                r_status = 'Dequeued by Promotion'
            elif c_status == 'fail':
                r_status = 'Job Failure'
            elif c_status == 'remove for replace':
                r_status = 'Dequeued by New Patchset'
            elif c_status == 'remove for abandon':
                r_status = 'Dequeued by Abandon'
            elif c_status == 'finish with no job':
                r_status = 'No Jobs to Run'
        if reason_action == 'fail':
            r_status = 'Job Failure'
            c_job = reason_cause
        elif reason_action == 'merger error':
            r_status = 'Merger Failure'
        elif reason_action == 'submit error':
            r_status = 'Submit Error'
        if not status or not c_status or not reason_action or not r_status or not reason_cause:
            print '[{}], [{}], [{}] ,[{}] ,[{}]'.format(status, c_status, reason_action, r_status, reason_cause)
            print list_[-1]['text']
            print '{},{} -> {},{}'.format(c_change, c_patchset, list_[0]['change'], list_[0]['patchset'])
        obj = self.RescheduleStatistics(change=list_[0]['change'],
                                        patchset=list_[0]['patchset'],
                                        queue_item=list_[0]['queue_item'],
                                        pipeline=list_[0]['pipeline'],
                                        project=None,
                                        branch=None,
                                        begin_id=list_[0]['id'],
                                        finish_id=list_[-1]['id'],
                                        item_finish_id=end_id,
                                        start_time=list_[0]['datetime'],
                                        end_time=list_[-1]['datetime'],
                                        duration=(list_[-1]['datetime'] - list_[0]['datetime']).total_seconds() * 1000,
                                        status=status,
                                        c_change=c_change,
                                        c_patchset=c_patchset,
                                        c_queue_item=c_queue_item,
                                        c_project=None,
                                        c_branch=None,
                                        c_status=c_status,
                                        c_job=((c_job[:2500] + '..') if c_job and len(c_job) > 2500 else c_job),
                                        c_end_time=c_end_time,
                                        c_finish_id=c_finish_id,
                                        reschedule_reason=r_status)
        self.session.add(obj)

    def analyze_reason_list(self, list_):
        if not list_:
            return None, None
        for item in list_:
            if 'at least one job failed, failed jobs:' in item:
                job = item.split('at least one job failed, failed jobs: ')[1]
                if job:
                    return 'fail', job
        for item in list_:
            if 'it has a merge conflict' in item:
                return 'merger error', None
        for item in list_:
            m = reg_submit_error.match(item)
            if m:
                reason = m.group('reason')
                reason_list = ast.literal_eval(reason)
                if reason_list is None:
                    reason_list = []
                if reason_list is True:
                    reason_list = []
                return 'submit error', ';'.join(reason_list)
        print('None of the reason matches')
        return None, None

    def commit(self):
        self.session.commit()
        pass

    def rollback(self):
        self.session.rollback()


def main(db_str, db_str_dest='', table_name=None, entry_num=5000, run_num=1):
    last_end = -2
    db = DbHandler(db_str)
    if not db_str_dest:
        db2 = db
    else:
        db2 = DbHandler(db_str_dest)
    try:
        db2.init_db(table_name)

        for i in range(0, run_num):
            new_last_end, last_time = db2.get_last_end_no()
            if new_last_end == last_end:
                raise Exception('Last End not Changed, break')
            last_end = new_last_end
            log.debug('Searching at %s, %s', last_end, last_time)

            rd = db.get_end_list(last_end, entry_num)

            if not rd:
                log.debug('No more id to process, break')
                break

            for end_item in rd:
                op_list = db.get_op_list_from_end(end_item)
                db2.process_op_list(op_list, db)

            print('Commiting...')
            db2.commit()
            print('Committed.')
    except Exception as ex:
        log.debug('Exception occurs:')
        log.debug(ex)
        log.debug('rollback')
        db2.rollback()
        traceback.print_exc()
        raise ex


if __name__ == '__main__':
    try:
        fire.Fire(main)
    except Exception as e:
        log.debug('Exception: {}'.format(str(e)))
        if str(e) == 'Last End not Changed, break':
            sys.exit(0)
        traceback.print_exc()
        sys.exit(2)
