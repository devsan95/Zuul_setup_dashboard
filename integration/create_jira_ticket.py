#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import requests
import json
import ruamel.yaml as yaml
import copy


def run(info_index, jira_url=None, user=None, pwd=None):
    if jira_url is None:
        jira_url = 'https://jira3.int.net.nokia.com'
    if user is None:
        user = 'autobuild_c_ou'
    if pwd is None:
        pwd = 'a4112fc4'

    meta = copy.deepcopy(info_index['meta']['jira'])
    meta['summary'] = meta['summary'].format(
        title=info_index['meta']['title'],
        version=info_index['meta']['version_name'])

    field = {'fields': meta}

    res = requests.post(jira_url + '/rest/api/2/issue/', json=field,
                        auth=requests.auth.HTTPBasicAuth(user, pwd))

    if not res.ok:
        raise Exception('Cannot create ticket')

    res_data = json.loads(res.content)
    ticket_key = res_data['key']
    print(ticket_key)
    return ticket_key


if __name__ == '__main__':
    structure_obj = yaml.load(open('repo_structure.yaml'),
                              Loader=yaml.Loader, version='1.1')
    structure_obj['meta']['version_name'] = 'test'
    run(structure_obj)
