#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import requests
import json
import ruamel.yaml as yaml
import copy
from api import jira_api

DEFAULT_JIRA_URL = 'https://jira3.int.net.nokia.com'
DEFAULT_USER = 'autobuild_c_ou'
DEFAULT_PASSWD = 'a4112fc4'


def run(info_index, jira_url=DEFAULT_JIRA_URL, user=DEFAULT_USER, pwd=DEFAULT_PASSWD):
    meta = copy.deepcopy(info_index['meta']['jira'])
    meta['summary'] = meta['summary'].format(
        title=info_index['meta']['title'],
        version=info_index['meta'].get('version_name'))

    field = {'fields': meta}

    res = requests.post(jira_url + '/rest/api/2/issue/', json=field,
                        auth=requests.auth.HTTPBasicAuth(user, pwd))

    if not res.ok:
        raise Exception('Cannot create ticket, reason: {} {}'.format(res.status_code, res.reason))

    res_data = json.loads(res.content)
    ticket_key = res_data['key']
    print(ticket_key)
    return ticket_key


def open(jira_id, jira_url=DEFAULT_JIRA_URL, user=DEFAULT_USER, pwd=DEFAULT_PASSWD):
    api = jira_api.JIRAPI(user, pwd, jira_url)
    api.open_issue(jira_id)


def close(jira_id, jira_url=DEFAULT_JIRA_URL, user=DEFAULT_USER, pwd=DEFAULT_PASSWD):
    api = jira_api.JIRAPI(user, pwd, jira_url)
    api.close_issue(jira_id)


if __name__ == '__main__':
    structure_obj = yaml.load(open('repo_structure.yaml'),
                              Loader=yaml.Loader, version='1.1')
    structure_obj['meta']['version_name'] = 'test'
    run(structure_obj)
