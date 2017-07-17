#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import git
import argparse
import sys
import os
import re
import time
import traceback
import api.gerrit_api
import api.git_api


def _parse_args():
    parser = argparse.ArgumentParser(description='Push result to gerrit')
    parser.add_argument('repo_path', type=str,
                        help='Path to repository')
    parser.add_argument('push_url', type=str,
                        help='Push url such as "HEAD:refs/for/master"')
    parser.add_argument('gerrit_user', type=str,
                        help='Gerrit user to do review')
    parser.add_argument('gerrit_url', type=str,
                        help='Address of gerrit ssh backend')
    parser.add_argument('gerrit_port', type=str,
                        help='Port of gerrit ssh backend')
    parser.add_argument('--key', '-k', nargs='?',
                        type=str, dest='key', required=False,
                        help='Key for gerrit ssh logging. '
                             'Use ~/.ssh/id_rsa if not specified')
    args = parser.parse_args()
    return vars(args)


def _main(**kwargs):
    if 'key' not in kwargs or not kwargs['key']:
        key = os.path.expanduser('~/.ssh/id_rsa')
    else:
        key = kwargs['key']

    path = os.path.abspath(os.path.expanduser(kwargs['repo_path']))
    if not api.git_api.is_git_repo(path):
        raise Exception('The input path is not a valid git repository')

    # get repo
    repo = git.Repo(path)

    # push code and get patchset ids
    git_progress = api.git_api.GitProgress()
    origin = repo.remotes.origin
    origin.push(kwargs['push_url'], progress=git_progress)

    reg = re.compile(r'//.*/([\d,]+)')
    patchsets = []
    for line in git_progress.stdout:
        print(line)
        result = reg.search(line)
        if result:
            patchsets.append(result.group(1))

    if not patchsets:
        raise Exception('Cannot get patchset number from the push')

    # handle each change
    for patchset in patchsets:
        # check if it is verified+1
        print('Patchset number is {}'.format(patchset))
        check_pipeline_passed = False
        for i in range(1, 20):
            if api.gerrit_api.does_patch_set_match_condition(
                    kwargs['gerrit_user'], kwargs['gerrit_url'], patchset,
                    ['Verified=+1'], key, kwargs['gerrit_port']):
                check_pipeline_passed = True
                break
            print('Not found. Waiting for 5 secs...')
            time.sleep(5)

        if not check_pipeline_passed:
            raise Exception('Patchset has not been checked')

        # review as code review +2
        api.gerrit_api.review_patch_set(
            kwargs['gerrit_user'], kwargs['gerrit_url'], patchset,
            ['Code-Review=+2'], 'Automatic review', key, kwargs['gerrit_port'])


if __name__ == '__main__':
    try:
        args = _parse_args()
        _main(**args)
        sys.exit(0)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
