#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import requests
import json


def run(info_index, jira_url=None, user=None, pwd=None):
    if jira_url is None:
        jira_url = 'https://jira3.int.net.nokia.com'
    if user is None:
        user = 'autobuild_c_ou'
    if pwd is None:
        pwd = 'a4112fc4'

    meta = info_index['meta']['jira'].deepcopy()
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
