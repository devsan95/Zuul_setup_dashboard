#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

from __future__ import print_function

import time
from functools import partial as fn


class classpartialmethod(fn):
    def __get__(self, instance, owner):
        if instance is None:
            return self
        return fn(self.func, instance,
                  *(self.args or ()), **(self.keywords or {}))


cfn = classpartialmethod


# Define Exception class for retry
class RetryException(Exception):
    u_str = "Exception ({}) raised after {} tries."

    def __init__(self, exp, max_retry):
        self.exp = exp
        self.max_retry = max_retry

    def __unicode__(self):
        return self.u_str.format(self.exp, self.max_retry)

    def __str__(self):
        return self.__unicode__()


# Define retry util function
def retry_func(func, max_retry=10, interval=0):
    """
    @param func: The function that needs to be retry
    @param max_retry: Maximum retry of `func` function, default is `10`
    @param interval: Interval of retry, default is `0`
    @return: func
    @raise: RetryException if retries exceeded than max_retry
    """
    _exception = None
    _func_name = str(func)
    if isinstance(func, fn):
        _func_name = str(func.func)

    for retry_time in range(1, max_retry + 1):
        try:
            return func()
        except Exception as e:
            _exception = e
            print('Failed to call {}, in retry({}/{})'.format(
                _func_name, retry_time, max_retry))
            print('Exception {}'.format(e))
            if interval:
                time.sleep(interval)
    else:
        raise RetryException(_exception, max_retry)
