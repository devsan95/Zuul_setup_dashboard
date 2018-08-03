#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

"""A module manipulating properties files."""

import ConfigParser
import os


NoOptionError = ConfigParser.NoOptionError
NoSectionError = ConfigParser.NoSectionError


class ConfigTool(object):
    """
    A class that read properties files.

    Example:
        1. Static way
        Read direct from file, use file name, section name and key name as
        input parameter.

            import api.config
            value = api.config.ConfigTool.get_config('filename',
                                                     'section', 'key')

        2. Use as an Object
        Create an object of this class,
        and use the object to load config files.
        Then you can read option and value as your load priority.
        Config file loaded last will be searched first.

            import api.config
            config = api.config.ConfigTool()
            config.load('file1')
            config.load('file2')
            value = config.get('section', 'key')

    """

    _config_dict = {}
    _config_path = os.path.realpath(os.path.join(
        os.path.split(os.path.realpath(__file__))[0],
        '../../CICONF/properties'))

    def __init__(self):
        self._load_list = []

    @classmethod
    def _get_normal_path(cls, path, absolute=False):
        file_path = path
        if not absolute:
            file_path = os.path.join(cls._config_path,
                                     file_path + '.properties')
        ret_path = os.path.normpath(file_path)
        return ret_path

    def load(self, filename, absolute=False):
        """
        Load config file, and mark the file as the first priority.

        Args:
            filename(str): the name of the file to load.
            absolute(bool): if the path is absolute or not

        Returns:
            ConfigParser.ConfigParser: a ConfigParser object that loaded the
            properties file.

        """
        parser = self._load_config(filename, absolute)
        self._load_list.insert(0, self._get_normal_path(filename, absolute))
        return parser

    def get(self, section, key, raw=False, vars=None):
        """
        Get value from properties files as the load order.

        Args:
            section(str): section of the value.
            key(str): key of the value.
            raw(bool): same as the same name parameter in ConfigParser.
            vars(dict): same as the same name parameter in ConfigParser.

        Returns:
            str: the value you want to get.
        """
        last_exception = None
        for filename in self._load_list:
            try:
                return self.get_config(filename, section,
                                       key, raw, vars, absolute=True)
            except Exception as e:
                last_exception = e
        if last_exception:
            raise last_exception

    def get_dict(self, section, **kwargs):
        """
        Get dict of a section from properties files as the load order.

        Args:
            section(str): section to get.
            **kwargs: other parameters needed to pass to ConfigParser.

        Returns:
            dict: the dict you want to get.
        """
        last_exception = None
        for filename in self._load_list:
            try:
                return self.get_config_section(filename, section,
                                               absolute=True, **kwargs)
            except Exception as e:
                last_exception = e
        if last_exception:
            raise last_exception

    @classmethod
    def _load_config(cls, filename, absolute=False):
        file_path = cls._get_normal_path(filename, absolute)
        if file_path in cls._config_dict:
            return cls._config_dict[file_path]
        else:
            parser = ConfigParser.ConfigParser()

            read_list = parser.read(file_path)
            if not read_list:
                raise Exception("Can't find the file. ")
                # TODO Xie Use more specific exception
            cls._config_dict[file_path] = parser
            # print 'Loaded %s. Display contents: ' % filename
            # print 'Sections are:'
            # list = parser.sections()
            # print list
            # print 'Items are:'
            # for sect in list:
            #     items = parser.items(sect)
            #     print sect, ': ', items
            return parser

    @classmethod
    def get_config(cls, filename, section, key,
                   raw=False, vars=None, absolute=False):
        """
        Get value from properties file you input.

        Args:
            filename(str): the name of the file you want to search.
            section(str): section of the value.
            key(str): key of the value.
            raw(bool): same as the same name parameter in ConfigParser.
            vars(dict): same as the same name parameter in ConfigParser.
            absolute(bool): if the filename is absolute or not

        Returns:
            str: the value you want to get.
        """
        parser = cls._load_config(filename, absolute)
        return parser.get(section, key, raw, vars)

    @classmethod
    def get_config_section(cls, filename, section, absolute=False, **kwargs):
        """
        Get a dict of a section from properties file you input.

        Args:
            filename(str): the name of the file you want to search.
            section(str): section of the value.
            absolute(str): if the filename is absolute or relative
            **kwargs: other parameters needed to pass to ConfigParse.

        Returns:
            dict: the dict you want to get.
        """
        parser = cls._load_config(filename, absolute, **kwargs)
        return dict(parser.items(section, **kwargs))


def get_config_path():
    _config_path = os.path.realpath(os.path.join(
        os.path.split(os.path.realpath(__file__))[0],
        '../../CICONF/'))
    return _config_path
