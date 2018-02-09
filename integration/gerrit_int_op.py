#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import re
from api import str_api


class IntegrationGerritOperation(object):
    def __init__(self, rest):
        self._rest = rest

    def get_ticket_from_topic(self, topic, repo, branch, name):
        reg = re.compile(r'<(.*?)> on <(.*?)> of <(.*?)> topic <(.*?)>')
        change_id = None
        rest = self._rest
        changes = rest.query_ticket('is:open project:{} branch:{} topic:{}'.format(
            repo, branch, topic))
        if changes:
            for change in changes:
                msgs = change['subject'].split('\n')
                for msg in msgs:
                    m = reg.match(msg)
                    if m:
                        if name == m.group(1):
                            return change['_number']
        return change_id

    def create_change_by_topic(self, topic, repo, branch, name):
        rest = self._rest
        message = '<{change}> on <{version}> of <{title}> topic <{topic}>'.format(
            change=name,
            topic=topic,
            version=branch,
            title=topic
        )
        change_id, ticket_id, rest_id = rest.create_ticket(
            repo, topic, branch, message
        )
        return ticket_id

    def get_info_from_change(self, change_id):
        rest = self._rest
        name = None
        branch = None
        repo = None
        platform = None
        reg = re.compile(r'<(.*?)> on <(.*?)> of <(.*?)> topic <(.*?)>')
        reg2 = re.compile(r'Platform ID: <(.*?)>')
        change = rest.get_ticket(change_id)
        msgs = change['subject'].split('\n')
        for msg in msgs:
            m = reg.match(msg)
            if m:
                name = m.group(1)
            m2 = reg2.match(msg)
            if m2:
                platform = m2.group(1)
            if name and platform:
                break
        branch = change['branch']
        repo = change['project']
        return name, branch, repo, platform

    def clear_change(self, change_id):
        rest = self._rest
        flist = rest.get_file_list(change_id)
        for file_path in flist:
            file_path = file_path.split('\n', 2)[0]
            if file_path != '/COMMIT_MSG':
                rest.restore_file_to_change(change_id, file_path)
        rest.publish_edit(change_id)

    def copy_change(self, from_id, to_id):
        rest = self._rest
        rest_id_dst = to_id
        rest_id_src = from_id
        flist = rest.get_file_list(rest_id_src)
        file_content = {}
        for file_path in flist:
            file_path = file_path.split('\n', 2)[0]
            if file_path != '/COMMIT_MSG':
                content = rest.get_file_content('file', rest_id_src)
                file_content[file_path] = str_api.strip_begin(
                    content, 'Subproject commit ')

        for file_path, content in file_content.items():
            rest.add_file_to_change(rest_id_dst, file_path, content)
        rest.publish_edit(rest_id_dst)
