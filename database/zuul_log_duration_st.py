import sys
import traceback

import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from model import LogAction
from model import get_log_duration_model


class DbHandler(object):
    start_strings = ['added to queue', 'cancel job']
    end_strings = ['remove from queue', 'resetting for nnfi',
                   'resetting for not merge']

    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.LogDuration = None

    def init_db(self, table_name=''):
        if table_name:
            self.LogDuration = get_log_duration_model(table_name)
        else:
            self.LogDuration = get_log_duration_model('log_duration')
        self.LogDuration.metadata.create_all(self.engine)

    def get_last_begin_no(self):
        query = self.session.query(self.LogDuration.begin_id) \
            .order_by(sa.desc(self.LogDuration.id))
        result = query.first()
        if not result:
            return -1
        return result.begin_id

    def get_last_end_no(self):
        query = self.session.query(self.LogDuration.finish_id) \
            .order_by(sa.desc(self.LogDuration.finish_id))
        result = query.first()
        if not result:
            return -1
        return result.finish_id

    def get_last_begin_end_no(self, id_, queue_item, begin=True):
        if begin:
            print('Find previous one for {}, {}, and it should be begin'
                  .format(id_, queue_item))
        else:
            print('Find previous one for {}, {}, and it should be end'
                  .format(id_, queue_item))
        query = self.session.query(LogAction)\
            .filter(sa.or_(LogAction.type == 'added to queue',
                           LogAction.type == 'remove from queue'),
                    LogAction.id < id_,
                    LogAction.queue_item == queue_item)\
            .order_by(sa.desc(LogAction.id))
        result = query.first()
        if not result:
            print('result is None')
            return None
        else:
            if begin:
                if result.type != 'added to queue':
                    print('Previous one is end, abandon')
                    return None
            else:
                if result.type != 'remove from queue':
                    print('Previous one is begin, abandon')
                    return None
        if result.type == 'added to queue':
            rt = 'begin'
        else:
            rt = 'end'
        ri = {'id': result.id, 'type': rt, 'change': result.change_item,
              'queue_item': result.queue_item}
        print('Previous one is {}'.format(ri['id']))
        return ri

    def get_border_dict(self, begin, limit):
        query = self.session.query(LogAction) \
            .filter(sa.or_(LogAction.type == 'added to queue',
                           LogAction.type == 'remove from queue'),
                    LogAction.id > begin) \
            .order_by(LogAction.id) \
            .limit(limit) \
            .all()

        rd = {}
        rlb = []
        rle = []

        for row in query:
            if row.type == 'added to queue':
                rt = 'begin'
            else:
                rt = 'end'

            if not row.queue_item:
                queue_item = 'unknown'
            else:
                queue_item = row.queue_item

            ri = {'id': row.id, 'type': rt, 'change': row.change_item,
                  'pipeline': queue_item, 'queue_item': row.queue_item}

            if rt == 'begin':
                rlb.append(ri)
            else:
                rle.append(ri)

            if row.change_item in rd:
                if queue_item not in rd[row.change_item]:
                    rd[row.change_item][queue_item] = [ri]
                else:
                    rd[row.change_item][queue_item].append(ri)
            else:
                rd[row.change_item] = {}
                rd[row.change_item][queue_item] = [ri]

        rd['begin_list'] = rlb
        rd['end_list'] = rle
        return rd

    def get_op_list(self, from_, to, change_item, queue_item):
        rl = []
        if queue_item == 'unknown':
            queue_item = ''
        query = self.session.query(LogAction) \
            .filter(LogAction.id <= to,
                    LogAction.id >= from_,
                    LogAction.change_item == change_item,
                    LogAction.queue_item == queue_item) \
            .order_by(LogAction.id)
        result = query.all()
        for row in result:
            dictrow = dict(row.__dict__)
            dictrow.pop('_sa_instance_state', None)
            rl.append(dictrow)
        return rl

    def find_string_index(self, list_, start_no, start):
        for i in range(start_no, len(list_)):
            item = list_[i]
            if start:
                if item['type'] in self.start_strings:
                    return i
            else:
                if item['type'] in self.end_strings:
                    return i
        return -1

    def save_op_list(self, list_):
        index = 0
        while index < len(list_):
            begin_item = self.find_string_index(list_, index, True)
            end_item = self.find_string_index(list_, begin_item, False)
            if begin_item == -1:
                begin_item = index
            if end_item == -1:
                end_item = len(list_) - 1
            index = end_item + 1
            self.save_op_list_(list_[begin_item:(end_item + 1)])

    def save_op_list_(self, list_):
        start_time = None
        merge_time = None
        merged_time = None
        launch_job_time = None
        launched_job_time = None
        complete_job_time = None
        finish_time = None
        result = None
        status_str = None
        pipeline = list_[0]['pipeline']
        queue_item = list_[0]['queue_item']
        change_item = list_[0]['change_item']
        begin_id = list_[0]['id']
        end_id = list_[-1]['id']
        changeset = '{},{}'.format(list_[0]['change'], list_[0]['patchset'])

        for item in list_:
            # start
            if not start_time:
                if item['type'] in self.start_strings:
                    start_time = item['datetime']
            # merge
            if item['type'] == 'prepare ref':
                merge_time = item['datetime']
            # merged
            if item['type'] in ['merge failed', 'merge complete']:
                merged_time = item['datetime']
            # launch
            if item['type'] == 'launch job' and not launch_job_time:
                launch_job_time = item['datetime']
            # launched
            if item['type'] == 'job started' and not launched_job_time:
                launched_job_time = item['datetime']
            # complete
            if item['type'] in \
               ['job started', 'job completed', 'job cancelled']:
                if item['type'] == 'job started':
                    complete_job_time = None
                else:
                    complete_job_time = item['datetime']
            # finish
            if not finish_time:
                if item['type'] in self.end_strings:
                    finish_time = item['datetime']
                    if item['type'].startswith('resetting'):
                        status_str = item['type']

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
                result = 1
            # fail
            if item['type'] == 'fail':
                status_str = 'fail'

        obj = self.LogDuration(
            changeset=changeset,
            kind=pipeline,
            start_time=start_time,
            merge_time=merge_time,
            merged_time=merged_time,
            launch_time=launch_job_time,
            launched_time=launched_job_time,
            completed_time=complete_job_time,
            finish_time=finish_time,
            begin_id=begin_id,
            finish_id=end_id,
            status=status_str,
            change_item=change_item,
            queue_item=queue_item,
            result=result
        )
        self.session.add(obj)

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def main(db_str, db_str_dest='', table_name='', entry_num=5000, run_num=1):
    db = DbHandler(db_str)
    if not db_str_dest:
        db2 = db
    else:
        db2 = DbHandler(db_str_dest)
    try:
        db2.init_db(table_name)

        for i in range(0, run_num):
            last_end = db2.get_last_end_no()

            rd = db.get_border_dict(last_end, entry_num)
            rl = rd['end_list']

            if not rl:
                print('No more id to process, break')
                break

            for key, value in rd.items():  # change, dict
                if key == 'begin_list':
                    continue
                if key == 'end_list':
                    continue

                for key2, value2 in value.items():  # queue_item, info object list
                    fi = value2[0]
                    if fi['type'] == 'end':
                        ri = db.get_last_begin_end_no(fi['id'],
                                                      fi['queue_item'], begin=True)
                        if ri:
                            value2.insert(0, ri)

            for end_item in rl:
                # find begin item
                end_id = end_item['id']
                begin_id = -1
                slist = rd[end_item['change']][end_item['queue_item']]
                for j in range(1, len(slist)):
                    sitem = slist[j]
                    psitem = slist[j - 1]
                    if sitem['id'] == end_item['id']:
                        if psitem['type'] == 'begin':
                            begin_id = psitem['id']
                        break
                    j += 1

                if begin_id > 0:
                    print('tuple: {}, {}'.format(begin_id, end_id))
                    op_list = db.get_op_list(
                        begin_id, end_id, end_item['change'],
                        end_item['queue_item'])
                    db2.save_op_list(op_list)
                else:
                    print('id {} is without begin'.format(end_id))

        db2.commit()
    except Exception as ex:
        print('Exception occurs:')
        print(ex)
        print('rollback')
        db2.rollback()
        raise ex


def _test(db_str):
    db = DbHandler(db_str)
    db.init_db()
    begin = 0
    limit = 10000
    query = db.session.query(LogAction)\
        .filter(sa.or_(LogAction.type == 'added to queue', LogAction.type == 'remove from queue'), LogAction.id > begin)\
        .order_by(LogAction.id)\
        .limit(limit)\
        .all()

    begin_dict = {}

    for row in query:
        if row.type == 'added to queue':
            rt = 'begin'
        else:
            rt = 'end'
        ri = {'id': row.id, 'type': rt}
        if row.change_item in begin_dict:
            begin_dict[row.change_item].append(ri)
        else:
            begin_dict[row.change_item] = [ri]

    import pprint
    pprint.pprint(begin_dict)


if __name__ == '__main__':
    try:
        fire.Fire(main)
    except Exception as e:
        print('Exception: {}'.format(str(e)))
        traceback.print_exc()
        sys.exit(2)
