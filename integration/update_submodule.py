#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import argparse
import re
import sys
import time
import traceback

from api import gerrit_rest


def _parse_args():
    parser = argparse.ArgumentParser(description='Update Submodule')
    parser.add_argument('change_id', type=str,
                        help='change id')
    parser.add_argument('rest_url', type=str,
                        help='')
    parser.add_argument('rest_user', type=str,
                        help='')
    parser.add_argument('rest_pwd', type=str,
                        help='')
    parser.add_argument('auth_type', type=str, default='digest',
                        help='')
    args = parser.parse_args()
    return vars(args)


def parse_submodule_list(subject):
    ret_dict = {}
    lines = subject.split('\n')
    r = re.compile(r'  - SUBMODULE <(.*)> <(.*)> <(.*)>')
    for line in lines:
        m = r.match(line)
        if m:
            ret_dict[m.group(1)] = m.group(3)
    return ret_dict


def fetch_submodule_commit(submodule_dict, rest_client):
    ret_dict = {}
    for submodule, change_id in submodule_dict.items():
        current_data = None
        while True:
            try:
                current_data = rest_client.query_ticket(change_id)
            except Exception as e:
                print(str(e))
                time.sleep(10)

            if current_data and 'status' in current_data \
                    and current_data['status'] == 'MERGED':
                break
            else:
                print('{} Not Merged'.format(change_id))
        commit_data = rest_client.get_commit(current_data['id'])
        ret_dict[submodule] = commit_data['commit']
    return ret_dict


def check_submodule_list_update(submodule_commit_dict, rest_id, rest_client):
    file_list = rest_client.get_file_list(rest_id)
    need_update = False
    for submodule, submit in submodule_commit_dict.items():
        if submodule not in file_list:
            need_update = True
            break
        else:
            info = file_list[submodule]
            if ('status' in info
                    and (info['status'] == 'A' or info['status'] == 'M')) \
                    or 'status' not in info:
                file_content = rest_client.get_file_change(submodule, rest_id)
                if 'Subproject commit {}'.format(submit)\
                        != file_content['new']:
                    need_update = True
                    break
            else:
                need_update = True
                break
    return need_update


def update_submodule(submodule_commit_dict, rest_id, rest_client):
    print('Need update ticket, result is {}'.format(
        str(submodule_commit_dict)))
    need_publish = False
    for submodule, commit in submodule_commit_dict.items():
        rest_client.add_file_to_change(rest_id, submodule, commit)
        need_publish = True
    if need_publish:
        rest_client.publish_edit(rest_id)
        rest_client.review_ticket(rest_id, 'Make into gate',
                                  {'Code-Review': 2})


def _main(change_id, rest_url, rest_user, rest_pwd, auth_type):
    rest = gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()

    rest_id = ''
    description = ''

    while True:
        try:
            data = rest.query_ticket(change_id)
        except Exception as e:
            print(str(e))
            time.sleep(10)

        if data and 'id' in data:
            rest_id = data['id']
            break

    while True:
        try:
            data = rest.get_commit(rest_id)
        except Exception as e:
            print(str(e))
            time.sleep(10)

        if data and 'message' in data:
            description = data['message']
            break

    submodule_dict = parse_submodule_list(description)
    submodule_commit_dict = fetch_submodule_commit(submodule_dict, rest)
    if check_submodule_list_update(submodule_commit_dict, rest_id, rest):
        update_submodule(submodule_commit_dict, rest_id, rest)


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
