#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import argparse
import sys
import traceback
import re
import create_ticket
from slugify import slugify

from api import gerrit_rest


def strip_end(text, suffix):
    if not text.endswith(suffix):
        return text
    return text[:len(text)-len(suffix)]


def strip_begin(text, prefix):
    if not text.startswith(prefix):
        return text
    return text[len(prefix):]


def _parse_args():
    parser = argparse.ArgumentParser(description='Update Submodule')
    parser.add_argument('rest_url', type=str,
                        help='')
    parser.add_argument('rest_user', type=str,
                        help='')
    parser.add_argument('rest_pwd', type=str,
                        help='')
    parser.add_argument('auth_type', type=str, default='digest',
                        help='')
    parser.add_argument('change_id', type=str,
                        help='')
    parser.add_argument('op', type=str,
                        help='')
    args = parser.parse_args()
    return vars(args)


def get_topic_from_commit_message(commit_message):
    reg = re.compile('topic <(.*?)>')
    result = reg.search(commit_message)
    if not result:
        raise Exception("Cannot find topic")
    return result.group(1)


def get_submodule_info_from_commit_message(commit_message):
    ret_dict = {}
    lines = commit_message.split('\n')
    r = re.compile(r'  - SUBMODULE <(.*)> <(.*)> <(.*)>')
    for line in lines:
        m = r.match(line)
        if m:
            ret_dict[m.group(1)] = {'change': m.group(3),
                                    'project': m.group(2)}
    return ret_dict


def get_temp_repo_info_from_commit_message(commit_message):
    ret_list = []
    lines = commit_message.split('\n')
    r = re.compile(r'  - TEMP <(.*)>')
    for line in lines:
        m = r.match(line)
        if m:
            ret_list.append(m.group(1))
    return ret_list


def get_file_from_change(rest, change_id):
    rest_id = rest.query_ticket(change_id)['id']
    list = rest.get_file_list(rest_id)
    file_content = {}
    for file in list:
        file = file.split('\n', 2)[0]
        if file != '/COMMIT_MSG':
            changeset = rest.get_file_change(file, rest_id)
            if 'new' in changeset \
                    and 'old' in changeset \
                    and changeset['new'] != changeset['old']:
                file_content[file] = strip_begin(changeset['new'],
                                                 'Subproject commit ')
    return file_content


def rebase_change(rest, change_id, commit_message, branch):
    # get all submodule, branch, repo ,change
    submodules = get_submodule_info_from_commit_message(commit_message)
    # restore all submodule and rebase
    for path, info in submodules.items():
        try:
            rest.restore_file_to_change(change_id, path)
        except Exception as e:
            print(str(e))
    rest.publish_edit(change_id)
    print(rest.rebase(change_id))
    # update all submodule: create branch and update revision
    for path, info in submodules.items():
        file_list = get_file_from_change(rest, info['change'])
        change_info = rest.get_change(info['change'])
        commit = create_ticket.create_temp_branch(
            rest, change_info['project'], change_info['branch'],
            branch, file_list)
        rest.add_file_to_change(change_id, path, commit)
    rest.publish_edit(change_id)


def delete_branch(rest, commit_message, branch):
    repo_list = get_temp_repo_info_from_commit_message(commit_message)
    for repo in repo_list:
        try:
            rest.delete_branch(repo, branch)
        except Exception as e:
            print(str(e))


def _main(rest_url, rest_user, rest_pwd, auth_type, change_id, op):
    rest = gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()

    commit_msg = rest.get_commit(change_id)['message']

    topic = get_topic_from_commit_message(commit_msg)
    branch_name = 'inte_test/{}'.format(slugify(topic))

    if op == 'delete':
        delete_branch(rest, commit_msg, branch_name)
    elif op == 'rebase':
        rebase_change(rest, change_id, commit_msg, branch_name)
    else:
        raise Exception('Invalid Operation {}'.format(op))


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
