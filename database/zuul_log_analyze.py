import re
import sys
import traceback

import arrow
import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from model import LogAction

reg_log = re.compile(
    r'(?P<date>\d\d\d\d-\d\d-\d\d) '
    r'(?P<time>\d\d:\d\d:\d\d),(?P<ms>\d\d\d) '
    r'(?P<level>\w*) '
    r'((?P<thread>\d*) )?'
    r'((?P<logger>[^:]*): )?(?P<info>.*)')
reg_enter = re.compile(
    r'Adding (?P<project>.*), <Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> to '
    r'<Pipeline (?P<pipeline>.*)>')
reg_enter_queue = re.compile(
    r'Adding change '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> '
    r'to queue '
    r'<ChangeQueue (?P<pipeline>[^:]*): (?P<queue>.*)>'
)
reg_remove = re.compile(
    r'Removing change '
    r'<QueueItem '
    r'(?P<queue_item>.*) for '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)>'
    r' in (?P<pipeline>.*)> from queue'
)

reg_remove_item = re.compile(
    r'Canceling builds behind change: '
    r'<QueueItem '
    r'(?P<queue_item>.*) for '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)>'
    r' in (?P<pipeline>.*)> '
    r'because it is being removed\.'
)

reg_remove_replace = re.compile(
    r'Change '
    r'<Change (?P<item_new>.*) (?P<change_new>\d*),(?P<patchset_new>\d*)> '
    r'is a new version of '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)>, '
    r'removing '
    r'<QueueItem '
    r'(?P<queue_item>.*) for <Change .* \d*,\d*> in (?P<pipeline>.*)>'
)

reg_remove_abandon = re.compile(
    r'Item '
    r'<QueueItem '
    r'(?P<queue_item>.*) for '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)>'
    r' in (?P<pipeline>.*)> '
    r'abandoned, removing\.'
)

reg_remove_dequeue = re.compile(
    r'Dequeueing '
    r'<QueueItem (?P<queue_item>.*) for '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in '
    r'(?P<pipeline>.*)>'
)

reg_remove_can_not_merge = re.compile(
    r'Dequeuing change '
    r'<QueueItem (?P<queue_item>.*) for '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in '
    r'(?P<pipeline>.*)> '
    r'because it can no longer merge'
)

# Dequeue reason
# 1 removeItem: Canceling builds behind change: %s because it is being removed. (with log)
# 1.1 Change %s is a new version of %s, removing %s (with log)
# 1.2 Change %s abandoned, removing. (with log)
# 1.3 Dequeue event (partly log: Processing management event %s)
# 2 Dequeuing change %s because it can no longer merge (with log)
# 3 a non-live item with no items behind (without log)
# 4 change are completed (without log)

reg_report = re.compile(
    r'Reporting change <QueueItem (?P<queue_item>.*) for '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in '
    r'(?P<pipeline>.*)>'
)

reg_launch_job = re.compile(
    r'Launching jobs for change '
    r'<QueueItem (?P<queue_item>.*) for '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in '
    r'(?P<pipeline>.*)>'
)

reg_prepare_ref = re.compile(
    r'Preparing ref for: '
    r'<QueueItem (?P<queue_item>.*) for '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in '
    r'(?P<pipeline>.*)>'
)

reg_cancel_job = re.compile(
    r'Cancel jobs for change '
    r'<QueueItem (?P<queue_item>.*) for '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> in '
    r'(?P<pipeline>.*)>'
)

reg_resetting_for_nnfi = re.compile(
    r'Resetting builds for change '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> '
    r'because the item ahead, '
    r'<QueueItem (?P<previous_queue_item>.*) for '
    r'<Change (?P<previous_item>.*) (?P<previous_change>\d*),'
    r'(?P<previous_patchset>\d*)> '
    r'in (?P<pipeline>.*)>, '
    r'is not the nearest non-failing item, '
    r'(?P<nnfi>None|'
    r'<QueueItem (?P<nnfi_queue_item>.*) for '
    r'<Change (?P<nnfi_item>.*) (?P<nnfi_change>\d*),'
    r'(?P<nnfi_patchset>\d*)> in '
    r'(?P<nnfi_pipeline>.*)>)'
)

reg_resetting_for_not_merge = re.compile(
    r'Resetting builds for change '
    r'<Change (?P<item>.*) (?P<change>\d*),(?P<patchset>\d*)> '
    r'because the item ahead, '
    r'<QueueItem (?P<previous_queue_item>.*) for '
    r'<Change (?P<previous_item>.*) (?P<previous_change>\d*),(?P<previous_patchset>\d*)> '
    r'in (?P<pipeline>.*)>, failed to merge'
)

reg_list = [
    {'reg': reg_enter, 'type': 'adding to pipeline'},
    {'reg': reg_enter_queue, 'type': 'adding to queue'},
    {'reg': reg_remove, 'type': 'remove from queue'},
    {'reg': reg_remove_item, 'type': 'remove item'},
    {'reg': reg_remove_replace, 'type': 'remove for replace'},
    {'reg': reg_remove_abandon, 'type': 'remove for abandon'},
    {'reg': reg_remove_dequeue, 'type': 'remove for dequeue command'},
    {'reg': reg_remove_can_not_merge, 'type': 'remove for cannot merge'},
    {'reg': reg_report, 'type': 'report result'},
    {'reg': reg_launch_job, 'type': 'launch job'},
    {'reg': reg_prepare_ref, 'type': 'prepare ref'},
    {'reg': reg_cancel_job, 'type': 'cancel job'},
    {'reg': reg_resetting_for_nnfi, 'type': 'resetting for nnfi'},
    {'reg': reg_resetting_for_not_merge, 'type': 'resetting for not merge'}
]


class LogLine(object):
    def __init__(self):
        self.date = None
        self.time = None
        self.ms = None
        self.level = None
        self.thread = None
        self.logger = None
        self.infos = None
        self.type = None
        self.change = None
        self.patchset = None
        self.change_item = None
        self.queue = None
        self.pipeline = None
        self.project = None
        self.queue_item = None

    def set(self, match):
        self.date = match.group('date')
        self.time = match.group('time')
        self.ms = int(match.group('ms'))
        self.level = match.group('level')
        self.thread = match.group('thread')
        self.logger = match.group('logger')
        self.infos = [match.group('info')]
        self.type = ''
        self.change = ''
        self.patchset = ''
        self.change_item = ''
        self.queue = ''
        self.pipeline = ''
        self.project = ''
        self.queue_item = ''

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
                self.type = reg['type']
                {
                    'adding to pipeline':
                        self._handle_type_adding_to_pipeline,
                    'adding to queue':
                        self._handle_type_adding_to_queue,
                    'remove from queue':
                        self._handle_type_remove_from_queue,
                    'remove item':
                        self._handle_type_remove_item,
                    'remove for replace':
                        self._handle_type_remove_for_replace,
                    'remove for abandon':
                        self._handle_type_remove_for_abandon,
                    'remove for dequeue command':
                        self._handle_type_remove_dequeue_command,
                    'remove for cannot merge':
                        self._handle_type_cannot_merge,
                    'report result':
                        self._handle_type_report_result,
                    'launch job':
                        self._handle_type_launch_job,
                    'prepare ref':
                        self._handle_type_prepare_ref,
                    'cancel job':
                        self._handle_type_cancel_job,
                    'resetting for nnfi':
                        self._handle_type_resetting_for_nnfi,
                    'resetting for not merge':
                        self. _handle_type_resetting_for_not_merge

                }[self.type](m)

                print('{} {}.{} {} [{}] {}'.format(
                    self.date, self.time, self.ms,
                    self.level, self.type, self.logger))
                for info in self.infos:
                    print('-->{}'.format(info))
                break

    def _handle_type_adding_to_pipeline(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.pipeline = m.group('pipeline')
        self.project = m.group('project')

    def _handle_type_adding_to_queue(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.pipeline = m.group('pipeline')
        self.queue = m.group('queue')

    def _handle_type_remove_from_queue(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.queue_item = m.group('queue_item')
        self.pipeline = m.group('pipeline')

    def _handle_type_remove_item(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.queue_item = m.group('queue_item')
        self.pipeline = m.group('pipeline')

    def _handle_type_remove_for_replace(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.pipeline = m.group('pipeline')
        self.queue_item = m.group('queue_item')

    def _handle_type_remove_for_abandon(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.queue_item = m.group('queue_item')
        self.pipeline = m.group('pipeline')

    def _handle_type_remove_dequeue_command(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.queue_item = m.group('queue_item')
        self.pipeline = m.group('pipeline')

    def _handle_type_cannot_merge(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.queue_item = m.group('queue_item')
        self.pipeline = m.group('pipeline')

    def _handle_type_report_result(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.queue_item = m.group('queue_item')
        self.pipeline = m.group('pipeline')

    def _handle_type_launch_job(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.queue_item = m.group('queue_item')
        self.pipeline = m.group('pipeline')

    def _handle_type_prepare_ref(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.queue_item = m.group('queue_item')
        self.pipeline = m.group('pipeline')

    def _handle_type_cancel_job(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.queue_item = m.group('queue_item')
        self.pipeline = m.group('pipeline')

    def _handle_type_resetting_for_nnfi(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.pipeline = m.group('pipeline')

    def _handle_type_resetting_for_not_merge(self, m):
        self.change = m.group('change')
        self.patchset = m.group('patchset')
        self.change_item = m.group('item')
        self.pipeline = m.group('pipeline')


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
        obj = LogAction(
            datetime=udt.datetime,
            level=ll.level,
            thread_id=ll.thread,
            logger=ll.logger,
            type=ll.type,
            change=int(ll.change),
            patchset=int(ll.patchset),
            queue=ll.queue,
            pipeline=ll.pipeline,
            project=ll.project,
            change_item=ll.change_item,
            queue_item=ll.queue_item,
            text=text
        )
        self.session.add(obj)
        self.session.commit()


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
    print log_line


def _main(log_path, db_str):
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


if __name__ == '__main__':
    try:
        fire.Fire(_main)
    except Exception as e:
        print('Exception: {}'.format(str(e)))
        traceback.print_exc()
        sys.exit(2)
