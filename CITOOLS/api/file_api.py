#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
A module to do file operation.
"""

import os
import shutil
import tempfile


def save_file(content, path, binary=False):
    """
    Save content to a file
    Args:
        content: content to save
        path: path of the file
        binary: whether to save the file as binary or text

    Returns:
        None
    """
    file_dir = get_file_dir(path)
    if not os.path.exists(file_dir):
        os.makedirs(file_dir)

    if binary:
        file_mode = 'wb'
    else:
        file_mode = 'w'

    with open(path, file_mode) as f:
        f.write(content)


def get_exec_dir():
    """
    Get the script's directory
    Returns:
        str: the script's directory
    """
    return os.path.abspath(os.path.dirname(__file__))


def get_exec_path():
    """
    Get the script's path
    Returns:
        str: the script's path

    """
    return os.path.realpath(__file__)


def get_file_dir(path):
    """
    Get the directory of a file
    Args:
        path: path to the file

    Returns:
        str: directory of the file

    """
    return os.path.abspath(os.path.dirname(path))


def get_file_size(path):
    """
    Get the size of a file
    Args:
        path: path to the file

    Returns:
        size of the file

    """
    return os.path.getsize(path)


def list_directory(path, is_relative=False):
    """
    list all contents of a directory
    Args:
        path: path to the directory
        is_relative: whether the output is absolute or relative

    Returns:
        list of the contents in the directory
    """
    file_set = set()
    for root, _, files in os.walk(path):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            if is_relative:
                file_path = os.path.relpath(file_path, path)
            file_set.add(file_path)
    return list(file_set)


def make_dirs_for_file(file_path):
    """
    Make needed directories of a file
    Args:
        file_path: path to the file

    Returns:
        None
    """
    dir_path = os.path.dirname(file_path)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


class TempFolder(object):
    def __init__(self):
        self._path = tempfile.mkdtemp(prefix='layout_test_')
        print('Create Temp Folder: {}'.format(self._path))

    def get_directory(self, sub_folder='.'):
        new_path = os.path.realpath(os.path.join(self._path, sub_folder))
        if os.path.normpath(new_path) == os.path.normpath('/'):
            raise Exception('Error, path is too dangerous.')
        return new_path

    def __del__(self):
        shutil.rmtree(self._path, True)
        print('Remove Temp Folder: {}'.format(self._path))
