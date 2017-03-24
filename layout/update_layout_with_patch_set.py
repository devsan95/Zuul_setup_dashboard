#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
check pipeline availability.
"""

import argparse
import os
import sys
import time
import traceback
import citools
from api import file_api, git_api, config
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

    layout_repo_path = tmp_dir.get_directory('layout')

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
