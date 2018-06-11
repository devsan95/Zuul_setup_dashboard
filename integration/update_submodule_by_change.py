#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

from __future__ import print_function

import json
import re
import sys
import traceback

import fire
import git
import urllib3

from api import gerrit_rest
from api import retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_submodule_list_from_comments(info):
    json_re = re.compile(r'Submodules-List: (.*)')
    for msg in reversed(info['messages']):
        result_list = json_re.findall(msg['message'])
        if len(result_list) > 0:
            return json.loads(result_list[-1])
    return None


def clear_change(rest, change_id, submodule_path):
    print('Clear {} in {}'.format(submodule_path, change_id))
    try:
        rest.delete_edit(change_id)
    except Exception as e:
        print('delete edit of {} failed'.format(change_id))
        print(e)
    try:
        rest.restore_file_to_change(change_id, submodule_path)
        rest.publish_edit(change_id)
    except Exception as e:
        print('Clear failed, {}'.format(e))
    print('Rebase {}'.format(change_id))
    try:
        rest.rebase(change_id)
    except Exception as e:
        print('Rebase failed, {}'.format(e))
        raise e


def check_submodule(rest, change_id, submodule_path, commit_id, repo_path):
    print('Check if submodule is needed to update')
    # get current commit
    current_commit = rest.get_file_content(submodule_path, change_id)
    print('current commit in submodule is {}'.format(current_commit))
    # compare if need to update
    gm = git.Git(repo_path)
    need_update = False
    try:
        print(gm.merge_base('--is-ancestor', commit_id, current_commit))
        print('{} is ancestor of {}, no need to update.'.format(
            commit_id, current_commit))
    except git.exc.GitCommandError as e:
        print('new commit is not ancestor of current commit, need update')
        print(e)
        need_update = True
    return need_update


def update_submodule(rest, changeid, submodule_path, commit_id):
    print('update submodule, delete edit...')
    try:
        rest.delete_edit(changeid)
    except Exception as e:
        print('delete edit of {} failed'.format(changeid))
        print(e)
    print('update submodule, add file and publish...')
    update_commitmsg(rest, changeid)
    rest.add_file_to_change(changeid, submodule_path, commit_id)
    rest.publish_edit(changeid)
    print('try to delete edit...')
    try:
        rest.delete_edit(changeid)
    except Exception as e:
        print(e)
    print('update submodule, score code-review+2...')
    rest.review_ticket(changeid, 'review', {'Code-Review': 2})
    print('update submodule, Done')


def update_commitmsg(rest, changeid):
    commit = retry.retry_func(
        retry.cfn(rest.get_commit, changeid),
        max_retry=10, interval=3
    )

    msg = commit['message']
    check_msg = 'Intentional changes in externals dir'
    if check_msg not in msg:
        print('No check msg, adding...')
        msgs = msg.split('\n')
        change_id_no = len(msgs) - 2
        for i in range(0, len(msgs)):
            if msgs[i].startswith('Change-Id:'):
                change_id_no = i
        msgs.insert(change_id_no, check_msg)
        new_msg = '\n'.join(msgs)
        rest.change_commit_msg_to_edit(changeid, new_msg)


def run(change_id, gerrit_info_path, repo_path):
    print('Init rest api...')
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)

    print('Get change info...')
    info = retry.retry_func(
        retry.cfn(rest.get_detailed_ticket, change_id),
        max_retry=10, interval=3
    )

    print('Get commit info...')
    commit = retry.retry_func(
        retry.cfn(rest.get_commit, change_id),
        max_retry=10, interval=3
    )

    commit_id = commit['commit']
    print('change commit id is {}'.format(commit_id))

    submodule_list = get_submodule_list_from_comments(info)
    if submodule_list:
        print('submodule list is {}'.format(submodule_list))
    else:
        print('No submodule list, exit')
        return

    for item in submodule_list:
        if len(item) < 2:
            print('Invalid submodule item: {}'.format(item))
            continue
        path = item[0]
        change = item[1]

        print('proceed {} in {}'.format(path, change))

        clear_change(rest, change, path)
        if check_submodule(rest, change, path, commit_id, repo_path):
            update_submodule(rest, change, path, commit_id)


if __name__ == '__main__':
    try:
        fire.Fire(run)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
