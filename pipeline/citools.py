#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""Add CITOOLS path to sys.path automatically."""

import os
import sys

_citools_path = ''


def _add_path():
    _path = os.path.realpath(os.path.join(
        os.path.split(os.path.realpath(__file__))[0], "../CITOOLS"))
    sys.path.append(_path)
    return _path


def print_path():
    """
    Print path of citools.

    This function can be used for module not ref warning.
    """
    print 'Added', _citools_path, 'in sys.path. '


_citools_path = _add_path()
