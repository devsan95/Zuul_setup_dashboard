#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import argparse
import re
import shlex
import sys
import traceback

from slugify import slugify

from api import gerrit_rest


def strip_end(text, suffix):
    if not text.endswith(suffix):
        return text
    return text[:len(text) - len(suffix)]


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
    rest_id = rest.get_ticket(change_id)['id']
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


def get_diff_from_change(rest, change_id):
    rest_id = rest.get_ticket(change_id)['id']
    list = rest.get_file_list(rest_id)
    file_diff = {}
    for file in list:
        file = file.split('\n', 2)[0]
        if file != '/COMMIT_MSG':
            changeset = rest.get_file_change(file, rest_id)
            if 'new_diff' in changeset \
                    and changeset['new_diff']:
                file_diff[file] = strip_begin(changeset['new_diff'],
                                              'Subproject commit ')
    return file_diff


def create_file_change_by_env_change(env_change, file_content):
    lines = file_content.split('\n')
    env_change_split = shlex.split(env_change)
    for i, line in enumerate(lines):
        if '=' in line:
            key2, value2 = line.strip().split('=', 1)
            for env_line in env_change_split:
                if '=' in env_line:
                    key, value = env_line.split('=', 1)
                    if key.strip() == key2.strip():
                        lines[i] = key2 + '=' + value
    for env_line in env_change_split:
        if env_line.startswith('#'):
            lines.append(env_line)
    return '\n'.join(lines)


def create_temp_branch(rest, project_name,
                       base_branch, target_branch, file_diff):
    # delete if exist
    list_branch = rest.list_branches(project_name)
    for branch in list_branch:
        branch['ref'] = strip_begin(branch['ref'], 'refs/heads/')

    for branch in list_branch:
        if branch['ref'] == target_branch:
            rest.delete_branch(project_name, target_branch)
            break
    # create new branch using base branch
    base = None
    for branch in list_branch:
        if branch['ref'] == base_branch:
            base = branch['revision']
            break

    if not base:
        raise Exception(
            'Cannot get revision of base_branch [{}]'.format(base_branch))

    rest.create_branch(project_name, target_branch, base)
    # add files change to branch and merge
    change_id, ticket_id, rest_id = rest.create_ticket(
        project_name, None, target_branch, 'for temp submodule')

    file_changes = {}
    for file, diff in file_diff.items():
        try:
            o_content = rest.get_file_content(file, change_id)
            file_changes[file] = \
                create_file_change_by_env_change(diff, o_content)
        except Exception as e:
            print(str(e))

    for file, content in file_changes.items():
        rest.add_file_to_change(rest_id, file, content)
    rest.publish_edit(rest_id)

    rest.review_ticket(rest_id,
                       'for temp submodule',
                       {'Code-Review': 2, 'Verified': 1, 'Gatekeeper': 1})
    rest.submit_change(rest_id)

    # get commit of the change
    info = rest.get_commit(rest_id)
    return info['commit']


def rebase_change(rest, change_id, commit_message, branch):
    # get all submodule, branch, repo ,change
    submodules = get_submodule_info_from_commit_message(commit_message)
    # restore all submodule and rebase
    for path, info in submodules.items():
        try:
            rest.restore_file_to_change(change_id, path)
        except Exception as e:
            print(str(e))
    try:
        rest.publish_edit(change_id)
    except Exception as e:
        print(str(e))
    try:
        rest.delete_edit(change_id)
    except Exception as e:
        print(str(e))
    print(rest.rebase(change_id))
    # update all submodule: create branch and update revision
    for path, info in submodules.items():
        pchange = info['change']
        print('parent change: {}'.format(pchange))
        file_list = get_diff_from_change(rest, pchange)
        change_info = rest.get_change(pchange)
        commit = create_temp_branch(
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
