#! /usr/bin/env python2.7
# -*- coding:utf8 -*-
# Copyright 2018 Nokia
# Copyright 2018 Shawn Zhiqi Xie
# Copyright 2018 HZ 5G SCM Team

"""
A module to do operations for integration change.
"""

import json
import re


class IntegrationChange(object):
    def __init__(self, rest, change_no):
        self.rest = rest
        self.change_no = change_no
        self.info = None
        self.detailed_info = None
        self.refresh_info()
        self.refresh_detailed_info()

    def refresh_info(self):
        self.info = self.rest.get_ticket(self.change_no,
                                         ['CURRENT_REVISION',
                                          'DOWNLOAD_COMMANDS',
                                          'LABELS'])

    def refresh_detailed_info(self):
        self.detailed_info = self.rest.get_detailed_ticket(self.change_no)

    def get_info(self):
        return self.info

    def get_detailed_info(self):
        return self.detailed_info

    def get_label_status(self, label):
        label_info = self.info.get('labels')
        if label_info:
            label_dict = label_info.get(label)
            if label_dict:
                if 'blocking' in label_dict:
                    return 'blocking'
                elif 'rejected' in label_dict:
                    return 'rejected'
                elif 'approved' in label_dict:
                    return 'approved'
        return None

    def review(self, comment, label_dict):
        self.rest.review_ticket(self.change_no, comment, label_dict)


class RootChange(IntegrationChange):
    def __init__(self, rest, change_no):
        super(RootChange, self).__init__(rest, change_no)

    def get_all_changes_by_comments(self, with_root=False):
        root_change = self.change_no
        component_changes, manager_change = \
            self.get_components_changes_by_comments()
        submodule_changes = self.get_submodule_changes_by_comments()
        change_set = set()

        if with_root:
            change_set.add(root_change)

        if component_changes:
            for change in component_changes:
                change_set.add(change)

        if manager_change:
            change_set.add(manager_change)

        if submodule_changes:
            if isinstance(submodule_changes, list):
                for submodule_ in submodule_changes:
                    if len(submodule_) > 1:
                        change_set.add(submodule_[1])

        return list(change_set)

    def get_components_changes_by_comments(self):
        json_re = re.compile(r'Tickets-List: ({.*})')
        for msg in reversed(self.detailed_info['messages']):
            msg = msg['message']
            result_list = json_re.findall(msg)
            if len(result_list) > 0:
                change_list = json.loads(result_list[0])
                return change_list.get('tickets'), change_list.get('manager')
        return None, None

    def get_submodule_changes_by_comments(self):
        json_re = re.compile(r'Submodules-List: (.*)')
        for msg in reversed(self.detailed_info['messages']):
            result_list = json_re.findall(msg['message'])
            if len(result_list) > 0:
                return json.loads(result_list[-1])
        return None


class ManageChange(IntegrationChange):
    def __init__(self, rest, change_no):
        super(ManageChange, self).__init__(rest, change_no)
