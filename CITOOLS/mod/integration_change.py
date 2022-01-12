#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
# Copyright 2018 Nokia
# Copyright 2018 Shawn Zhiqi Xie
# Copyright 2018 HZ 5G SCM Team

"""
A module to do operations for integration change.
"""

import json
import re

from mod import common_regex

com_name_reg = re.compile(r'\s+comp_name: ')
bb_version_reg = re.compile(r'\s+bb_version: ')
commit_ID_reg = re.compile(r'\s+commit-ID: ')
comp_reg = re.compile(r'  - COMP <(.*?)>')
fifi_reg = re.compile(r'%FIFI=(.*)')
create_feature = re.compile(r'create_feature_yaml=(.*)\b')
int_project_reg = re.compile(r'project: (.*)')
ecl_branch_reg = re.compile(r'ecl_branch: (.*)')
ecl_int_branch_reg = re.compile(r'ecl_int_branch: (.*)')
int_branch_reg = re.compile(r'int_branch: (.*)')
ric_reg = re.compile(r'  - RIC <([^<>]*)> <([^<>]*)>(?: <(\d*)>)?(?: <t:([^<>]*)>)?')
depends_reg = re.compile(r'  - Project:<(?P<name>.*)> Change:<(?P<change_no>.*)> Type:<(?P<type>.*)>')
depends_on_re = re.compile(r"^Depends-On: (I[0-9a-f]{40})\s*$", re.MULTILINE | re.IGNORECASE)
firstline_reg = common_regex.int_firstline_reg
jira_id_reg = re.compile(r'%JR=(.*)')
platform_id_reg = re.compile(r'Platform ID: <(.*?)>')


class IntegrationChange(object):
    def __init__(self, rest, change_no):
        self.rest = rest
        self.change_no = change_no
        self.info = None
        self.detailed_info = None
        self.commit_info = None
        self.refresh_info()
        self.refresh_detailed_info()
        self.refresh_commit_info()

    def refresh_info(self):
        self.info = self.rest.get_ticket(self.change_no,
                                         ['CURRENT_REVISION',
                                          'DOWNLOAD_COMMANDS',
                                          'LABELS'])

    def refresh_detailed_info(self):
        self.detailed_info = self.rest.get_detailed_ticket(self.change_no)

    def refresh_commit_info(self):
        self.commit_info = self.rest.get_commit(self.change_no)

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

    def get_root_change(self):
        if self.get_type() == 'root':
            return self.change_no
        else:
            for depend in self.get_depends():
                if depend[0] == 'root_monitor':
                    return depend[1]
            return None

    def get_components(self):
        components = set()
        msg = self.commit_info.get('message')
        miter = comp_reg.findall(msg)
        for m in miter:
            components.add(m)
        return list(components)

    def get_depends(self):
        depends = set()
        msg = self.commit_info.get('message')
        miter = depends_reg.findall(msg)
        for m in miter:
            depends.add(m)
        return list(depends)

    def get_depends_on(self):
        depends = set()
        msg = self.commit_info.get('message')
        miter = depends_on_re.findall(msg)
        for m in miter:
            depends.add(m)
        return list(depends)

    def get_feature_id(self):
        msg = self.commit_info.get('message')
        m = fifi_reg.search(msg)
        if m:
            return m.groups()[0]
        return None

    def get_integration_mode(self):
        msg = self.commit_info.get('message')
        if "<with-zuul-rebase>" in msg:
            return "HEAD"
        elif "<without-zuul-rebase>" in msg:
            return "FIXED_BASE"
        else:
            raise Exception("Can not get integration mode form commit message.")

    def review(self, comment, label_dict=None):
        self.rest.review_ticket(self.change_no, comment, label_dict)

    def get_type(self):
        if 'ROOT CHANGE' in self.commit_info.get('message'):
            return 'root'
        if 'MANAGER CHANGE' in self.commit_info.get('message'):
            return 'integration'
        if self.get_info().get('project') == 'MN/SCMTA/zuul/inte_ric':
            return 'external'
        return 'component'

    def get_project(self):
        project = self.rest.get_ticket(self.change_no)['project']
        return project

    def get_branch(self):
        branch = self.rest.get_ticket(self.change_no)['branch']
        return branch

    def get_version(self):
        msg = self.commit_info.get('message')
        version = firstline_reg.search(msg).groups()[1]
        return version

    def get_title(self):
        msg = self.commit_info.get('message')
        title = firstline_reg.search(msg).groups()[2]
        return title

    def get_change_name(self):
        msg = self.commit_info.get('message')
        change_name = firstline_reg.search(msg).groups()[0]
        return change_name

    def get_topic(self):
        msg = self.commit_info.get('message')
        topic = firstline_reg.search(msg).groups()[3]
        return topic

    def get_topic_type(self):
        msg = self.commit_info.get('message')
        type_title = firstline_reg.search(msg).groups()[2]
        return type_title.split()[0]

    def get_platform_id(self):
        msg = self.commit_info.get('message')
        platform_id = platform_id_reg.search(msg).groups()[0]
        return platform_id

    def get_mr_repo_and_branch(self):
        mr_re = re.compile(r'Patch Set .*\n.*\nMR created in (.*)\n.*title:(.*)\n.*branch:(.*)')
        mr_repo = ''
        mr_branch = ''
        for msg in reversed(self.detailed_info['messages']):
            msg = msg['message']
            m = mr_re.match(msg)
            if m:
                mr_repo = m.group(1).strip()
                mr_branch = m.group(3).strip()
        return mr_repo, mr_branch

    def get_jira_id(self):
        msg = self.commit_info.get('message')
        jira_id = jira_id_reg.search(msg).groups()[0]
        return jira_id

    def get_with_without(self):
        msg = self.commit_info.get('message')
        if 'without-zuul-rebase' in msg:
            return '<without-zuul-rebase>'
        return '<with-zuul-rebase>'


class RootChange(IntegrationChange):

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
                for submodule_string in result_list:
                    if 'externals/integration' in submodule_string:
                        result_list.remove(submodule_string)
                if result_list:
                    return json.loads(result_list[-1])
        return None

    def get_create_feature_yaml(self):
        msg = self.commit_info.get('message')
        m = create_feature.search(msg)
        if m:
            return m.groups()[0]
        return 'true'

    def get_int_project(self):
        msg = self.commit_info.get('message')
        m = int_project_reg.search(msg)
        if m:
            return m.groups()[0]
        return None

    def get_ecl_branch(self):
        msg = self.commit_info.get('message')
        m = ecl_branch_reg.search(msg)
        if m:
            return m.groups()[0]
        return None

    def get_ecl_int_branch(self):
        msg = self.commit_info.get('message')
        m = ecl_int_branch_reg.search(msg)
        if m:
            return m.groups()[0]
        return None

    def get_int_branch(self):
        msg = self.commit_info.get('message')
        m = int_branch_reg.search(msg)
        if m:
            return m.groups()[0]
        return None


class ManageChange(IntegrationChange):

    def get_all_components(self):
        components = set()
        msg = self.commit_info.get('message')
        miter = ric_reg.findall(msg)
        for m in miter:
            components.add(m)
        return list(components)

    def get_build_streams(self, with_sbts=False):
        streams = list()
        streams_regex = re.compile(r'.+\/([.0-9]*)\/.*')
        sbts_regex = re.compile(r'.+\/(SBTS[.0-9]*)\/.*')
        changed_files = self.rest.get_file_list(self.change_no)
        for change in changed_files:
            stream = streams_regex.match(change)
            if stream and 'default' not in stream.group(1):
                streams.append(stream.group(1))
                continue
            if with_sbts:
                sbts_stream = sbts_regex.match(change)
                if sbts_stream and 'default' not in sbts_stream.group(1):
                    streams.append(sbts_stream.group(1))
        return streams


class IntegrationCommitMessage(object):
    def __init__(self, change):
        self.change = change
        self.msg_lines = self.change.commit_info.get('message').split('\n')

    def get_msg(self):
        return '\n'.join(self.msg_lines)

    def update_interface_info(self, bb_version, commit_ID, comp_name):
        # find bb_version line and commit-ID line to remove
        begin_line = 0
        changeid_line = 0
        comp_line_value = '        comp_name: {}'.format(comp_name)
        bb_line_value = '        bb_version: {}'.format(bb_version)
        commit_line_value = '        commit-ID: {}'.format(commit_ID)
        old_interfaces_list = []
        for i, v in enumerate(self.msg_lines):
            if v.startswith('Change-Id:'):
                changeid_line = i
                continue
            if v.startswith('interface info:'):
                begin_line = i
                continue
            if begin_line > 0 and i > begin_line:
                m = com_name_reg.match(v)
                if m and v.split(':')[1].strip() == comp_name:
                    old_interfaces_list.append(i)
                    bb_line = self.msg_lines[i + 1]
                    commit_line = self.msg_lines[i + 2]
                    m = bb_version_reg.match(bb_line)
                    if m:
                        old_interfaces_list.append(i + 1)
                        self.msg_lines[i] = bb_line_value
                    n = commit_ID_reg.match(commit_line)
                    if n:
                        old_interfaces_list.append(i + 2)
                        self.msg_lines[i] = commit_line_value
        print('Remove old interfaces list: {}'.format(old_interfaces_list))
        self.msg_lines = [v for i, v in enumerate(self.msg_lines) if i not in old_interfaces_list]
        if begin_line == 0:
            print('Set begin line to {} by changeid position'.format(changeid_line))
            begin_line = changeid_line
            self.msg_lines.insert(begin_line, 'interface info:')
        self.msg_lines.insert(begin_line + 1, comp_line_value)
        self.msg_lines.insert(begin_line + 2, bb_line_value)
        self.msg_lines.insert(begin_line + 3, commit_line_value)

    def update_fifi(self, new_fifi):
        # no matter current FIFI has value or not
        for i, v in enumerate(self.msg_lines):
            if v.startswith('%FIFI='):
                self.msg_lines.insert(i, '%FIFI={}'.format(new_fifi))
                self.msg_lines.remove(v)

    def update_topic_in_firstline(self, new_topic):
        # no matter current topic exist in first line or not
        reg = common_regex.int_firstline_reg
        msg = self.get_msg()
        old_topic = reg.search(msg).groups()[1]
        to_be_replaced = '<{}>'.format(old_topic)

        new_msg = msg.replace(to_be_replaced, '<{}>'.format(new_topic))
        self.msg_lines = new_msg.split('\n')

    def update_topic_in_gnb_firstline(self, new_topic):
        msg = self.get_msg()
        gnb_first_line = common_regex.gnb_firstline_reg.search(msg)
        new_msg = msg.replace(gnb_first_line.groups()[3], new_topic) if gnb_first_line else msg
        self.msg_lines = new_msg.split('\n')

    def update_topic(self, new_topic):
        if new_topic:
            self.update_topic_in_gnb_firstline(new_topic)
            self.update_fifi(new_topic)
            self.update_topic_in_firstline(new_topic)

    def remove_ric(self, change):
        # judge if there is the need to remove
        ol = self.change.get_all_components()
        nl = change.get_components()
        rl = []
        for line in nl:
            for oline in ol:
                if str(change.change_no) == str(oline[2]) and str(line) == str(oline[0]):
                    rl.append(line)
                    break
        # find where to remove
        begin, end = self.find_ric()
        # insert
        to_remove = []
        for index in range(begin, end + 1):
            line = self.msg_lines[index]
            for rline in rl:
                if str(change.change_no) in line and rline in line:
                    to_remove.append(line)
                    break
        for line in to_remove:
            self.msg_lines.remove(line)

    def add_ric(self, change):
        # find the beginning line of ric
        begin_line = -1
        for i, v in enumerate(self.msg_lines):
            if 'This integration contains following ric component(s):' in v:
                begin_line = i + 1
        project = change.get_project()
        components = change.get_components()
        change_no = str(change.change_no)
        change_type = change.get_type()
        for comp in components:
            line_value = '  - RIC <{}> <{}> <{}> <t:{}>'.format(
                comp, project, change_no, change_type)
            if begin_line > -1 and line_value not in self.msg_lines:
                self.msg_lines.insert(begin_line, line_value)

    def find_ric(self):
        begin = -1
        end = -1
        for index, item in enumerate(self.msg_lines):
            if begin == -1:
                if ric_reg.match(item):
                    begin = index
            else:
                if not ric_reg.match(item):
                    end = index - 1
                    break
        return begin, end

    def remove_depends(self, change):
        # find where to remove
        begin, end = self.find_depends()
        # insert
        to_remove = []
        for index in range(begin, end + 1):
            line = self.msg_lines[index]
            if str(change.change_no) in line:
                to_remove.append(line)
        for line in to_remove:
            self.msg_lines.remove(line)

    def add_depends(self, change):
        # find the beginning line of depends
        begin_line = -1
        for i, v in enumerate(self.msg_lines):
            if 'This change depends on following change(s):' in v:
                begin_line = i + 1
        change_name = change.get_change_name()
        change_no = str(change.change_no)
        change_type = change.get_type()
        if begin_line > -1:
            line_value = '  - Project:<{}> Change:<{}> Type:<{}>'.format(
                change_name, change_no, change_type)
            if line_value not in self.msg_lines:
                self.msg_lines.insert(begin_line, line_value)

    def find_depends(self):
        begin = -1
        end = -1
        for index, item in enumerate(self.msg_lines):
            if begin == -1:
                if depends_reg.match(item):
                    begin = index
            else:
                if not depends_reg.match(item):
                    end = index - 1
                    break
        return begin, end

    def add_depends_on(self, change):
        begin_line = -1
        for i, v in enumerate(self.msg_lines):
            if v.startswith('Depends-on: '):
                begin_line = i + 1
        change_id = str(change.get_info().get('change_id'))
        if begin_line > -1:
            line_value = 'Depends-on: {}'.format(change_id)
            if line_value not in self.msg_lines:
                self.msg_lines.insert(begin_line, line_value)

    def remove_depends_on(self, change):
        # find where to remove
        begin, end = self.find_depends_on()
        # insert
        to_remove = []
        for index in range(begin, end + 1):
            line = self.msg_lines[index]
            if str(change.get_info().get('change_id')) in line:
                to_remove.append(line)

        for line in to_remove:
            self.msg_lines.remove(line)

    def find_depends_on(self):
        begin = -1
        end = -1
        for index, item in enumerate(self.msg_lines):
            if begin == -1:
                if depends_on_re.match(item):
                    begin = index
            else:
                if not depends_on_re.match(item):
                    end = index - 1
                    break
        return begin, end

    def add_depends_root(self, root_change_obj):
        begin_line = -1
        for i, v in enumerate(self.msg_lines):
            if v.startswith('Change-Id:'):
                begin_line = i - 1
        change_name = root_change_obj.get_change_name()
        change_no = str(root_change_obj.change_no)
        change_type = root_change_obj.get_type()
        if begin_line > -1:
            line_value = '\nThis change depends on following change(s):\n'
            line_value += '  - Project:<{}> Change:<{}> Type:<{}>'.format(
                change_name, change_no, change_type)
            if line_value not in self.msg_lines:
                self.msg_lines.insert(begin_line, line_value)

    def add_depends_on_root(self, root_change_id):
        begin_line = -1
        for i, v in enumerate(self.msg_lines):
            if v.startswith('Change-Id:'):
                begin_line = i - 1
        if begin_line > -1:
            line_value = 'Depends-on: {}'.format(root_change_id)
            if line_value not in self.msg_lines:
                self.msg_lines.insert(begin_line, line_value)

    def remove_depends_on_root(self, root_change_id):
        line_value = 'Depends-on: {}'.format(root_change_id)
        if line_value in self.msg_lines:
            self.msg_lines.remove(line_value)
