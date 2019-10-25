#! /usr/bin/env python2.7

# -*- coding:utf-8 -*-

"""
check pipeline availability.
"""

import os
import re
import sys
import time
import traceback
import citools
import argparse
from api import file_api, gerrit_api, config


def _parse_args():
    parser = argparse.ArgumentParser(description='Validate pipeline.')
    parser.add_argument('--project', '-p', nargs='?', default='dummy-project',
                        type=str, dest='project', required=False,
                        help='Gerrit project to create ticket.')
    parser.add_argument('--project2', '-p2', nargs='?', default='dummy-project2',
                        type=str, dest='project2', required=False,
                        help='Gerrit project to create ticket.')
    args = parser.parse_args()
    return vars(args)


def _main():
    with open('/tmp/test_result.txt', 'a') as opfd:
        opfd.write("======================== Test Result Starting =======================\n")
    args = _parse_args()
    tmp_dir = file_api.TempFolder()
    cf = config.ConfigTool()
    cf.load('qa')
    print('Working dir is {}'.format(tmp_dir.get_directory()))

    test_repo_path = tmp_dir.get_directory('test')
    test_repo_path2 = tmp_dir.get_directory('test-regate')

    ssh_user = cf.get('qa-gerrit', 'user')
    ssh_server = "gerrit-code.zuulqa.dynamic.nsn-net.net"
    ssh_port = cf.get('qa-gerrit', 'port')
    ssh_project = cf.get(args['project'], 'project')
    ssh_project2 = cf.get(args['project2'], 'project')

    # fetch code
    if not os.path.exists(test_repo_path):
        os.makedirs(test_repo_path)
    # create first change
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
    check_pipeline_repassed = False
    gate_pipeline_passed = False
    for i in range(1, 20):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset, ['label:Verified=+1']):
            check_pipeline_passed = True
            break

    # if not check_pipeline_passed:
    with open('/tmp/test_result.txt', 'a') as opfd:
        opfd.write("check result: {}\n".format(check_pipeline_passed))
    # raise Exception('Patchset has not been checked')

    gerrit_api.review_patch_set(ssh_user, ssh_server, patchset, [], message='recheck')

    time.sleep(10)

    for i in range(1, 20):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset, ['label:Verified=+1']):
            check_pipeline_repassed = True
            break

    # if not check_pipeline_repassed:
    # raise Exception('Patchset has not been rechecked')
    with open('/tmp/test_result.txt', 'a') as opfd:
        opfd.write("recheck result: {}\n".format(check_pipeline_repassed))

    gerrit_api.review_patch_set(
        ssh_user, ssh_server, patchset, ['Code-Review=+2'])

    for i in range(1, 20):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset, ['status:merged']):
            gate_pipeline_passed = True
            break

    # if not gate_pipeline_passed:
    # raise Exception('Patchset not merged')
    with open('/tmp/test_result.txt', 'a') as opfd:
        opfd.write("gate result: {}\n".format(gate_pipeline_passed))

    # fetch code for regate
    if not os.path.exists(test_repo_path2):
        os.makedirs(test_repo_path2)

    push_result_list2 = gerrit_api.create_one_ticket(
        ssh_server, ssh_user, ssh_port, ssh_project2, tmp_folder=test_repo_path2)

    patchset2 = None
    for line2 in push_result_list2:
        print(line2)
        result = reg.search(line2)
        if result:
            patchset2 = result.group(1)

    if patchset2 is None:
        raise Exception('Cannot get patchset No for regate.')

    # check if regate can work
    print('Patchset for regate test is {}'.format(patchset2))
    regate_pipeline_passed = False
    for i in range(1, 20):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset2, ['label:Verified=+1']):
            break

    gerrit_api.review_patch_set(
        ssh_user, ssh_server, patchset2, ['Code-Review=+2'])

    for i in range(1, 20):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset2, ['label:Gatekeeper=-1']):
            break

    gerrit_api.review_patch_set(
        ssh_user, ssh_server, patchset2, [], message='regate')

    for i in range(1, 20):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset2, ['label:Gatekeeper=-1']):
            regate_pipeline_passed = True
            break

    # if not regate_pipeline_passed:
    # raise Exception('regate not work')
    with open('/tmp/test_result.txt', 'a') as opfd:
        opfd.write("regate result: {}\n".format(regate_pipeline_passed))


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
