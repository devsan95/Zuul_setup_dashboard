#! /usr/bin/env python2.7

# -*- coding:utf-8 -*-

"""
check pipeline availability.
"""

import os
import re
import sys
import time
import datetime
import traceback
import citools
import argparse
from api import file_api, gerrit_api, config
from pygerrit2 import GerritRestAPI, HTTPBasicAuth


def _parse_args():
    parser = argparse.ArgumentParser(description='Validate pipeline.')
    parser.add_argument('--project', '-p', nargs='?', default='dummy-project3',
                        type=str, dest='project', required=False,
                        help='Gerrit project to create tickets for bunch.')
    args = parser.parse_args()
    return vars(args)


def _main():
    args = _parse_args()
    tmp_dir = file_api.TempFolder()
    cf = config.ConfigTool()
    cf.load('qa')
    print('Working dir is {}'.format(tmp_dir.get_directory()))

    test_repo_path1 = tmp_dir.get_directory('test-bunch1')
    test_repo_path2 = tmp_dir.get_directory('test-bunch2')
    test_repo_path3 = tmp_dir.get_directory('test-bunch3')
    print(test_repo_path1)
    print(test_repo_path2)
    print(test_repo_path3)

    ssh_user = cf.get('qa-gerrit', 'user')
    ssh_server = "gerrit-code.zuulqa.dynamic.nsn-net.net"
    ssh_server_http = "10.157.107.56:8180"
    ssh_port = cf.get('qa-gerrit', 'port')
    ssh_project = cf.get(args['project'], 'project')

    # fetch code
    if not os.path.exists(test_repo_path1):
        os.makedirs(test_repo_path1)
    # create first change
    push_result_list1 = gerrit_api.create_one_ticket(
        ssh_server, ssh_user, ssh_port, ssh_project, tmp_folder=test_repo_path1)

    reg = re.compile(r'\+/([\d,]+)')
    patchset1 = None
    for line in push_result_list1:
        print(line)
        result = reg.search(line)
        if result:
            patchset1 = result.group(1)

    if patchset1 is None:
        raise Exception('Cannot get patchset1 No.')

    # check if the first change is passed check pipeline
    print('Patchset1 is {}'.format(patchset1))
    for i in range(1, 30):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset1, ['label:Verified=+1']):
            break

    if not os.path.exists(test_repo_path2):
        os.makedirs(test_repo_path2)
    # create second change
    push_result_list2 = gerrit_api.create_one_ticket(
        ssh_server, ssh_user, ssh_port, ssh_project, file_path='content2.txt', tmp_folder=test_repo_path2)

    patchset2 = None
    for line in push_result_list2:
        print(line)
        result = reg.search(line)
        if result:
            patchset2 = result.group(1)

    if patchset2 is None:
        raise Exception('Cannot get patchset2 No.')

    # check if the second change is passed check pipeline
    print('Patchset2 is {}'.format(patchset2))
    for i in range(1, 30):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset2, ['label:Verified=+1']):
            break

    if not os.path.exists(test_repo_path3):
        os.makedirs(test_repo_path3)
    # create third change
    push_result_list3 = gerrit_api.create_one_ticket(
        ssh_server, ssh_user, ssh_port, ssh_project, file_path='content3.txt', tmp_folder=test_repo_path3)

    patchset3 = None
    for line in push_result_list3:
        print(line)
        result = reg.search(line)
        if result:
            patchset3 = result.group(1)

    if patchset3 is None:
        raise Exception('Cannot get patchset3 No.')

    # check if the third change is passed check pipeline
    print('Patchset3 is {}'.format(patchset3))
    for i in range(1, 30):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, patchset3, ['label:Verified=+1']):
            break

    time.sleep(3)
    #    if not check_pipeline_passed3:
    #        raise Exception('Patchset3 has not been rechecked')
    # make bunch happen
    gerrit_api.review_patch_set(
        ssh_user, ssh_server, patchset1, ['Code-Review=+2'])

    time.sleep(5)

    gerrit_api.review_patch_set(
        ssh_user, ssh_server, patchset2, ['Code-Review=+2'])
    gerrit_api.review_patch_set(
        ssh_user, ssh_server, patchset3, ['Code-Review=+2'])

    auth = HTTPBasicAuth('caqa', 'Welcome321')
    rest = GerritRestAPI(url="http://" + ssh_server_http, auth=auth, verify=False)
    gate_bunch_topic = False
    for i in range(1, 30):
        print('Waiting for 5 secs...')
        time.sleep(5)
        if rest.get("/changes/{}/topic".format(patchset2)):
            change_topic2 = rest.get("/changes/{}/topic".format(patchset2))
            change_topic3 = rest.get("/changes/{}/topic".format(patchset3))
            break

    #    if not gate_bunch_topic:
    #        raise Exception('no topic no bunched changes')
    if change_topic2 == change_topic3 and change_topic2.count("Bunched_Gating"):
        gate_bunch_topic = True

    with open('/tmp/test_result.txt', 'a') as opfd:
        opfd.write("gateinbunch result: {}\n".format(gate_bunch_topic))
        opfd.write("======================== Test Result Stopped {} =======================\n".format(datetime.datetime.today()))


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
