#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
# Copyright 2018 Nokia
# Copyright 2018 Shawn Zhiqi Xie
# Copyright 2018 HZ 5G SCM Team

"""
A module to do gerrit operation.
"""
from sh import ssh, scp
import json
import git
import arrow
import os
from api import file_api, git_api


def get_ticket_info(ssh_user, ssh_server, change_id,
                    ssh_key=None, port='29418'):
    if ssh_key:
        json_str = ssh('-o', 'StrictHostKeyChecking=no',
                       '-o', 'UserKnownHostsFile=/dev/null',
                       '-p', str(port), ssh_user + '@' + ssh_server,
                       '-i', ssh_key,
                       'gerrit', 'query', '--comments',
                       '--format=JSON', '--current-patch-set',
                       'change:{}'.format(change_id))
    else:
        json_str = ssh('-o', 'StrictHostKeyChecking=no',
                       '-o', 'UserKnownHostsFile=/dev/null',
                       '-p', str(port), ssh_user + '@' + ssh_server,
                       'gerrit', 'query', '--comments',
                       '--format=JSON', '--current-patch-set',
                       'change:{}'.format(change_id))
    print(json_str)

    return json.loads(json_str.split('\n')[0])


def does_patch_set_match_condition(ssh_user, ssh_server, change_id,
                                   condition_list, ssh_key=None, port='29418'):
    if ssh_key:
        json_str = ssh('-o', 'StrictHostKeyChecking=no',
                       '-o', 'UserKnownHostsFile=/dev/null',
                       '-p', str(port), ssh_user + '@' + ssh_server,
                       '-i', ssh_key,
                       'gerrit', 'query',
                       '--format=JSON', '--current-patch-set',
                       'change:{}'.format(change_id), *condition_list)
    else:
        json_str = ssh('-o', 'StrictHostKeyChecking=no',
                       '-o', 'UserKnownHostsFile=/dev/null',
                       '-p', str(port), ssh_user + '@' + ssh_server,
                       'gerrit', 'query',
                       '--format=JSON', '--current-patch-set',
                       'change:{}'.format(change_id), *condition_list)

    try:
        json_list = json_str.rstrip('\n').split('\n')
        json_index = json.loads(json_list[-1])
        if int(json_index['rowCount']) < 1:
            return False

        json_dict = json.loads(json_list[0])
        if int(json_dict['number']) != int(change_id):
            return False
        return True
    except Exception as ex:
        print("An exception %s occurred, msg: %s" % (type(ex), str(ex)))
        return False


def review_patch_set(ssh_user, ssh_server, change_id,
                     label_list, message=None, ssh_key=None, port='29418'):
    param_list = []
    for label in label_list:
        param_list.append('--label')
        param_list.append(label)
    if message:
        param_list.append('--message')
        param_list.append('"' + message + '"')
    param_list.append(str(change_id) + ',' + str(get_last_patchset(
        ssh_user, ssh_server, change_id, ssh_key)))
    ssh_msg = ''
    if ssh_key:
        ssh_msg = ssh('-o', 'StrictHostKeyChecking=no',
                      '-o', 'UserKnownHostsFile=/dev/null',
                      '-p', str(port), '-i', ssh_key,
                      ssh_user + '@' + ssh_server,
                      'gerrit', 'review', *param_list)
    else:
        ssh_msg = ssh('-o', 'StrictHostKeyChecking=no',
                      '-o', 'UserKnownHostsFile=/dev/null',
                      '-p', str(port),
                      ssh_user + '@' + ssh_server,
                      'gerrit', 'review', *param_list)
    print(ssh_msg)


def init_msg_hook(repo_path, scp_user, scp_server, port):
    scp('-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-p', '-P', port, scp_user + '@' + scp_server + ':hooks/commit-msg',
        repo_path + '/.git/hooks/')


def create_one_ticket(gerrit_server, gerrit_user, gerrit_port, gerrit_project,
                      file_path=None, branch='master',
                      tmp_folder=None, append_mode=False):
    ssh_url = 'ssh://{}@{}:{}/{}'.format(
        gerrit_user, gerrit_server, gerrit_port, gerrit_project
    )
    if tmp_folder is None:
        tmp_folder = file_api.TempFolder('gerrit_repo')

    repo_path = os.path.join(tmp_folder, 'repo')
    repo = git.Repo.clone_from(ssh_url, repo_path)
    init_msg_hook(repo_path, gerrit_user, gerrit_server, gerrit_port)

    # create patch
    if file_path:
        file_path = os.path.join(repo_path, file_path)
    else:
        file_path = os.path.join(repo_path, 'content.txt')
    open_mode = 'w'
    if append_mode:
        open_mode = 'a'
    with open(file_path, open_mode) as content:
        content.write('%s \n' % str(arrow.now()))
        content.flush()
        repo.git.add('.')
        repo.git.commit(m='create ticket')

    # push code and get patchset id
    git_progress = git_api.GitProgress()
    origin = repo.remotes.origin
    origin.push('HEAD:refs/for/%s' % branch, progress=git_progress)
    return git_progress.stdout


def get_last_patchset(ssh_user, ssh_server, change_id,
                      ssh_key=None, port='29418'):
    info = get_ticket_info(ssh_user, ssh_server, change_id, ssh_key, port)
    return info['currentPatchSet']['number']
