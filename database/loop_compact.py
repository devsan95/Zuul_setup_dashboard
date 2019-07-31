import sys
import traceback

import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from model import get_loop_action_model, get_loop_compact_model

Loop_Action = get_loop_action_model()
Loop_Compact = get_loop_compact_model()


class DbHandler(object):
    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def init_db(self):
        Loop_Action.metadata.create_all(self.engine)
        Loop_Compact.metadata.create_all(self.engine)

    def get_loop_action_entries(self, greater_than, limit):
        query = self.session.query(Loop_Action)\
            .filter(Loop_Action.id > greater_than)\
            .order_by(sa.asc(Loop_Action.id))\
            .limit(limit)
        result = query.all()
        return result

    def get_last_scan_id(self):
        query = self.session.query(Loop_Compact)\
            .order_by(sa.desc(Loop_Compact.ref_id))\
            .limit(1)
        result = query.first()
        if not result:
            return 0
        return result.ref_id

    def write_loop(self, loop):
        if 'lines' not in loop:
            return
        if len(loop) <= 2:
            return
        begin_entry = loop['begin loop']
        end_entry = loop['end loop']
        print('Proceed Loop from [{}|{}] to [{}|{}]'.format(begin_entry['ref_id'], begin_entry['datetime'], end_entry['ref_id'], end_entry['datetime']))
        self.write_log(begin_entry)
        # for key, value in loop.iteritems():
        #     if key != 'begin loop' and key != 'end loop':
        #         self.write_log(value)
        for entry in loop['lines']:
            self.write_log(entry)
        self.write_log(end_entry)

    def write_log(self, data):
        try:
            average = 0
            if data['times'] > 0:
                average = float(data['duration']) / data['times']
            obj = Loop_Compact(
                ref_id=data['ref_id'],
                datetime=data['datetime'],
                duration=data['duration'],
                times=data['times'],
                average=average,
                action=data['action'],
            )
        except Exception as e:
            print data
            print e
            raise

        self.session.add(obj)

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def main(db_str, entry_number, run_times):
    try:
        db = DbHandler(db_str)
        db.init_db()
        last_id = -1
        for i in range(0, run_times):
            last_id_new = db.get_last_scan_id()
            if last_id_new == last_id:
                print('Last id {} is not changed, break!'.format(last_id))
                break
            last_id = last_id_new
            print('Last id is {}'.format(last_id))
            process_list = db.get_loop_action_entries(last_id, entry_number)
            write_group = {}
            for entry in process_list:
                if 'begin loop' in write_group:
                    begin_entry = write_group['begin loop']
                    end_entry = write_group['end loop']
                    if entry.action == 'begin loop':
                        end_entry['ref_id'] = -1
                        end_entry['datetime'] = entry.begintime
                        duration = (entry.begintime - begin_entry['datetime']).total_seconds() * 1000
                        end_entry['duration'] = duration
                        db.write_loop(write_group)
                        write_group = {
                            'begin loop':
                                {
                                    'ref_id': entry.id,
                                    'datetime': entry.begintime,
                                    'duration': 0,
                                    'times': 0,
                                    'action': entry.action,
                                },
                            'end loop':
                                {
                                    'ref_id': None,
                                    'datetime': None,
                                    'duration': 0,
                                    'times': 0,
                                    'action': 'end loop',
                                }
                        }
                    elif entry.action == 'end loop':
                        end_entry['ref_id'] = entry.id
                        end_entry['datetime'] = entry.endtime
                        duration = (entry.endtime - begin_entry['datetime']).total_seconds() * 1000
                        end_entry['duration'] = duration

                        db.write_loop(write_group)
                        write_group = {}
                    elif entry.action == 'begin item':
                        end_entry['times'] += 1
                    elif entry.action == 'end item':
                        pass
                    elif entry.action == 'db' and not entry.result:
                        pass
                    else:
                        # if entry.action not in write_group:
                        #     write_group[entry.action] = {
                        #         'ref_id': None,
                        #         'datetime': None,
                        #         'duration': 0,
                        #         'times': 0,
                        #         'action': entry.action,
                        #     }
                        # action_entry = write_group[entry.action]
                        # action_entry['duration'] += entry.duration
                        # action_entry['times'] += 1
                        if 'lines' not in write_group:
                            write_group['lines'] = []
                        write_group['lines'].append(
                            {
                                'ref_id': entry.id,
                                'datetime': entry.begintime,
                                'duration': entry.duration,
                                'times': 1,
                                'action': entry.action,
                            }
                        )
                else:
                    if entry.action == 'begin loop':
                        write_group['begin loop'] = {
                            'ref_id': entry.id,
                            'datetime': entry.begintime,
                            'duration': 0,
                            'times': 0,
                            'action': entry.action,
                        }
                        write_group['end loop'] = {
                            'ref_id': None,
                            'datetime': None,
                            'duration': 0,
                            'times': 0,
                            'action': 'end loop',
                        }
            print('Commit...')
            db.commit()

    except Exception as ex:
        print('Exception occurs:')
        print(ex)
        print('rollback')
        traceback.print_exc()
        db.rollback()
        sys.exit(2)


if __name__ == '__main__':
    try:
        fire.Fire(main)
    except Exception as e:
        print('Exception: {}'.format(str(e)))
        traceback.print_exc()
        sys.exit(2)
