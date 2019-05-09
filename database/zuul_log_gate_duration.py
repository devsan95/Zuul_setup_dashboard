import sys
import traceback

import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from api import log_api
from model import LogAction
from model import get_gate_statistics_model

log = log_api.get_console_logger('ZUUL_LOG_DURATION')

start_strings = ['added to queue', 'cancel job']
end_strings = ['remove from queue', 'resetting for nnfi',
               'resetting for not merge']
break_strings = ['resetting for nnfi', 'resetting for not merge']
new_break_strings = ['cancel jobs for reschedule of merge error', 'cancel jobs for reschedule of nnfi']


class DbHandler(object):
    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.GateStatistics = None

    def init_db(self, table_name=None):
        if table_name:
            self.GateStatistics = get_gate_statistics_model(table_name)
        else:
            self.GateStatistics = get_gate_statistics_model('log_duration')
        # self.GateStatistics.metadata.create_all(self.engine)

    def get_last_end_no(self):
        query = self.session.query(self.GateStatistics.finish_id) \
            .order_by(sa.desc(self.GateStatistics.finish_id))
        result = query.first()
        if not result:
            return -1
        return result.finish_id

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

    def save_op_list(self, list_):
        if not list_:
            log.debug('Empty list')
            return
        # log.debug('---')
        # log.debug('[%s] [%s]', list_[0]['change_item'], list_[0]['queue_item'])
        # log.debug('')

        start_time = None
        merge_time = None
        merged_time = None
        launch_job_time = None
        launched_job_time = None
        complete_job_time = None
        finish_time = None
        status_str = None
        pipeline = list_[0]['pipeline']
        queue_item = list_[0]['queue_item']
        begin_id = list_[0]['id']
        end_id = None
        changeset = '{},{}'.format(list_[0]['change'], list_[0]['patchset'])
        waiting_for_window = True
        waiting_for_window_time = None
        this_start_time = None
        reschedule_times = 0

        use_old_reschdule = True

        for index, item in enumerate(list_):
            # log.debug('%s\t%s\t[%s]\t[%s]', item['id'], item['type'], item['datetime'], item['pipeline'])
            # start
            if not start_time:
                if index == 0:
                    start_time = item['datetime']
                    this_start_time = start_time
                    if item['type'] not in start_strings:
                        log.debug('error begin entry {}'.format(item))
            # merge
            if item['type'] == 'prepare ref':
                merge_time = item['datetime']
                launch_job_time = None
                launched_job_time = None
                complete_job_time = None
                if waiting_for_window:
                    waiting_for_window = False
                    waiting_for_window_time = merge_time
            # merged
            if item['type'] in ['merge failed', 'merge complete']:
                merged_time = item['datetime']
                launch_job_time = None
                launched_job_time = None
                complete_job_time = None
            # launch
            if item['type'] == 'launch job' and not launch_job_time:
                launch_job_time = item['datetime']
                launched_job_time = None
                complete_job_time = None
            # launched
            if item['type'] == 'job started' and not launched_job_time:
                launched_job_time = item['datetime']
                complete_job_time = None
            # complete
            if item['type'] in \
                    ['job started', 'job completed', 'job cancelled']:
                if item['type'] == 'job started':
                    complete_job_time = None
                else:
                    complete_job_time = item['datetime']
            # finish
            if item['type'] in end_strings:
                finish_time = item['datetime']
                if item['type'].startswith('resetting'):
                    status_str = item['type']

            if not finish_time:
                if index == len(list_) - 1:
                    finish_time = item['datetime']
                    log.debug('error end entry {}'.format(item))

            # resetting
            if use_old_reschdule:
                if item['type'] in ['resetting for nnfi', 'resetting for not merge']:
                    if not waiting_for_window:
                        reschedule_times += 1
            if item['type'] in new_break_strings:
                if use_old_reschdule:
                    use_old_reschdule = False
                    reschedule_times = 0
                if not waiting_for_window:
                    reschedule_times += 1

            if item['type'] in ['cancel job']:
                merge_time = None
                merged_time = None
                this_start_time = item['datetime']

            # removeItem
            if item['type'] == 'remove item' and not status_str:
                status_str = 'removed'
            # replace
            if item['type'] == 'remove for replace':
                status_str = 'replaced by new changeset'
            # abandon
            if item['type'] == 'remove for abandon':
                status_str = 'abandoned'
            # no longer merge
            if item['type'] == 'remove for cannot merge':
                status_str = 'conflicted'
            # not live
            if item['type'] == 'item is not live':
                status_str = 'not live'

            # merge fail
            if item['type'] == 'finish with merge fail':
                status_str = 'merge fail'
            # no job
            if item['type'] == 'finish with no job':
                status_str = 'no job'
            # success
            if item['type'] == 'success':
                status_str = 'success'
            # fail
            if item['type'] == 'fail':
                status_str = 'fail'

            if not end_id and item['type'] == 'remove from queue':
                end_id = item['id']

        window_waiting_duration = 0
        merge_duration = 0
        pre_launch_duration = 0
        first_launch_duration = 0
        job_running_duration = 0
        dequeue_duration = 0
        total_duration = 0
        reschedule_total_time = 0
        if not end_id:
            end_id = list_[-1]['id']

        if merge_time > finish_time:
            merge_time = None
            log.debug('merge_time > finish_time, status is %s', status_str)
        if merged_time > finish_time:
            merge_time = None
            merged_time = None
            log.debug('merged_time > finish_time, status is %s', status_str)

        if start_time:
            if waiting_for_window_time:
                reschedule_total_time = (this_start_time - waiting_for_window_time).total_seconds() * 1000
                if merge_time:
                    reschedule_total_time = (merge_time - waiting_for_window_time).total_seconds() * 1000
                if reschedule_total_time < 0:
                    reschedule_total_time = 0
                if reschedule_total_time > 0 and reschedule_times < 1:
                    reschedule_times = 1

                window_waiting_duration = (waiting_for_window_time - start_time).total_seconds() * 1000
            if not waiting_for_window_time:
                log.debug('error, no waiting_for_window_time')
                dequeue_duration = (finish_time - start_time).total_seconds() * 1000
            if merge_time:
                if merged_time:
                    merge_duration = (merged_time - merge_time).total_seconds() * 1000
                    if launch_job_time:
                        pre_launch_duration = (launch_job_time - merged_time).total_seconds() * 1000
                        if launched_job_time:
                            if launched_job_time > finish_time:
                                log.debug('launched time error, {} > {}'.format(launched_job_time, finish_time))
                                launched_job_time = finish_time
                            first_launch_duration = (launched_job_time - launch_job_time).total_seconds() * 1000
                            if complete_job_time:
                                if complete_job_time > finish_time:
                                    log.debug('complete_job_time time error, {} > {}'.format(complete_job_time, finish_time))
                                    complete_job_time = finish_time
                                job_running_duration = (complete_job_time - launched_job_time).total_seconds() * 1000
                                dequeue_duration = (finish_time - complete_job_time).total_seconds() * 1000
                            else:
                                log.debug('error, no complete_job_time')
                                job_running_duration = (finish_time - launched_job_time).total_seconds() * 1000
                        else:
                            log.debug('error, no launched job time')
                            dequeue_duration = (finish_time - launch_job_time).total_seconds() * 1000
                    else:
                        log.debug('no launch time, status is %s', status_str)
                        dequeue_duration = (finish_time - merged_time).total_seconds() * 1000
                else:
                    log.debug('error, no merged time')
                    dequeue_duration = (finish_time - merge_time).total_seconds() * 1000
        total_duration = (finish_time - start_time).total_seconds() * 1000
        obj = self.GateStatistics(
            changeset=changeset,
            queue_item=queue_item,
            pipeline=pipeline,
            begin_id=begin_id,
            finish_id=end_id,
            start_time=start_time,
            end_time=finish_time,
            window_waiting_time=window_waiting_duration,
            merge_time=merge_duration,
            pre_launch_time=pre_launch_duration,
            first_launch_time=first_launch_duration,
            job_running_time=job_running_duration,
            dequeue_duration=dequeue_duration,
            total_duration=total_duration,
            reschedule_times=reschedule_times,
            reschedule_total_duration=reschedule_total_time,
            status=status_str,
            result=(status_str == 'success'),
        )
        self.session.add(obj)

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def main(db_str, db_str_dest='', table_name='t_gate_statistics', entry_num=5000, run_num=1):
    db = DbHandler(db_str)
    if not db_str_dest:
        db2 = db
    else:
        db2 = DbHandler(db_str_dest)
    try:
        db2.init_db(table_name)

        for i in range(0, run_num):
            last_end = db2.get_last_end_no()
            log.debug('last end is %s', last_end)

            rd = db.get_end_list(last_end, entry_num)

            if not rd:
                log.debug('No more id to process, break')
                break

            for end_item in rd:
                log.debug('Process %s', end_item)
                op_list = db.get_op_list_from_end(end_item)
                db2.save_op_list(op_list)
                log.debug('\n------')

            log.debug('committing...')
            db2.commit()
            log.debug('done')
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
        traceback.print_exc()
        sys.exit(2)
