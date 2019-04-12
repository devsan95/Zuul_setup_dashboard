#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
this is a scripts generate all types of tool moudels together
it is used for scripts which using tempalted html/json
all used function in tool modules accept dict as parameter
"""


import arrow


def get_date_only(pdict):
    print('pdict is {}'.format(pdict))
    current_datetime = arrow.now().floor('second').isoformat('~')
    current_date, current_time = current_datetime.split('~')
    return current_date


def get_time_only(pdict):
    print('pdict is {}'.format(pdict))
    current_datetime = arrow.now().floor('second').isoformat('~')
    current_date, current_time = current_datetime.split('~')
    return current_time


def get_date_time(pdict):
    print('pdict is {}'.format(pdict))
    return arrow.now().floor('second').isoformat('~')
