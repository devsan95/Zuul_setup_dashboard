#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""Add CITOOLS path to sys.path automatically."""

import os
import sys


def _add_path():
    _path = os.path.realpath(os.path.join(
        os.path.split(os.path.realpath(__file__))[0], ".."))
    sys.path.append(_path)
    _path = os.path.realpath(os.path.join(
        os.path.split(os.path.realpath(__file__))[0], "."))
    sys.path.append(_path)


_add_path()
