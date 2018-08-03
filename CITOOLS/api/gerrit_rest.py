#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
# Copyright 2018 Nokia
# Copyright 2018 Shawn Zhiqi Xie
# Copyright 2018 HZ 5G SCM Team

"""
A module to do gerrit rest operation.
"""

import json
from urlparse import urljoin

import requests
import yaml


def init_from_yaml(path):
    with open(path) as f:
        obj = yaml.load(f)
        gerrit = obj['gerrit']
        rest = GerritRestClient(gerrit['url'], gerrit['user'], gerrit['pwd'])
        if 'auth' in gerrit:
            if gerrit['auth'] == 'basic':
                rest.change_to_basic_auth()
            elif gerrit['auth'] == 'digest':
                rest.change_to_digest_auth()
        return rest


class GerritRestClient:
    def __init__(self, url, user, pwd):
        self.server_url = url
        if not self.server_url.endswith('/'):
            self.server_url = self.server_url + '/'
        self.user = user
        self.pwd = pwd
        self.auth = requests.auth.HTTPDigestAuth
        self.session = requests.Session()
        self.session.verify = False

    def change_to_digest_auth(self):
        self.auth = requests.auth.HTTPDigestAuth

    def change_to_basic_auth(self):
        self.auth = requests.auth.HTTPBasicAuth

    def get_auth(self):
        if self.user:
            return self.auth(self.user, self.pwd)
        else:
            return None

    def get_rest_url(self, path_):
        if path_.startswith('/'):
            path_ = path_[1:]
        if self.user:
            url_ = urljoin(self.server_url, 'a/')
            url__ = urljoin(url_, path_)
            return url__
        else:
            url_ = urljoin(self.server_url, path_)
            return url_

    @staticmethod
    def parse_rest_response(response):
        content = response.content
        content = content.split("\n", 1)[1]
        return json.loads(content)

    def get_change_address(self, change_no):
        url = urljoin(self.server_url, '#/c/{}/'.format(change_no))
        return url

    def generic_get(self, urlpath):
        auth = self.get_auth()
        url = self.get_rest_url(urlpath)
        changes = self.session.get(url, auth=auth)

        if not changes.ok:
            raise Exception(
                'Get path [{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    urlpath, changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result

    def add_file_to_change(self, rest_id, file_path, content=''):
        auth = self.get_auth()
        _url = 'changes/{}/edit/{}'.format(
            rest_id, requests.utils.quote(file_path, safe=''))
        rest_url = self.get_rest_url(_url)
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
        auth = self.get_auth()
        _url = 'changes/{}/edit'.format(rest_id)
        rest_url = self.get_rest_url(_url)
        change_input = {"restore_path": file_path}
        ret = self.session.post(rest_url, json=change_input, auth=auth)
        if not ret.ok:
            if ret.status_code == 409 and \
                    ret.content.startswith('no changes were made'):
                pass
            else:
                raise Exception(
                    'In restore file [{}] to change [{}] failed.\n'
                    'Status code is [{}], Content is [{}]'.format(
                        file_path, rest_id, ret.status_code, ret.content))

    def publish_edit(self, rest_id):
        auth = self.get_auth()
        rest_url = 'changes/{}/edit:publish'.format(rest_id)
        ret = self.session.post(self.get_rest_url(rest_url), auth=auth)
        if not ret.ok:
            if ret.status_code == 409 and \
                    ret.content.startswith(
                        'identical tree and message'):
                pass
            elif ret.status_code == 409 and \
                    ret.content.startswith(
                        'no edit exists for change'):
                pass
            else:
                raise Exception(
                    'Publish edit to change [{}] failed.\n'
                    'Status code is [{}], content is [{}]'.format(
                        rest_id, ret.status_code, ret.content))

    def delete_edit(self, rest_id):
        auth = self.get_auth()
        rest_url = 'changes/{}/edit'.format(rest_id)
        ret = requests.delete(self.get_rest_url(rest_url), auth=auth)
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
        auth = self.get_auth()
        headers = {}
        changes = self.session.post(self.get_rest_url('changes/'),
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

        auth = self.get_auth()
        url = 'changes/{}/revisions/current/review'.format(rest_id)

        changes = self.session.post(self.get_rest_url(url), json=review_input, auth=auth)

        if not changes.ok:
            raise Exception(
                'In change [{}], Creating review via REST api failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_id, changes.status_code, changes.content))

    def query_ticket(self, query_string, count=None):
        get_param = {
            'q': query_string,
        }
        if count:
            get_param['n'] = count
        auth = self.get_auth()
        url = 'changes/'
        changes = self.session.get(self.get_rest_url(url),
                                   params=get_param, auth=auth)

        if not changes.ok:
            raise Exception(
                'Query change [{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    query_string, changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result

    def get_ticket(self, ticket_id, fields=None):
        auth = self.get_auth()
        get_param = {}
        if fields:
            get_param['o'] = fields
        url = 'changes/{}'.format(ticket_id)
        changes = self.session.get(self.get_rest_url(url), auth=auth,
                                   params=get_param)

        if not changes.ok:
            raise Exception(
                'Query change [{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    ticket_id, changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result

    def get_detailed_ticket(self, ticket_id):
        auth = self.get_auth()
        url = 'changes/{}/detail'.format(ticket_id)
        try:
            ticket = self.session.get(self.get_rest_url(url), auth=auth)
        except Exception as ex:
            print('Exception occur: %s' % str(ex))
        if not ticket.ok:
            raise Exception(
                'Get change [{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    ticket_id, ticket.status_code, ticket.content))
        ticket = self.parse_rest_response(ticket)
        return ticket

    def get_change(self, rest_id):
        auth = self.get_auth()
        url = 'changes/{}'.format(rest_id)
        changes = self.session.get(self.get_rest_url(url), auth=auth)

        if not changes.ok:
            raise Exception(
                'Get change [{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_id, changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result

    def get_commit(self, rest_id, revision_id='current'):
        auth = self.get_auth()
        url = 'changes/{}/revisions/{}/commit'.format(
            rest_id, revision_id)
        changes = self.session.get(self.get_rest_url(url), auth=auth)

        if not changes.ok:
            raise Exception(
                'get_commit_message [{},{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_id, revision_id,
                    changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result

    def generate_http_password(self, account_id):
        auth = self.get_auth()
        rest_url = 'accounts/{}/password.http'.format(account_id)
        content = {"generate": True}
        ret = self.session.put(self.get_rest_url(rest_url), json=content, auth=auth)
        if not ret.ok:
            raise Exception(
                'generate_http_password account_id [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    account_id, ret.status_code, ret.content))

    def get_file_list(self, rest_id, revision_id='current'):
        auth = self.get_auth()
        url = 'changes/{}/revisions/{}/files/'.format(
            rest_id, revision_id)
        changes = self.session.get(self.get_rest_url(url), auth=auth)

        if not changes.ok:
            raise Exception(
                'get_file_list [{},{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_id, revision_id,
                    changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result

    def get_file_change(self, file_path, rest_id, revision_id='current'):
        auth = self.get_auth()
        url = 'changes/{}/revisions/{}/files/{}/diff'.format(
            rest_id, revision_id,
            requests.utils.quote(file_path, safe=''))
        changes = self.session.get(self.get_rest_url(url), auth=auth)

        if not changes.ok:
            raise Exception(
                'get_file_change [{}, {},{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    file_path, rest_id, revision_id,
                    changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        ret_dict = {'old': '', 'new': '', 'old_diff': '', 'new_diff': ''}
        for change in result['content']:
            for fid, content in change.items():
                if fid == 'ab':
                    ret_dict['old'] += '\n'.join(content)
                    ret_dict['new'] += '\n'.join(content)

                    ret_dict['old'] += '\n'
                    ret_dict['new'] += '\n'
                elif fid == 'a':
                    ret_dict['old'] += '\n'.join(content)

                    ret_dict['old'] += '\n'

                    ret_dict['old_diff'] += '\n'.join(content)

                    ret_dict['old_diff'] += '\n'
                elif fid == 'b':
                    ret_dict['new'] += '\n'.join(content)

                    ret_dict['new'] += '\n'

                    ret_dict['new_diff'] += '\n'.join(content)

                    ret_dict['new_diff'] += '\n'
        return ret_dict

    def get_file_content(self, file_path, rest_id, revision_id='current'):
        auth = self.get_auth()
        url = 'changes/{}/revisions/{}/files/{}/content'.format(
            rest_id, revision_id,
            requests.utils.quote(file_path, safe=''))
        changes = self.session.get(self.get_rest_url(url), auth=auth,
                                   headers={'Accept-Encoding': 'deflate',
                                            'Accept': 'application/json'})

        if not changes.ok:
            raise Exception(
                'get_file_change [{}, {},{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    file_path, rest_id, revision_id,
                    changes.status_code, changes.content))

        return self.parse_rest_response(changes)

    def add_reviewer(self, rest_id, reviewer):
        review_input = {
            'reviewer': reviewer,
            'confirmed': True
        }

        auth = self.get_auth()
        url = 'changes/{}/reviewers'.format(rest_id)

        changes = self.session.post(self.get_rest_url(url),
                                    json=review_input, auth=auth)

        if not changes.ok:
            raise Exception(
                'In change [{}], add reviewers via REST api failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_id, changes.status_code, changes.content))

    def get_reviewer(self, rest_id):
        auth = self.get_auth()
        url = 'changes/{}/reviewers'.format(rest_id)

        reviewers = self.session.get(self.get_rest_url(url), auth=auth)

        if not reviewers.ok:
            raise Exception(
                'In change [{}], get reviewers via REST api failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_id, reviewers.status_code, reviewers.content))

        return self.parse_rest_response(reviewers)

    def list_account_emails(self, account='self'):
        auth = self.get_auth()
        url = 'accounts/{}/emails'.format(account)
        emails = self.session.get(self.get_rest_url(url), auth=auth)

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

        auth = self.get_auth()
        url = 'changes/{}/rebase'.format(rest_id)

        changes = self.session.post(self.get_rest_url(url), json=rebase_input, auth=auth)

        if not changes.ok:
            if changes.status_code == 409 and (
                    changes.content.startswith(
                        'Change is already up to date')
            ):
                pass
            else:
                raise Exception(
                    'In change [{}], rebase via REST api failed.\n '
                    'Status code is [{}], content is [{}]'.format(
                        rest_id, changes.status_code, changes.content))

    def set_commit_message(self, rest_id, content=''):
        auth = self.get_auth()
        info = self.get_change(rest_id)
        data = {
            'message':
                content + '\n\nChange-Id: {}\n'.format(info['change_id'])
        }
        rest_url = 'changes/' + str(rest_id) + '/message'
        ret = self.session.put(self.get_rest_url(rest_url), json=data, auth=auth)
        if not ret.ok:
            raise Exception(
                'In set commit message to change [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    rest_id, ret.status_code, ret.content))

    def list_branches(self, project_name):
        auth = self.get_auth()
        url = 'projects/{}/branches/'.format(
            requests.utils.quote(project_name, safe=''))
        ret = self.session.get(self.get_rest_url(url), auth=auth)

        if not ret.ok:
            raise Exception(
                'list branches of {} failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    project_name, ret.status_code, ret.content))

        result = self.parse_rest_response(ret)
        return result

    def create_branch(self, project_name, branch_name, base='HEAD'):
        auth = self.get_auth()
        data = {'revision': base}
        rest_url = 'projects/{}/branches/{}'.format(
            requests.utils.quote(project_name, safe=''),
            requests.utils.quote(branch_name, safe=''))
        ret = self.session.put(self.get_rest_url(rest_url), json=data, auth=auth)
        if not ret.ok:
            raise Exception(
                'In create_branch to project [{}] branch [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    project_name, branch_name,
                    ret.status_code, ret.content))

    def delete_branch(self, project_name, branch_name):
        auth = self.get_auth()
        rest_url = 'projects/{}/branches/{}'.format(
            requests.utils.quote(project_name, safe=''),
            requests.utils.quote(branch_name, safe=''))
        ret = requests.delete(self.get_rest_url(rest_url), auth=auth)
        if not ret.ok:
            raise Exception(
                'delete_branch to project [{}] branch [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    project_name, branch_name,
                    ret.status_code, ret.content))

    def submit_change(self, rest_id):
        auth = self.get_auth()
        rest_url = 'changes/{}/submit'.format(rest_id)
        ret = self.session.post(self.get_rest_url(rest_url), auth=auth)
        if not ret.ok:
            raise Exception(
                'submit_change to change [{}] failed.\n'
                'Status code is [{}], content is [{}]'.format(
                    rest_id, ret.status_code, ret.content))

    def abandon_change(self, rest_id):
        auth = self.get_auth()
        rest_url = 'changes/{}/abandon'.format(rest_id)
        ret = self.session.post(self.get_rest_url(rest_url), auth=auth)
        if not ret.ok:
            if ret.status_code == 409 and \
                    ret.content.startswith('change is abandoned'):
                pass
            else:
                raise Exception(
                    'abandon_change to change [{}] failed.\n'
                    'Status code is [{}], content is [{}]'.format(
                        rest_id, ret.status_code, ret.content))

    def restore_change(self, rest_id):
        auth = self.get_auth()
        rest_url = 'changes/{}/restore'.format(rest_id)
        ret = self.session.post(self.get_rest_url(rest_url), auth=auth)
        if not ret.ok:
            if ret.status_code == 409 and \
                    ret.content.startswith('change is abandoned'):
                pass
            else:
                raise Exception(
                    'restore_change to change [{}] failed.\n'
                    'Status code is [{}], content is [{}]'.format(
                        rest_id, ret.status_code, ret.content))

    def change_commit_msg_to_edit(self, rest_id, commit_msg):
        auth = self.get_auth()
        _url = 'changes/{}/edit:message'.format(rest_id)
        rest_url = self.get_rest_url(_url)
        content = {'message': commit_msg}
        ret = self.session.put(rest_url, json=content, auth=auth)
        if not ret.ok:
            if ret.status_code == 409 and \
                    ret.content.startswith('no changes were made'):
                pass
            else:
                raise Exception(
                    'In change_commit_msg_to_edit to change [{}] failed.\n'
                    'Status code is [{}], content is [{}]'.format(
                        rest_id, ret.status_code, ret.content))

    def create_account(self, name, email, http_password,
                       ssh_key=None, groups=None):
        auth = self.get_auth()
        _url = 'accounts/{}'.format(name)
        rest_url = self.get_rest_url(_url)
        content = {'name': name,
                   'email': email,
                   'http_password': http_password}
        if ssh_key:
            content['ssh_key'] = ssh_key
        if groups:
            content['groups'] = groups

        changes = self.session.put(rest_url, auth=auth, json=content)

        if not changes.ok:
            raise Exception(
                'create_account [{}] failed.\n '
                'Status code is [{}], content is [{}]'.format(
                    rest_url, changes.status_code, changes.content))

        result = self.parse_rest_response(changes)
        return result
