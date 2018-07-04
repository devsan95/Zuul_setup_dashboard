#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

from random import randint
import argparse
import sys
import time
import traceback


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Input the pipeline, and success rate')

    parser.add_argument('--pipeline', type=str, dest='pipeline',
                        help='The pipeline that job belong to')
    parser.add_argument('--rate', type=int, dest='rate',
                        help='The pipeline that job belong to')

    args = parser.parse_args()
    return vars(args)


def is_failed():
    if randint(0, 60) < 2:
        return True
    else:
        return False


def sleep_time():
    # 20% 10s ~ 59s
    if randint(0, 10) > 7:
        return randint(10, 60)
    else:
        return randint(120, 540)


def _main(**kwargs):
    pipeline = kwargs["pipeline"]

    # sleep
    sleep_seconds = sleep_time()
    print("sleep {} s".format(sleep_seconds))
    time.sleep(sleep_seconds)

    # only gate pipeline job will fail
    if pipeline == "gate":
        if is_failed():
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
