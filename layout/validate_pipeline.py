#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
check pipeline availability.
"""

import argparse
import os
import re
import sys
import time
import traceback
import citools
from api import file_api, git_api, gerrit_api, config
from sh import supervisorctl, kill
import layout_handler


def _parse_args():
    parser = argparse.ArgumentParser(description='Check pipeline.')
    parser.add_argument('zuul_url', type=str,
                        help='zuul merger url.')
    parser.add_argument('zuul_project', type=str,
                        help='zuul project.')
    parser.add_argument('zuul_ref', type=str,
                        help='zuul merger refspec.')
    parser.add_argument('zuul_commit', type=str,
                        help='zuul merger commit hash.')
    args = parser.parse_args()
    return vars(args)


def _main():
    tmp_dir = file_api.TempFolder()
    cf = config.ConfigTool()
    cf.load('qa')
    print('Working dir is {}'.format(tmp_dir.get_directory()))
    args = _parse_args()
    layout_repo_url = '{}/{}'.format(args['zuul_url'],
                                     args['zuul_project'])
    layout_repo_ref = args['zuul_ref']
    layout_repo_commit = args['zuul_commit']

    test_repo_path = tmp_dir.get_directory('test')
    layout_repo_path = tmp_dir.get_directory('layout')

    ssh_user = cf.get('qa-gerrit', 'user')
    ssh_server = cf.get('qa-gerrit', 'server')
    ssh_port = cf.get('qa-gerrit', 'port')
    ssh_project = cf.get('dummy-project', 'project')

    # update layout according to patchset
    git_api.git_clone_with_refspec_and_commit(
        layout_repo_url,
        layout_repo_ref,
        layout_repo_commit,
        layout_repo_path)

    # open log file to see if reconfig is completed
    log_path = cf.get('qa-zuul', 'log-path')
    with open(log_path, 'r') as log_file:
        lh = layout_handler.LayoutGroup(os.path.join(layout_repo_path,
                                                     'layout.yaml'))
        zuul_reconfigured = False
        log_file.seek(0, 2)

        lh.combine('/etc/zuul/layout.yaml')
        pid = int(supervisorctl('pid', 'zuul-server'))
        kill('-SIGHUP', pid)
        print('Waiting for zuul-server reconfiguring...')
        for i in range(1, 20):
            time.sleep(5)
            lines = log_file.readlines()
            for line in lines:
                if 'Reconfiguration complete' in line:
                    print(line)
                    zuul_reconfigured = True
                    break
            if zuul_reconfigured:
                break

        if not zuul_reconfigured:
            raise Exception('Reconfiguring failed')

    # fetch code
    if not os.path.exists(test_repo_path):
        os.makedirs(test_repo_path)

    push_result_list = gerrit_api.create_one_ticket(
        ssh_server, ssh_user, ssh_port, ssh_project, tmp_folder=test_repo_path)

    reg = re.compile(r'/([\d,]+)')
    patchset = None
    for line in push_result_list:
        print(line)
        result = reg.search(line)
        if result:
            patchset = result.group(1)

    if patchset is None:
        raise Exception('Cannot get patchset No.')

    # check if it is merged
    print('Patchset is {}'.format(patchset))
    check_pipeline_passed = False
    gate_pipeline_passed = False
    for i in range(1, 20):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset, ['Verified=1']):
            check_pipeline_passed = True
            break

    if not check_pipeline_passed:
        raise Exception('Patchset has not been checked')

    gerrit_api.review_patch_set(
        ssh_user, ssh_server, patchset, ['Code-Review=+2'])

    for i in range(1, 20):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset, ['status:merged']):
            gate_pipeline_passed = True
            break

    if not gate_pipeline_passed:
        raise Exception('Patchset not merged')


if __name__ == '__main__':
    try:
        citools.print_path()
        os.environ['GIT_PYTHON_TRACE'] = 'full'
        os.environ['GIT_SSL_NO_VERIFY'] = 'true'

        _main()
        sys.exit(0)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
