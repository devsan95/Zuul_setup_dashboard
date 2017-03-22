#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

""" A collection of functions relating to jenkins job operation. """

import subprocess
import os


def get_workspace(sub='.'):
    """
    Shortcut of get a sub directory of jenkins job workspace.
    If workspace is null (e.g. executed in shell),
    use current directory instead
    :return: a string of path
    """
    path = os.environ.get('WORKSPACE')
    if not path or not os.path.exists(path):
        path = os.curdir
    new_path = os.path.realpath(os.path.join(path, sub))
    return new_path


def run_cmd(cmd):
    """
    Run command in shell.
    :param cmd:  command to run
    :return:  null
    """
    print 'Running: ', cmd
    subprocess.check_call(cmd, shell=True)


def write_dict_to_properties(dict_env, output_file):
    """
    Write a dictionary to a env file.
    :param dict_env:  dictionary to write
    :param output_file:  full path of file to be written
    :return:  null
    """
    print 'Write dictionary: '
    print dict_env
    print 'To file: '
    print output_file

    with open(output_file, 'w') as out_file:
        for key, value in dict_env.items():
            out_file.write('%s="%s"\n' % (key, value))
