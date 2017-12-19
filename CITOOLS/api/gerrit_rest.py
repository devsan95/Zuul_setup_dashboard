#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
A module to do gerrit rest operation.
"""

import requests
import json


class GerritRestClient:
    def __init__(self, url, user, pwd):
        self.server_url = url
        self.user = user
        self.pwd = pwd
        self.auth = requests.auth.HTTPDigestAuth
        self.session = requests.Session()
        self.session.verify = False

    def change_to_digest_auth(self):
        self.auth = requests.auth.HTTPDigestAuth

    def change_to_basic_auth(self):
        self.auth = requests.auth.HTTPBasicAuth

    @staticmethod
    def parse_rest_response(response):
        content = response.content
        content = content.split("\n", 1)[1]
        return json.loads(content)

    def add_file_to_change(self, rest_id, file_path, content=''):
        auth = self.auth(self.user, self.pwd)
        rest_url = self.server_url + '/a/changes/' + rest_id + \
            '/edit/' + requests.utils.quote(file_path, safe='')
        ret = self.session.put(rest_url, content, auth=auth)
        if not ret.ok:
            if ret.status_code == 409 and \
                 ret.content.startswith('no changes were made'):
                pass
            else:
                raise Exception(
                    'In add file [{}] to change [{}] failed.\n'
                    'Status code is [{}], content is [{}]'.format(
                        file_path, rest_id, ret.status_code, ret.content))

    def restore_file_to_change(self, rest_id, file_path):
        auth = self.auth(self.user, self.pwd)
        rest_url = self.server_url + '/a/changes/' + rest_id + \
            '/edit'
        change_input = {"restore_path": file_path}
        ret = self.session.post(rest_url, json=change_input, auth=auth)
        if not ret.ok:
            if ret.status_code == 409 and \
                 ret.content.startswith('no changes were made'):
                pass
            else:
                raise Exception(
                    'In restore file [{}] to change [{}] failed.\n'
                    'Status code is [{}]'.format(
                        file_path, rest_id, ret.status_code))

    def publish_edit(self, rest_id):
        auth = self.auth(self.user, self.pwd)
        rest_url = '{}/a/changes/{}/edit:publish'.format(
            self.server_url, rest_id)
        ret = self.session.post(rest_url, auth=auth)
        if not ret.ok:
            raise Exception(
                'Publish edit to change [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    rest_id, ret.status_code, ret.content))

    def delete_edit(self, rest_id):
        auth = self.auth(self.user, self.pwd)
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
            "status": 'DRAFT' if drafted else 'NEW'
        }
        if topic:
            input_data['topic'] = topic
        auth = self.auth(self.user, self.pwd)
        headers = {}
        changes = self.session.post(self.server_url + "/a/changes/",
                                    json=input_data, auth=auth,
                                    headers=headers)
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

        auth = self.auth(self.user, self.pwd)
        url = '{}/a/changes/{}/revisions/current/review'.format(
            self.server_url, rest_id)

        changes = self.session.post(url, json=review_input, auth=auth)

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
        auth = self.auth(self.user, self.pwd)
        url = '{}/a/changes/'.format(self.server_url)
        changes = self.session.get(url, params=get_param, auth=auth)

        if not changes.ok:
            raise Exception(
                'Query change [{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    ticket_id, changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result[0]

    def get_commit(self, rest_id, revision_id='current'):
        auth = self.auth(self.user, self.pwd)
        url = '{}/a/changes/{}/revisions/{}/commit'.format(
            self.server_url, rest_id, revision_id)
        changes = self.session.get(url, auth=auth)

        if not changes.ok:
            raise Exception(
                'get_commit_message [{},{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_id, revision_id,
                    changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result

    def generate_http_password(self, account_id):
        auth = self.auth(self.user, self.pwd)
        rest_url = '{}/accounts/{}/password.http'.format(
            self.server_url, account_id)
        content = {"generate": True}
        ret = self.session.put(rest_url, json=content, auth=auth)
        if not ret.ok:
            raise Exception(
                'generate_http_password account_id [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    account_id, ret.status_code, ret.content))

    def get_file_list(self, rest_id, revision_id='current'):
        auth = self.auth(self.user, self.pwd)
        url = '{}/a/changes/{}/revisions/{}/files/'.format(
            self.server_url, rest_id, revision_id)
        changes = self.session.get(url, auth=auth)

        if not changes.ok:
            raise Exception(
                'get_file_list [{},{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_id, revision_id,
                    changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result

    def get_file_change(self, file_path, rest_id, revision_id='current'):
        auth = self.auth(self.user, self.pwd)
        url = '{}/a/changes/{}/revisions/{}/files/{}/diff'.format(
            self.server_url, rest_id, revision_id,
            requests.utils.quote(file_path, safe=''))
        changes = self.session.get(url, auth=auth)

        if not changes.ok:
            raise Exception(
                'get_file_change [{}, {},{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    file_path, rest_id, revision_id,
                    changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        ret_dict = {'old': '', 'new': ''}
        for change in result['content']:
            for fid, content in change.items():
                if fid == 'ab':
                    ret_dict['old'] += '\n'.join(content)
                    ret_dict['new'] += '\n'.join(content)
                elif fid == 'a':
                    ret_dict['old'] += '\n'.join(content)
                elif fid == 'b':
                    ret_dict['new'] += '\n'.join(content)
        return ret_dict

    def add_reviewer(self, rest_id, reviewer):
        review_input = {
            'reviewer': reviewer,
            'confirmed': True
        }

        auth = self.auth(self.user, self.pwd)
        url = '{}/a/changes/{}/reviewers'.format(
            self.server_url, rest_id)

        changes = self.session.post(url, json=review_input, auth=auth)

        if not changes.ok:
            raise Exception(
                'In change [{}], add reviewers via REST api failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_id, changes.status_code, changes.content))

    def list_account_emails(self, account='self'):
        auth = self.auth(self.user, self.pwd)
        url = '{}/a/accounts/{}/emails'.format(self.server_url, account)
        emails = self.session.get(url, auth=auth)

        if not emails.ok:
            raise Exception(
                'list_account_emails failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    emails.status_code, emails.content))

        result = self.parse_rest_response(emails)
        return result

    def rebase(self, rest_id, base=None):
        rebase_input = {}
        if base:
            rebase_input['base'] = base

        auth = self.auth(self.user, self.pwd)
        url = '{}/a/changes/{}/rebase'.format(
            self.server_url, rest_id)

        changes = self.session.post(url, json=rebase_input, auth=auth)

        if not changes.ok:
            if changes.status_code == 409 and \
                    changes.content.startswith('Change is already up to date'):
                pass
            else:
                raise Exception(
                    'In change [{}], rebase via REST api failed.\n '
                    'Status code is [{}], content is [{}]'.format(
                        rest_id, changes.status_code, changes.content))
