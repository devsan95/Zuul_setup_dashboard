#! /usr/bin/env python2.7
# -*- coding:utf8 -*-


def strip_begin(text, prefix):
    if not text.startswith(prefix):
        return text
    return text[len(prefix):]
