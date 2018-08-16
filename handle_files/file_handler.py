#! /usr/bin/env python2.7
# -*- coding:utf8 -*-


from configobj import ConfigObj


class FileHandler:
    def __init__(self, path):
        self.config = ConfigObj(path)

    def set_section_value(self, section_name, value_dict):
        self.config[section_name] = value_dict
        self.config.write()

    def set_option_value(self, section_name, option_name, value):
        self.config[section_name][option_name] = value
        self.config.write()

    def get_sections(self):
        return self.config.sections

    def get_options(self, section_name):
        return self.config[section_name]

    def add_section(self, section_name, value_dict={}):
        self.config.sections.append(section_name)
        self.config[section_name] = value_dict
        self.config.write()
