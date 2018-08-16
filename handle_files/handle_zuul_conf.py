#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import sys
import traceback
import argparse
from file_handler import FileHandler


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Update zuul.conf')
    parser.add_argument('--action', type=str, dest='action',
                        help='disable or enable')

    parser.add_argument('--path', type=str, dest='path',
                        default="/var/fpwork/zuul_backup/zuul_prod/etc/zuul.conf",
                        help='The path of zuul.conf, default'
                             ' is /var/fpwork/zuul_backup/zuul_prod/etc/zuul.conf')
    args = parser.parse_args()
    return vars(args)


def disable(path):
    print "disable start!"
    handler = FileHandler(path)
    handler.set_section_value("gerrit", {})
    print "disable done!"


def enable(path):
    handler = FileHandler(path)
    gerrit_setting = {
        'driver': 'gerrit',
        'server': 'gerrit.ext.net.nokia.com',
        'port': '29418',
        'baseurl': 'https://gerrit.ext.net.nokia.com/gerrit',
        'user': 'scmtaci',
        'sshkey': '/etc/zuul/scmta.id_rsa',
        'timeout': '20'
    }
    handler.set_section_value("gerrit", gerrit_setting)


def _main(**kwargs):
    action = kwargs['action']
    path = kwargs['path']

    print("action is {}, path is {}".format(action, path))
    if action.lower() == "disable":
        disable(path)
    elif action.lower() == "enable":
        enable(path)


if __name__ == '__main__':
    try:
        args = _parse_args()

        _main(**args)

    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
