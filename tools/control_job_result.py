#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

from random import randint
import argparse
import sys
import time
import traceback


success_rate_dict = {
   "A": 80,
   "TakeAShower": 20,
   "SleepyDog": 90
}


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Input the pipeline, and success rate')

    parser.add_argument('--pipeline', type=str, dest='pipeline',
                        help='The pipeline that job belong to')
    parser.add_argument('--job', type=str, dest='job',
                        help='job name')

    args = parser.parse_args()
    return vars(args)


def is_failed(job_name):
    if job_name in success_rate_dict:
        print("Job {} success is {}".format(job_name, success_rate_dict[job_name][0]))
        return randint(0, 100) > success_rate_dict[job_name][0]
    else:
        return False


def sleep_time(pipeline):
    if pipeline == "gate":
        if randint(0, 10) > 7:
            return randint(10, 60)
        else:
            return randint(120, 540)
    else:
        return randint(10, 60)


def _main(**kwargs):
    pipeline = kwargs["pipeline"]
    job_name = kwargs["job"]

    # sleep
    sleep_seconds = sleep_time(pipeline)
    print("sleep {} s".format(sleep_seconds))
    time.sleep(sleep_seconds)

    # only gate pipeline job will fail
    if pipeline == "gate":
        if is_failed(job_name):
            sys.exit(1)
    else:
        pass


if __name__ == '__main__':
    try:
        args = _parse_args()

        _main(**args)

    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
