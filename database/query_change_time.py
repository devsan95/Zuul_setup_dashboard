import arrow
import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from model import get_log_duration_model

LogDuration = get_log_duration_model('t_log_duration')


def mean(numbers):
    return float(sum(numbers)) / max(len(numbers), 1)


class ChangeTime(object):
    def __init__(self):
        self.change_set = None
        self.start_time = 0
        self.end_time = 0
        self.window_time = 0
        self.pre_merge_time = 0
        self.merge_time = 0
        self.pre_launch_time = 0
        self.launch_time = 0
        self.job_time = 0
        self.total_time = 0
        self.total_reschedule_time = 0
        self.average_reschedule_time = 0
        self.reschedule_times = 0
        self.count = 0
        self.status = ""
        self.result = 0
        self.reschedule_time = []

    def to_line(self):
        ret_str = "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}".format(
            self.change_set, self.start_time, self.end_time, self.window_time,
            self.merge_time, self.pre_launch_time, self.launch_time,
            self.job_time, self.total_time)
        if self.reschedule_time:
            sums = sum(self.reschedule_time)
            average = sums / len(self.reschedule_time)
            self.total_reschedule_time = sums
            self.average_reschedule_time = average
            self.reschedule_times = len(self.reschedule_time)
            ret_str += '\t{}\t{}\t{}'.format(sums, self.reschedule_times, average)

        else:
            ret_str += '\t0\t0\t0'
        ret_str += '\t{}'.format(self.start_time.strftime('%Y-%m-%d'))
        ret_str += '\t{}'.format(self.status)
        if self.reschedule_time:
            ret_str += '\t{}'.format('\t'.join([str(x) for x in self.reschedule_time]))
        return ret_str

    def to_line_all(self):
        ret_str = '{}'.format(self.start_time.strftime('%Y-%m-%d'))
        ret_str += "\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}".format(
            self.start_time, self.end_time, self.window_time,
            self.merge_time, self.pre_launch_time, self.launch_time,
            self.job_time, self.total_time)

        ret_str += '\t{}\t{}\t{}'.format(self.total_reschedule_time, self.reschedule_times, self.average_reschedule_time)
        ret_str += '\t{}'.format(self.count)
        ret_str += '\t{}'.format(self.status)
        return ret_str


class DbHandler(object):
    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def init_db(self):
        pass

    def get_change_tuple_by_time(self, begin_time, end_time):
        ret_set = set()
        q = self.session.query(
            LogDuration.changeset,
            LogDuration.queue_item).filter(
                LogDuration.start_time >= begin_time.datetime,
                LogDuration.finish_time <= end_time.datetime,
                LogDuration.kind == 'gate',
                LogDuration.project == 'MN/5G/NB/gnb')
        for item in q.all():
            ret_set.add(tuple(item))
        return ret_set

    def process_tuple(self, one_tuple):
        change_time = ChangeTime()
        q = self.session.query(LogDuration).filter(
            LogDuration.queue_item == one_tuple[1],
            LogDuration.changeset == one_tuple[0],
            LogDuration.kind == 'gate').order_by(
            sa.asc(LogDuration.start_time))
        result = []
        for i in q.all():
            result.append(i)
        if not result:
            raise Exception('Find no entry for {}'.format(one_tuple))
        change_time.status = result[-1].status
        change_time.result = result[-1].result
        change_time.change_set = one_tuple[0]
        change_time.start_time = result[0].start_time
        change_time.end_time = result[-1].finish_time
        change_time.total_time = (result[-1].finish_time - result[0].start_time).total_seconds() * 1000
        if len(result) == 1 and result[0].merge_time:
            change_time.window_time = (result[0].merge_time - result[0].start_time).total_seconds() * 1000

        else:

            window1 = 0
            window2 = 0

            for i in range(len(result) - 1):
                if not result[i].merge_time:
                    window1 += (result[i].finish_time - result[i].start_time).total_seconds() * 1000
            if result[-1].merge_time:
                window2 = (result[-1].merge_time - result[-1].start_time).total_seconds() * 1000
            else:
                window2 = (result[-1].finish_time - result[-1].start_time).total_seconds() * 1000

            change_time.window_time = window1 + window2

        if result[-1].merge_time:
            if result[-1].merged_time:
                change_time.merge_time = (result[-1].merged_time - result[-1].merge_time).total_seconds() * 1000
                if result[-1].launch_time:
                    change_time.pre_launch_time = (result[-1].launch_time - result[-1].merged_time).total_seconds() * 1000
                    if result[-1].launched_time:
                        change_time.launch_time = (result[-1].launched_time - result[-1].launch_time).total_seconds() * 1000
                        change_time.job_time = (result[-1].finish_time - result[-1].launched_time).total_seconds() * 1000
        if len(result) > 1:
            for i in range(len(result) - 1):
                if result[i].status not in ['resetting for nnfi', 'resetting for not merge']:
                    print result[i].status, one_tuple
                    raise Exception()
                if result[i].merge_time:
                    change_time.reschedule_time.append((result[i].finish_time - result[i].start_time).total_seconds() * 1000)
        return change_time

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def run(db_url, start_date, end_date, start_hour, end_hour, output=None, write_line=False, write_summary=False):
    try:
        if output:
            output_file = open(output, 'w')
        db = DbHandler(db_url)
        start_time = arrow.get(start_date)
        end_time = arrow.get(end_date)
        current_time = start_time
        while True:
            if current_time.weekday() == 5 or current_time.weekday() == 6:
                current_time = current_time.replace(days=1)
                continue
            begin_time = current_time.replace(hour=int(start_hour))
            finish_time = current_time.replace(hour=int(end_hour))
            if end_hour == 0:
                finish_time = finish_time.replace(days=1)
            output_lines = []
            print('From {} to {}'.format(begin_time, finish_time))
            change_tuple = db.get_change_tuple_by_time(begin_time, finish_time)
            for one_item in change_tuple:
                change_time = db.process_tuple(one_item)
                if output_file and write_line:
                    output_file.write(change_time.to_line())
                    output_file.write('\n')
                change_time.to_line()
                output_lines.append(change_time)
            total_change_time = ChangeTime()
            if output_lines:
                total_change_time.start_time = min([x.start_time for x in output_lines])
                total_change_time.end_time = max([x.end_time for x in output_lines])
                total_change_time.window_time = mean([x.window_time for x in output_lines if x.window_time > 0])
                total_change_time.pre_merge_time = mean([x.pre_merge_time for x in output_lines if x.pre_merge_time > 0])
                total_change_time.merge_time = mean([x.merge_time for x in output_lines if x.merge_time > 0])
                total_change_time.pre_launch_time = mean([x.pre_launch_time for x in output_lines if x.pre_launch_time > 0])
                total_change_time.launch_time = mean([x.launch_time for x in output_lines if x.launch_time > 0])
                total_change_time.job_time = mean([x.job_time for x in output_lines if x.job_time > 0])
                total_change_time.total_time = mean([x.total_time for x in output_lines if x.total_time > 0])
                total_change_time.total_reschedule_time = mean([x.total_reschedule_time for x in output_lines if x.total_reschedule_time >= 0])
                total_change_time.average_reschedule_time = mean([x.average_reschedule_time for x in output_lines if x.average_reschedule_time >= 0])
                total_change_time.reschedule_times = mean([x.reschedule_times for x in output_lines if x.reschedule_times >= 0])
                total_change_time.count = len(output_lines)
                total_change_time.status = len([x for x in output_lines if x.result == 1])
                if output_file and write_summary:
                    output_file.write(total_change_time.to_line_all())
                    output_file.write('\n')
                print total_change_time.to_line_all()
            current_time = current_time.replace(days=1)
            if current_time > end_time:
                break
    except Exception as e:
        raise e
    finally:
        if output_file:
            output_file.close()


if __name__ == '__main__':
    fire.Fire(run)
