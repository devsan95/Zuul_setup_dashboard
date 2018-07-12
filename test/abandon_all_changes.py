#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

from __future__ import print_function

import fire

from api import gerrit_rest


def run(gerrit_conf, repos=None, branches=None):
    rest = gerrit_rest.init_from_yaml(gerrit_conf)

    if repos:
        if isinstance(repos, basestring):
            repos = [repos]
    if branches:
        if isinstance(branches, basestring):
            branches = [branches]

    query_list = ['status:open']
    if repos:
        repo_string = ' OR '.join(['project:{}'.format(x) for x in repos])
        if repo_string:
            query_list.append(repo_string)
    if branches:
        branch_string = ' OR '.join(['branch:{}'.format(x) for x in branches])
        if branch_string:
            query_list.append(branch_string)

    query_string = ' AND '.join(query_list)
    while True:
        ret = rest.query_ticket(query_string)
        if not ret:
            print('EOF.')
            break
        for change in ret:
            try:
                print(rest.get_change_address(change['_number']))
                rest.abandon_change(change['id'])
                print('Abandoned.')
            except Exception as e:
                print(e)


if __name__ == '__main__':
    fire.Fire(run)
