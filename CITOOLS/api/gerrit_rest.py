#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
A module to do gerrit rest operation.
"""

import requests
import re
import json


class GerritRestClient:
    def __init__(self, url, user, pwd):
        self.server_url = url
        self.user = user
        self.pwd = pwd

    @staticmethod
    def parse_rest_response(response):
        content = response.content
        reg = re.compile(r'{.*}', re.MULTILINE | re.DOTALL)
        result = reg.findall(content)
        if not result:
            raise Exception('Invalid result: \n{}'.format(content))
        content = result[0]
        return json.loads(content)

    def add_file_to_change(self, rest_id, file_path, content=''):
        auth = requests.auth.HTTPDigestAuth(self.user, self.pwd)
        rest_url = self.server_url + '/a/changes/' + rest_id + \
            '/edit/' + requests.utils.quote(file_path, safe='')
        ret = requests.put(rest_url, content, auth=auth)
        if not ret.ok:
            raise Exception(
                'In add file [{}] to change [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    file_path, rest_id, ret.status_code, ret.content))

    def publish_edit(self, rest_id):
        auth = requests.auth.HTTPDigestAuth(self.user, self.pwd)
        rest_url = '{}/a/changes/{}/edit:publish'.format(
            self.server_url, rest_id)
        ret = requests.post(rest_url, auth=auth)
        if not ret.ok:
            raise Exception(
                'Publish edit to change [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    rest_id, ret.status_code, ret.content))

    def delete_edit(self, rest_id):
        auth = requests.auth.HTTPDigestAuth(self.user, self.pwd)
        rest_url = '{}/a/changes/{}/edit'.format(
            self.server_url, rest_id)
        ret = requests.delete(rest_url, auth=auth)
        if not ret.ok:
            raise Exception(
                'Delete edit to change [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    rest_id, ret.status_code, ret.content))

    def create_ticket(self, project, topic, branch, message, drafted=False):
        input_data = {
            "project": project,
            "subject": message,
            "branch": branch,
            "topic": topic,
            "status": 'DRAFT' if drafted else 'NEW'
        }
        auth = requests.auth.HTTPDigestAuth(self.user, self.pwd)
        headers = {}
        changes = requests.post(self.server_url + "/a/changes/",
                                json=input_data, auth=auth, headers=headers)
        if not changes.ok:
            raise Exception(
                'In project [{}], Creating change via REST api failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    project, changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        change_id = result['change_id']
        ticket_id = result['_number']
        rest_id = result['id']

        return change_id, ticket_id, rest_id

    def review_ticket(self, rest_id, message, labels=None):
        review_input = {
            'message': message
        }
        if labels:
            review_input['labels'] = labels

        auth = requests.auth.HTTPDigestAuth(self.user, self.pwd)
        url = '{}/a/changes/{}/revisions/current/review'.format(
            self.server_url, rest_id)

        changes = requests.post(url, json=review_input, auth=auth)

        if not changes.ok:
            raise Exception(
                'In change [{}], Creating review via REST api failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_id, changes.status_code, changes.content))

    def query_ticket(self, ticket_id):
        get_param = {
            'q': 'change:{}'.format(ticket_id),
            'n': 1
        }
        auth = requests.auth.HTTPDigestAuth(self.user, self.pwd)
        url = '{}/a/changes/'.format(self.server_url)
        changes = requests.get(url, params=get_param, auth=auth)

        if not changes.ok:
            raise Exception(
                'Query change [{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    ticket_id, changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result

    def generate_http_password(self, account_id):
        auth = requests.auth.HTTPDigestAuth(self.user, self.pwd)
        rest_url = '{}/accounts/{}/password.http'.format(
            self.server_url, account_id)
        content = {"generate": True}
        ret = requests.put(rest_url, json=content, auth=auth)
        if not ret.ok:
            raise Exception(
                'generate_http_password account_id [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    account_id, ret.status_code, ret.content))
