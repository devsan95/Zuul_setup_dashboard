#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import traceback
import sys
import argparse


def _parse_args():
    parser = argparse.ArgumentParser(description='perform integration test')
    parser.add_argument('test_type', type=str,
                        help='type of integration test')
    parser.add_argument('base', type=int,
                        help='base')
    parser.add_argument('a', type=int,
                        help='a')
    parser.add_argument('b', type=int,
                        help='b')
    args = parser.parse_args()
    return vars(args)


def _main(test_type, base, a, b):
    if test_type == 'a':
        if (a + base) % 2 == 0:
            sys.exit(0)
    elif test_type == 'b':
        if (b + base) % 3 == 0:
            sys.exit(0)
    elif test_type == 'integration':
        if (a + b + base) % 4 == 0:
            sys.exit(0)
    else:
        raise Exception('Unknown test type.')
    sys.exit(1)


if __name__ == '__main__':
    try:
        param = _parse_args()
        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
