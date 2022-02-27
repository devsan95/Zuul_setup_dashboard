#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import argparse
import json
import re
import sys
import traceback

import api.file_api
import api.gerrit_api
import api.gerrit_rest
import skytrack_database_handler
from api import retry
from update_submodule_by_change import get_submodule_list_from_comments


def _parse_args():
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('change_id', type=str, help='change id')
    parser.add_argument('rest_url', type=str, help='')
    parser.add_argument('rest_user', type=str, help='')
    parser.add_argument('rest_pwd', type=str, help='')
    parser.add_argument('auth_type', type=str, default='digest', help='')
    args = parser.parse_args()
    return vars(args)


def strip_begin(text, prefix):
    if not text.startswith(prefix):
        return text
    return text[len(prefix):]


def parse_comments(change_id, rest):
    change_list = []
    submodule_list = []
    change_set = set()
    json_re = re.compile(r'Tickets-List: ({.*})')
    comment_list = rest.generic_get('/changes/{}/detail'.format(change_id))
    for msg in reversed(comment_list['messages']):
        msg = msg['message']
        result_list = json_re.findall(msg)
        if len(result_list) > 0:
            change_list = json.loads(result_list[0])
            break

    submodule_list = get_submodule_list_from_comments(comment_list)

    if change_list:
        root_change = change_list.get('root')
        if root_change:
            change_set.add(root_change)

        manager_change = change_list.get('manager')
        if manager_change:
            change_set.add(manager_change)

        com_changes = change_list.get('tickets')
        if com_changes:
            for co_change_id in com_changes:
                change_set.add(co_change_id)
    else:
        change_set.add(change_id)

    if submodule_list:
        if isinstance(submodule_list, list):
            for submodule_ in submodule_list:
                if len(submodule_) > 1:
                    change_set.add(submodule_[1])

    print(change_set)

    return change_set


def abandon_topic(change_no, rest, mysql_info):
    origin_msg = retry.retry_func(
        retry.cfn(rest.get_commit, change_no), max_retry=10,
        interval=3)['message']
    msg = " ".join(origin_msg.split("\n"))
    reg = re.compile(r'%JR=(\w+-\d+)')
    issue_key = reg.search(msg).groups()[0]
    skytrack_database_handler.update_ticket_status(issue_key, 'Abandon', mysql_info)


def _main(change_id, rest_url, rest_user, rest_pwd, auth_type, mysql_info):
    rest = api.gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()
    changes = parse_comments(change_id, rest)
    try:
        abandon_topic(change_id, rest, mysql_info)
    except Exception as e:
        print('Abandon jira failed, because {}'.format(e))
    for change in changes:
        print('Abandoning {}'.format(change))
        try:
            rest.abandon_change(change)
        except Exception as e:
            print(e)


if __name__ == '__main__':
    try:
        param = _parse_args()
        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
