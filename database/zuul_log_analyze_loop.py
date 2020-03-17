import re
import sys
import traceback
import copy

import arrow
import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from model import get_loop_action_model

Loop_Action = get_loop_action_model()

# some regex
# for build item
# <Build (?P<build_item>.*) of (?P<job_name>.*) on (?P<worker>.*)>
# for change
# <Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)>
# for queue item
# <QueueItem (?P<queue_item>.*) for <Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in (?P<pipeline>.*)>

reg_log = re.compile(
    r'(?P<date>\d\d\d\d-\d\d-\d\d) '
    r'(?P<time>\d\d:\d\d:\d\d),(?P<ms>\d\d\d) '
    r'(?P<level>\w*) '
    r'((?P<thread>\d*) )?'
    r'((?P<logger>[^:]*): )?(?P<info>.*)')

reg_begin_loop = re.compile(r'Run handler awake')
reg_end_loop = re.compile(r'Run handler sleeping')
ssh_command_begin = re.compile(r'SSH command: \[(?P<command>.*)\]')
ssh_command_end = re.compile(r'SSH exit status: (?P<status>.*)')
item_begin = re.compile(r'Function <_processOneItem> begins\.')
item_end = re.compile(r'Function <_processOneItem> took (?P<duration>\d*) ms to finish\.')
db_begin = re.compile(r'Appending to db:')
db_end = re.compile(r'Update DB <QueueItem (?P<queue_item>.*) for <Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in (?P<pipeline>.*)> successfully\.')
db_end2 = re.compile(r'Exception (?P<Exception>.*)')
launch_begin = re.compile(r'Launch job (?P<job>.*) \(uuid: (?P<uuid>.*)\) for change item <QueueItem (?P<queue_item>.*) for <Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in (?P<pipeline>.*)> with dependent changes (?P<depend>.*)')
launch_end = re.compile(r'Job (?P<job>.*) is not registered with Gearman')
launch_end2 = re.compile(r'Unable to submit job to Gearman')
launch_end3 = re.compile(r'Received handle (?P<handle>.*) for (?P<build>.*)')
cancel_begin = re.compile(r'Cancel build (.*) for job (.*)')
cancel_end = re.compile(r'Build (.*) has no associated gearman job')
cancel_end2 = re.compile(r'Canceled running build (.*)')
cancel_end3 = re.compile(r'Removed build (.*) from queue')
cancel_end4 = re.compile(r'Unable to cancel build (.*)')


reg_list = [
    {'reg': reg_begin_loop, 'action': 'begin loop', 'type': 0},  # 0 lone line 1 start line 2 end line 3 Find matched line
    {'reg': reg_end_loop, 'action': 'end loop', 'type': 3, 'match_action': 'begin loop'},
    {'reg': item_begin, 'action': 'begin item', 'type': 0},
    {'reg': item_end, 'action': 'end item', 'type': 3, 'match_action': 'begin item'},
    {'reg': db_begin, 'action': 'db', 'type': 1},
    {'reg': db_end, 'action': 'db', 'type': 2, 'logger': 'zuul.reporter.mysql.SQLReporter'},
    {'reg': db_end2, 'action': 'db', 'type': 2, 'logger': 'zuul.reporter.mysql.SQLReporter'},
    {'reg': ssh_command_begin, 'action': 'ssh', 'type': 1},
    {'reg': ssh_command_end, 'action': 'ssh', 'type': 2},
    {'reg': launch_begin, 'action': 'launch', 'type': 1},
    {'reg': launch_end, 'action': 'launch', 'type': 2},
    {'reg': launch_end2, 'action': 'launch', 'type': 2},
    {'reg': launch_end3, 'action': 'launch', 'type': 2},
    {'reg': cancel_begin, 'action': 'cancel', 'type': 1},
    {'reg': cancel_end, 'action': 'cancel', 'type': 2},
    {'reg': cancel_end2, 'action': 'cancel', 'type': 2},
    {'reg': cancel_end3, 'action': 'cancel', 'type': 2},
    {'reg': cancel_end4, 'action': 'cancel', 'type': 2},
]


class LogLine(object):
    def __init__(self, tz):
        self.date = None
        self.time = None
        self.ms = None
        self.thread = None
        self.logger = None
        self.infos = None
        self.action = None
        self.detail = None
        self.type = None  # 0 lone line 1 start line 2 end line 3 Find matchline
        self.match_action = None
        self.tz = tz

    def set(self, match):
        self.date = match.group('date')
        self.time = match.group('time')
        self.ms = int(match.group('ms'))
        self.thread = match.group('thread')
        self.logger = match.group('logger')
        self.infos = [match.group('info')]
        self.action = ''
        self.detail = ''
        self.type = None
        self.match_action = None

    def append(self, string):
        if self.infos:
            self.infos.append(string)

    def parse(self):
        if not self.infos:
            return

        info = self.infos[0]
        for reg in reg_list:
            m = reg['reg'].match(info)
            if m:
                if 'logger' in reg:
                    if reg['logger'] != self.logger:
                        continue
                self.action = reg['action']
                self.type = reg['type']
                self.detail = '\n'.join(self.infos)
                if 'match_action' in reg:
                    self.match_action = reg['match_action']
                break

    def get_utc(self):
        timestr = '{}T{}.{:0>3}'.format(
            self.date,
            self.time,
            self.ms
        )
        adt = arrow.get(timestr)
        adt = adt.replace(tzinfo=self.tz)
        udt = adt.to('utc')
        return udt


class DbHandler(object):
    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def init_db(self):
        Loop_Action.metadata.create_all(self.engine)

    def get_last_match(self, action, oaction):
        query = self.session.query(Loop_Action)\
            .filter(sa.or_(Loop_Action.action == action,
                           Loop_Action.action == oaction)) \
            .order_by(sa.desc(Loop_Action.id))\
            .limit(1)
        result = query.first()
        if not result:
            return None
        if result.action == oaction:
            return None
        return result.begintime

    def write_log(self, data):

        obj = Loop_Action(
            begintime=data['begintime'].datetime,
            endtime=data['endtime'].datetime,
            duration=data['duration'],
            thread_id=data['thread_id'],
            logger=data['logger'],
            action=data['action'],
            detail=data['detail'],
            result=data['result']
        )

        self.session.add(obj)

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def parse_log(db, main_thread, current_begin, log_line):
    if log_line.action.startswith('begin loop'):
        main_thread = log_line.thread
    if not main_thread:
        return main_thread, current_begin
    if main_thread != log_line.thread:
        return main_thread, current_begin
    print('{} {}.{} [{}] {}'.format(
        log_line.date, log_line.time, log_line.ms, log_line.action, log_line.logger))
    for info in log_line.infos:
        print('-->{}'.format(info))
    if current_begin:
        if log_line.type == 2 and log_line.action == current_begin.action:
            write_entry(db, current_begin, log_line)
            current_begin = None
        else:
            print('current begin [{}], line [{},{}], not match'.format(current_begin.action, log_line.action, log_line.type))
            write_entry(db, current_begin, log_line, True)
            current_begin = None

    if log_line.type == 1:
        current_begin = copy.copy(log_line)

    if log_line.type == 0:
        write_begin(db, log_line)

    if log_line.type == 3:
        write_end(db, log_line)

    return main_thread, current_begin


def write_entry(db, begin, end, no_result=False):
    data = dict()
    data['begintime'] = begin.get_utc()
    data['endtime'] = end.get_utc()
    data['duration'] = (data['endtime'] - data['begintime']).total_seconds() * 1000
    data['thread_id'] = begin.thread
    data['logger'] = begin.logger
    data['action'] = begin.action
    data['detail'] = begin.detail

    if no_result:
        data['result'] = ''
    else:
        data['result'] = end.detail
    db.write_log(data)


def write_begin(db, begin):
    data = dict()
    data['begintime'] = begin.get_utc()
    data['endtime'] = data['begintime']
    data['duration'] = 0
    data['thread_id'] = begin.thread
    data['logger'] = begin.logger
    data['action'] = begin.action
    data['detail'] = begin.detail
    data['result'] = ''
    db.write_log(data)


def write_end(db, end):
    data = dict()
    begintime = arrow.get(db.get_last_match(end.match_action, end.action))
    if not begintime:
        begintime = end.get_utc()
    data['begintime'] = begintime
    data['endtime'] = end.get_utc()
    data['duration'] = (data['endtime'] - data['begintime']).total_seconds() * 1000
    data['thread_id'] = end.thread
    data['logger'] = end.logger
    data['action'] = end.action
    data['detail'] = end.detail
    data['result'] = ''
    db.write_log(data)


def main(log_path, db_str, tz=None):
    try:
        db = DbHandler(db_str)
        db.init_db()
        if not tz:
            tz = 'America/New_York'
        log_line = LogLine(tz=tz)
        main_thread = ''
        current_begin = None
        with open(log_path) as f:
            lines = f.readlines()
            for line in lines:
                m = reg_log.match(line)
                if m:
                    log_line.parse()
                    if log_line.type is not None:
                        main_thread, current_begin = parse_log(db, main_thread, current_begin, log_line)
                    log_line.set(m)
                else:
                    log_line.append(line)
            log_line.parse()
            if log_line.type is not None:
                main_thread, current_begin = parse_log(db, main_thread, current_begin, log_line)
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
