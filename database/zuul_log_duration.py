import sys
import traceback

import arrow
import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from model import LogAction
from model import LogDuration


class DbHandler(object):
    start_strings = ['adding to queue', 'cancel job']
    end_strings = ['remove from queue', 'resetting for nnfi',
                   'resetting for not merge']

    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def init_db(self):
        LogDuration.metadata.create_all(self.engine)

    def get_last_begin_no(self):
        query = self.session.query(LogDuration.begin_id) \
            .order_by(sa.desc(LogDuration.id))
        result = query.first()
        if not result:
            return -1
        return result.begin_id

    def get_last_end_no(self):
        query = self.session.query(LogDuration.finish_id) \
            .order_by(sa.desc(LogDuration.id))
        result = query.first()
        if not result:
            return -1
        return result.finish_id

    def get_last_begin_end_no(self, id_, change_item, begin=True):
        if begin:
            print('Find previous one for {}, {}, and it should be begin'
                  .format(id_, change_item))
        else:
            print('Find previous one for {}, {}, and it should be end'
                  .format(id_, change_item))
        query = self.session.query(LogAction)\
            .filter(sa.or_(LogAction.type == 'adding to queue',
                           LogAction.type == 'remove from queue'),
                    LogAction.id < id_,
                    LogAction.change_item == change_item)\
            .order_by(sa.desc(LogAction.id))
        result = query.first()
        if not result:
            print('result is None')
            return None
        else:
            if begin:
                if result.type != 'adding to queue':
                    print('Previous one is end, abandon')
                    return None
            else:
                if result.type != 'remove from queue':
                    print('Previous one is begin, abandon')
                    return None
        if result.type == 'adding to queue':
            rt = 'begin'
        else:
            rt = 'end'
        ri = {'id': result.id, 'type': rt, 'change': result.change_item}
        print('Previous one is {}'.format(ri['id']))
        return ri

    def get_border_dict(self, begin, limit):
        query = self.session.query(LogAction) \
            .filter(sa.or_(LogAction.type == 'adding to queue',
                           LogAction.type == 'remove from queue'),
                    LogAction.id > begin) \
            .order_by(LogAction.id) \
            .limit(limit) \
            .all()

        rd = {}
        rlb = []
        rle = []

        for row in query:
            if row.type == 'adding to queue':
                rt = 'begin'
            else:
                rt = 'end'

            if not row.pipeline:
                pipeline = 'unknown'
            else:
                pipeline = row.pipeline

            ri = {'id': row.id, 'type': rt, 'change': row.change_item,
                  'pipeline': pipeline}

            if rt == 'begin':
                rlb.append(ri)
            else:
                rle.append(ri)

            if row.change_item in rd:
                if pipeline not in rd[row.change_item]:
                    rd[row.change_item][pipeline] = [ri]
                else:
                    rd[row.change_item][pipeline].append(ri)
            else:
                rd[row.change_item] = {}
                rd[row.change_item][pipeline] = [ri]

        rd['begin_list'] = rlb
        rd['end_list'] = rle
        return rd

    def get_op_list(self, from_, to, change_item, pipeline):
        rl = []
        if pipeline == 'unknown':
            pipeline = ''
        query = self.session.query(LogAction) \
            .filter(LogAction.id <= to,
                    LogAction.id >= from_,
                    LogAction.change_item == change_item,
                    LogAction.pipeline == pipeline) \
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
        launch_job_time = None
        finish_time = None
        status_str = None
        pipeline = list_[0]['pipeline']
        change_item = list_[0]['change_item']
        begin_id = list_[0]['id']
        end_id = list_[-1]['id']
        changeset = '{},{}'.format(list_[0]['change'], list_[0]['patchset'])

        duration_ms = 0
        duration_lm = 0
        duration_fl = 0
        for item in list_:
            # start
            if not start_time:
                if item['type'] in self.start_strings:
                    start_time = item['datetime']
            # merge
            if item['type'] == 'prepare ref':
                merge_time = item['datetime']
            # launch
            if item['type'] == 'launch job' and not launch_job_time:
                launch_job_time = item['datetime']
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

        if start_time and merge_time:
            duration_ms = \
                (arrow.get(merge_time) - arrow.get(start_time))\
                .total_seconds() * 1000

        if launch_job_time and merge_time:
            duration_lm = \
                (arrow.get(launch_job_time) - arrow.get(merge_time))\
                .total_seconds() * 1000

        if launch_job_time and finish_time:
            duration_fl = \
                (arrow.get(finish_time) - arrow.get(launch_job_time))\
                .total_seconds() * 1000

        obj = LogDuration(
            changeset=changeset,
            kind=pipeline,
            start_time=start_time,
            duration_ms=duration_ms,
            merge_time=merge_time,
            duration_lm=duration_lm,
            launch_time=launch_job_time,
            duration_fl=duration_fl,
            finish_time=finish_time,
            begin_id=begin_id,
            finish_id=end_id,
            status=status_str,
            change_item=change_item
        )
        self.session.add(obj)
        self.session.commit()


def _main(db_str, entry_num=5000, run_num=1):
    db = DbHandler(db_str)
    db.init_db()

    for i in range(0, run_num):
        last_end = db.get_last_end_no()

        rd = db.get_border_dict(last_end, entry_num)
        rl = rd['end_list']

        for key, value in rd.items():  # change, dict
            if key == 'begin_list':
                continue
            if key == 'end_list':
                continue

            for key2, value2 in value.items():  # pipeline, info object list
                fi = value2[0]
                if fi['type'] == 'end':
                    ri = db.get_last_begin_end_no(fi['id'],
                                                  fi['change'], begin=True)
                    if ri:
                        value2.insert(0, ri)

        for end_item in rl:
            # find begin item
            end_id = end_item['id']
            begin_id = -1
            slist = rd[end_item['change']][end_item['pipeline']]
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
                    begin_id, end_id, end_item['change'], end_item['pipeline'])
                db.save_op_list(op_list)
            else:
                print('id {} is without begin'.format(end_id))


def _test(db_str):
    db = DbHandler(db_str)
    db.init_db()
    begin = 0
    limit = 10000
    query = db.session.query(LogAction)\
        .filter(sa.or_(LogAction.type == 'adding to queue', LogAction.type == 'remove from queue'), LogAction.id > begin)\
        .order_by(LogAction.id)\
        .limit(limit)\
        .all()

    begin_dict = {}

    for row in query:
        if row.type == 'adding to queue':
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
        fire.Fire(_main)
    except Exception as e:
        print('Exception: {}'.format(str(e)))
        traceback.print_exc()
        sys.exit(2)
