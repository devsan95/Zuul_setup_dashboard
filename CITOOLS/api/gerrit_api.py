#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
A module to do gerrit operation.
"""
from sh import ssh, scp
import json
import git
import arrow
import os
from api import file_api, git_api


def does_patch_set_match_condition(ssh_user, ssh_server, patchset,
                                   condition_list):
    print(condition_list)
    json_str = ssh('-p', '29418', ssh_user + '@' + ssh_server,
                   'gerrit', 'query', '--format=JSON', '--current-patch-set',
                   'change:{}'.format(patchset), *condition_list)
    print(json_str)

    try:
        json_list = json_str.rstrip('\n').split('\n')
        json_index = json.loads(json_list[-1])
        if int(json_index['rowCount']) < 1:
            print('Empty results')
            return False

        json_dict = json.loads(json_list[0])
        if int(json_dict['number']) != int(patchset):
            print('{} not match {}'.format(json_dict['number'], patchset))
            return False
        print('Patch set matches condition.')
        return True
    except Exception as ex:
        print("An exception %s occurred, msg: %s" % (type(ex), str(ex)))
        return False


def review_patch_set(ssh_user, ssh_server, patchset, label_list):
    param_list = []
    for label in label_list:
        param_list.append('--label')
        param_list.append(label)
    param_list.append(patchset+',1')
    print(ssh('-p', '29418', ssh_user + '@' + ssh_server,
              'gerrit', 'review', *param_list))


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
