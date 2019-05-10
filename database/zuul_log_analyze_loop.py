import re
import sys
import traceback

import arrow
import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from model import LogAction

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

reg_list = [
    {'reg': reg_begin_loop, 'action': 'begin loop', 'type': 0},
    {'reg': reg_end_loop, 'action': 'end loop', 'type': 3, 'match_action': 'begin loop'},
]


class LogLine(object):
    def __init__(self):
        self.date = None
        self.time = None
        self.ms = None
        self.thread = None
        self.logger = None
        self.infos = None
        self.action = None
        self.detail = None
        self.pipeline = None
        self.project = None
        self.queue_item = None
        self.location = None
        self.prefix = None
        self.type = None  # 0 lone line 1 start line 2 end line 3 Find matchline
        self.match_action = None

    def set(self, match, location, prefix):
        self.date = match.group('date')
        self.time = match.group('time')
        self.ms = int(match.group('ms'))
        self.thread = match.group('thread')
        self.logger = match.group('logger')
        self.infos = [match.group('info')]
        self.action = ''
        self.detail = ''
        self.pipeline = ''
        self.project = ''
        self.queue_item = ''
        self.location = location
        self.prefix = prefix
        self.type = None

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
                self.action = reg['action']
                getattr(self, '_handle_' + self.action.replace(' ', '_'))()(m)

                print('{} {}.{} [{}] {}'.format(
                    self.date, self.time, self.ms,
                    self.action, self.logger))
                for info in self.infos:
                    print('-->{}'.format(info))
                break

    def _handle_begin_loop(self, result):
        pass


class DbHandler(object):
    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def init_db(self):
        LogAction.metadata.create_all(self.engine)

    def write_log(self, log_line):
        ll = log_line
        timestr = '{}T{}.{:0>3}'.format(
            log_line.date,
            log_line.time,
            log_line.ms
        )
        adt = arrow.get(timestr)
        adt = adt.replace(tzinfo='America/New_York')
        udt = adt.to('utc')
        if len(ll.infos) > 1:
            text = '\n'.join(ll.infos)
        else:
            text = ll.infos[0]
        if not ll.change:
            ll.change = '0'

        obj = LogAction(
            datetime=udt.datetime,
            thread_id=ll.thread,
            logger=ll.logger,
            type=ll.type,
            change=int(ll.change),
            queue=ll.queue,
            pipeline=ll.pipeline,
            project=ll.project,
            change_item=ll.change_item,
            queue_item=ll.queue_item,
            text=text,
            job=ll.job
        )
        self.session.add(obj)

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def _test():
    log_line = LogLine()
    lines = [
        '2018-03-14 05:58:23,212 DEBUG 139914440066816 zuul.IndependentPipelineManager: Change <Change 0x7f4054261dd0 262009,1> abandoned, removing.'
    ]
    for line in lines:
        m = reg_log.match(line)
        if m:
            log_line.set(m)
            log_line.parse()
        else:
            log_line.append(line)
    print(log_line)


def main(log_path, db_str):
    try:
        db = DbHandler(db_str)
        db.init_db()
        log_line = LogLine()
        with open(log_path) as f:
            lines = f.readlines()
            for line in lines:
                m = reg_log.match(line)
                if m:
                    log_line.parse()
                    if log_line.type:
                        db.write_log(log_line)
                    log_line.set(m)
                else:
                    log_line.append(line)
        db.commit()
    except Exception as ex:
        print('Exception occurs:')
        print(ex)
        print('rollback')
        db.rollback()
        raise ex


if __name__ == '__main__':
    try:
        fire.Fire(main)
    except Exception as e:
        print('Exception: {}'.format(str(e)))
        traceback.print_exc()
        sys.exit(2)
