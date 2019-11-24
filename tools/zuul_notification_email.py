#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2019/11/15 15:13
# @Author  : irin.zheng@nokia.com
# @Site    : HZ
# @File    : zuul_notification_email.py
# @Software: PyCharm

import argparse
import easy_mail


def arguments():
    """
    accept parameters from outside
    :return:dict{params}
    """
    parse = argparse.ArgumentParser()
    parse.add_argument('--resultFile', '-r', required=True, help='restart result information file')
    return parse.parse_args()


if __name__ == '__main__':
    args = arguments()
    result_file = args.resultFile
    isRestartSuccess = True
    host_server = ""
    with open(result_file, 'r') as f:
        message = f.read()
        lines = f.readlines()
        for line in lines:
            if "Host" in line:
                host_server = line.split(":")[1].strip().split("<")[0]
            if "Failed" in line:
                isRestartSuccess = False
                break
    title = "Zuul service on {} restart success after reboot".format(host_server)
    easy_mail.mail(title, message, subtype="html")
