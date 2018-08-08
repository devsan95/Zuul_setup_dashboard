import re
import sys
import traceback

import arrow
import fire


reg_log = re.compile(
    r'(?P<date>\d\d\d\d-\d\d-\d\d) '
    r'(?P<time>\d\d:\d\d:\d\d),(?P<ms>\d\d\d) '
    r'(?P<level>\w*) '
    r'((?P<thread>\d*) )?'
    r'((?P<logger>[^:]*): )?(?P<info>.*)')

reg_begin = re.compile(r'Function <(?P<name>.*)> begins\.')
reg_end = re.compile(
    r'Function <(?P<name>.*)> took (?P<cost>.*) ms to finish\.')
reg_handler_begin = re.compile(r'Run handler awake')
reg_handler_end = re.compile(r'Run handler sleeping')
reg_ssh_end = re.compile(r'Connection took (?P<cost>\d*\.\d*)')


class TimePoint(object):
    def __init__(self):
        self.type = None
        self.time = None
        self.name = None
        self.thread = None
        self.cost = None

    def __repr__(self):
        return '<TimePoint name {x.name}, ' \
               'type {x.type}, ' \
               'thread {x.thread}, ' \
               'cost {x.cost}, ' \
               'time {x.time}>'.format(x=self)


class TimeBlock(object):
    def __init__(self):
        self.begin_time = None
        self.end_time = None
        self.name = None
        self.thread = None
        self.cost = None


def parse_begin(info):
    m = reg_begin.match(info)
    if m:
        tp = TimePoint()
        tp.type = 'begin'
        tp.name = m.group('name')
        return tp
    else:
        return None


def parse_end(info):
    m = reg_end.match(info)
    if m:
        tp = TimePoint()
        tp.type = 'end'
        tp.name = m.group('name')
        tp.cost = float(m.group('cost'))
        return tp
    else:
        return None


def parse_handler_begin(info):
    m = reg_handler_begin.match(info)
    if m:
        tp = TimePoint()
        tp.type = 'begin'
        tp.name = 'Scheduler'
        return tp
    else:
        return None


def parse_handler_end(info):
    m = reg_handler_end.match(info)
    if m:
        tp = TimePoint()
        tp.type = 'end'
        tp.name = 'Scheduler'
        return tp
    else:
        return None


def parse_ssh_end(info):
    m = reg_ssh_end.match(info)
    if m:
        tp = TimePoint()
        tp.type = 'block'
        tp.name = 'ssh'
        tp.cost = float(m.group('cost')) * 1000
        return tp
    else:
        return None


class LogLine(object):
    def __init__(self):
        self.date = None
        self.time = None
        self.ms = None
        self.level = None
        self.thread = None
        self.logger = None
        self.infos = None
        self.utc = None

    def set(self, match):
        self.date = match.group('date')
        self.time = match.group('time')
        self.ms = int(match.group('ms'))
        self.level = match.group('level')
        self.thread = match.group('thread')
        self.logger = match.group('logger')
        self.infos = [match.group('info')]

        timestr = '{}T{}.{:0>3}'.format(
            self.date,
            self.time,
            self.ms
        )
        adt = arrow.get(timestr)
        adt = adt.replace(tzinfo='America/New_York')
        self.utc = adt.to('utc')

    def append(self, string):
        if self.infos:
            self.infos.append(string)


class ParseResult(object):
    parse_list = [
        parse_begin,
        parse_end,
        parse_handler_begin,
        parse_handler_end,
        parse_ssh_end
    ]

    def __init__(self, threshold=0):
        self.result = {}
        self.temp_result = {}
        self.meet_begin = False
        self.main_thread = None
        self.cycle_stack = 0
        self.cycle_threshold = threshold

    def parse(self, log_line):
        if not log_line.infos:
            return
        info = log_line.infos[0]
        thread = log_line.thread

        for func in self.parse_list:
            ret = func(info)
            if ret:
                break
        if ret:
            ret.thread = thread
            ret.time = log_line.utc
            self.save_parse_result(ret)

    def save_parse_result(self, pr):
        if pr.name == 'Scheduler':
            if pr.type == 'begin':
                self.save_result_to_temp(pr)
                self.meet_begin = True
                self.main_thread = pr.thread
                print('Begin meet')
            elif pr.type == 'end':
                self.save_result_to_temp(pr)
                self.meet_begin = False
                if self.cycle_threshold > 0 and pr.cost:
                    if self.cycle_stack + pr.cost > self.cycle_threshold:
                        raise Exception('{} exceed thread {}'.format(
                            self.cycle_stack + pr.cost, self.cycle_threshold))
                    self.cycle_stack += pr.cost
                self.save_result()
                print('End meet')
        else:
            if self.meet_begin:
                self.save_result_to_temp(pr)
            else:
                print('No meet begin, throw {}'.format(pr))

    def save_result_to_temp(self, pr):
        if pr.thread not in self.temp_result:
            self.temp_result[pr.thread] = {}
        if pr.name not in self.temp_result[pr.thread]:
            self.temp_result[pr.thread][pr.name] = {}

        storage = self.temp_result[pr.thread][pr.name]
        if 'last' not in storage:
            storage['last'] = None
        if 'blocks' not in storage:
            storage['blocks'] = []

        if pr.type == 'begin':
            storage['last'] = pr
        elif pr.type == 'end':
            if not storage['last']:
                print('No last, throw {}'.format(pr))
            else:
                block = TimeBlock()
                block.name = pr.name
                block.begin_time = storage['last'].time
                block.end_time = pr.time
                block.thread = pr.thread
                block.cost = pr.cost
                if block.cost is None:
                    block.cost = block.end_time - block.begin_time
                    block.cost = block.cost.total_seconds() * 1000
                    pr.cost = block.cost
                storage['blocks'].append(block)
        elif pr.type == 'block':
            block = TimeBlock()
            block.name = pr.name
            block.end_time = pr.time
            block.thread = pr.thread
            block.cost = pr.cost
            storage['blocks'].append(block)

    def save_result(self):
        for thread in self.temp_result:
            if thread not in self.result:
                self.result[thread] = {}
            for name in self.temp_result[thread]:
                if name not in self.result[thread]:
                    self.result[thread][name] = []

                self.result[thread][name] = \
                    self.result[thread][name] + self.temp_result[thread][name]['blocks']
                self.temp_result[thread][name]['blocks'] = []
                self.temp_result[thread][name]['last'] = None


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


def main(log_path, threshold=0):
    try:
        parse_result = ParseResult(threshold)
        log_line = LogLine()
        try:
            with open(log_path) as f:
                lines = f.readlines()
                for line in lines:
                    m = reg_log.match(line)
                    if m:
                        # Parse Old
                        parse_result.parse(log_line)
                        # Set New
                        log_line.set(m)
                    else:
                        log_line.append(line)
        except Exception as e:
            print('Exception:\n{}'.format(e))
        result = parse_result.result
        write_path = log_path + '.result.log'
        with open(write_path, 'w') as f:
            for thread in result:
                print('------------------------------\nThread: {}'.format(thread))
                f.write('------------------------------\nThread: {}\n'.format(thread))
                for name in result[thread]:
                    print(name)
                    f.write('{}:\n'.format(name))
                    list_f = [float(x.cost) for x in result[thread][name]]
                    list_r = [str(int(x.cost)) for x in result[thread][name]]
                    sum_f = sum(list_f)
                    average_f = sum_f / len(list_f)
                    print(','.join(list_r))
                    print('Sum is {} ms, average is {} ms'.format(sum_f, average_f))
                    f.write(','.join(list_r))
                    f.write('\n')
    except Exception as ex:
        print('Exception occurs:')
        print(ex)
        raise ex


if __name__ == '__main__':
    try:
        fire.Fire(main)
    except Exception as e:
        print('Exception: {}'.format(str(e)))
        traceback.print_exc()
        sys.exit(2)
