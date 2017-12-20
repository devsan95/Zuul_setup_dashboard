#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date    : 2017-12-19 09:59:02
# @Author  : robin (robin.zhu@nokia-sbell.com)
# @site    : HangZhou

import os
import datetime
from commands import getstatusoutput as excute_shell
from os import path as osp
import fire

gerrit_branch = "master"
components = "recipes-components"


class ExcuteShellError(BaseException):
    """docstring for ExcuteShellError"""

    pass


def run_shell(commands):
    '''
    If don't check result,use excute_shell
    '''
    print("running:  {0}".format(commands))
    result = excute_shell(commands)
    if result[0] != 0:
        raise ExcuteShellError(
            "excute {0} failed,{1}".format(commands, result[-1]))
    return result[-1]


def get_commit_by_file(file):
    return run_shell("git log -n1 --format=%H {0}".format(file))


def get_commit_from_repo(repo):
    def get_commit_from_file(src_files):
        os.chdir(repo)
        commit_ids = [get_commit_by_file(file) for file in src_files]
        return commit_ids
    return get_commit_from_file


def commit_files_by_dir(src_repo, dst_repo, subdir):
    r = run_shell("git status")
    change_files = [
        l.split("/")[1] for l in r.split("\n") if l.startswith("\t" + subdir)]
    change_files = list(set(change_files))
    get_commit = get_commit_from_repo(osp.join(src_repo, subdir))
    commit_ids = get_commit(change_files)
    os.chdir(osp.join(dst_repo, subdir))
    for index, file in enumerate(change_files):
        run_shell("git add {0}".format(file))
        run_shell("git commit -m 'commit from {0} {1}'\
            ".format(commit_ids[index], file))
        run_shell("git push origin HEAD:refs/for/{0}", format(gerrit_branch))


def sync_repo(src_repo, dst_repo):
    '''
    rsync src_repo to dst_repo
    get changed file according to "git status"
    commit and push each changed dir.
    '''
    run_shell("rsync -avz --delete --exclude '.git'\
        {0}/ {1}/".format(src_repo, dst_repo))
    os.chdir(dst_repo)
    commit_files_by_dir(src_repo, dst_repo, components)
    os.chdir(dst_repo)
    run_shell("git add . ")
    run_shell("git commit -m 'sync repo at {0}'\
        ".format(datetime.datetime.now()))
    run_shell("git push origin HEAD:refs/for/{0}", format(gerrit_branch))


if __name__ == '__main__':
    fire.Fire(sync_repo)
    # import sys
    # src_repo = sys.argv[1]
    # dst_repo = sys.argv[2]
    # sync_repo(src_repo,dst_repo)
