#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import json
import numbers

import requests
from xml.etree import cElementTree as ElementTree


class WftAuth(object):
    def __init__(self, access_key):
        self.access_key = None
        self.set_access_key(access_key)

    def set_access_key(self, access_key):
        self.access_key = access_key

    def get_auth(self):
        return {'access_key': self.access_key}

    def get_access_key(self):
        return self.access_key


class WftBuildQuery(object):
    def __init__(self, auth):
        self.auth = None
        self.set_auth(auth)

        self.columns = []
        self.filters = []
        self.page = None
        self.items = None
        self.sorting_field = None
        self.sorting_direction = None
        self.group_by = None
        self.group_by_processor = None

        self.reset()

        self.operations = [
            'eq', 'not_eq', 'eq_any', 'cont', 'not_cont', 'cont_any',
            'matches_regexp', 'does_not_match_regexp', 'lt', 'lteq', 'gt',
            'gteq', 'start', 'not_start', 'end', 'not_end', 'date_between',
            'date_between_relative', 'not_date_between',
            'not_date_between_relative'
        ]
        self.sorting_directions = ['ASC', 'DESC']

    def reset(self):
        self.reset_columns()
        self.reset_filters()
        self.page = 1
        self.items = '20'
        self.sorting_field = 'baseline'
        self.sorting_direction = 'DESC'
        self.group_by = ''
        self.group_by_processor = ''

    def set_auth(self, auth):
        self.auth = auth

    def reset_columns(self):
        self.columns = [
            'deliverer.project.full_path', 'deliverer.title', 'baseline',
            'branch.title', 'state', 'planned_delivery_date', 'common_links',
            'compare_link', 'id', 'created_at'
        ]

    def set_columns(self, columns):
        if not isinstance(columns, list):
            raise Exception("columns type wrong, please input list.")
        self.columns = columns

    def reset_filters(self):
        self.filters = []

    def _filter_param_check(self, column, operation, value):
        if operation not in self.operations:
            raise Exception(
                'operation wrong, '
                'please use operations in {}'.format(self.operations))

        if not isinstance(column, basestring):
            raise Exception(
                'column wrong, '
                'column should be a string')

        if (not isinstance(value, basestring)) and \
           (not isinstance(value, list)):
            raise Exception(
                'value wrong, '
                'value should be a string or a list')

    def _find_filter(self, column, operation, value):
        for item in self.filters:
            if item['column'] == column and \
               item['operation'] == operation and \
               item['value'] == value:
                return item
        return None

    def add_filter(self, column, operation, value):
        self._filter_param_check(column, operation, value)
        item = self._find_filter(column, operation, value)
        if not item:
            self.filters.append(
                {'column': column,
                 'operation': operation,
                 'value': value}
            )

    def remove_filter(self, column, operation, value):
        self._filter_param_check(column, operation, value)
        item = self._find_filter(column, operation, value)
        if item:
            self.filters.remove(item)

    def add_columns(self, column):
        if column not in self.columns:
            self.columns.append(column)

    def remove_columns(self, column):
        if column in self.columns:
            self.columns.remove(column)

    def set_result_number(self, number):
        if isinstance(number, numbers.Integral) and number > 0:
            self.items = str(number)
        else:
            raise Exception('number wrong, please input positive integer')

    def get_result_number(self):
        return int(self.items)

    def set_group_by(self, group=None, processor=None):
        if isinstance(group, basestring):
            self.group_by = group
        else:
            self.group_by = ''

        if isinstance(processor, basestring):
            self.group_by_processor = processor
        else:
            self.group_by_processor = ''

    def set_sorting(self, field=None, desc=True):
        if isinstance(field, basestring):
            self.sorting_field = field
        else:
            self.sorting_field = ''

        if desc:
            self.sorting_direction = 'DESC'
        else:
            self.sorting_field = 'ASC'

    def set_page(self, page):
        self.page = page

    def next_page(self):
        self.page += 1

    def previous_page(self):
        if self.page > 1:
            self.page -= 1

    def _gen_request_json(self):
        json_dict = {
            "page": str(self.page),
            "items": self.items,
            "sorting_field": self.sorting_field,
            "sorting_direction": self.sorting_direction,
            "group_by": self.group_by,
            "group_by_processor": self.group_by_processor,
            "columns": self.columns,
            "view_filters_attributes": {},
            "access_key": self.auth.get_access_key()
        }
        for i, filter_ in enumerate(self.filters):
            json_dict['view_filters_attributes'][i] = {
                "column": filter_['column'],
                "operation": filter_['operation'],
                "value": filter_['value']
            }
        return json.dumps(json_dict)

    def query(self, ssl_verify=False):
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        json_str = self._gen_request_json()
        response = \
            requests.get('https://wft.int.net.nokia.com:8091/api/v1/build.json',
                         headers=headers,
                         data=json_str,
                         verify=ssl_verify)
        if not response.ok:
            raise Exception('error {}, content: {}'.format(
                response.status_code, response.content))
        return json.loads(response.content)


class WftBuild(object):
    def __init__(self, xml):
        self.xml = xml
        self.tree = ElementTree.fromstring(self.xml)

    @classmethod
    def get_build(cls, baseline):
        response = \
            requests.get('https://wft.int.net.nokia.com/ext/'
                         'build_content/{}'.format(baseline),
                         verify=False)
        if not response.ok:
            raise Exception('Cannot get build xml')
        return cls(response.content)

    def traverse(self):
        self.print_children(self.tree, 0)

    @staticmethod
    def print_children(ele, indent):
        if isinstance(ele.text, basestring):
            text = ele.text.strip()
        else:
            text = ''
        print('{}{}<{}>{} {}'.format(' ' * indent,
                                     '└', ele.tag,
                                     text, ele.attrib,))
        for child in ele:
            WftBuild.print_children(child, indent + 2)

    def find_items(self, xpath):
        return self.tree.findall(xpath)
