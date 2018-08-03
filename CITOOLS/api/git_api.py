#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

"""
A module to do git operation.
"""
import git


def is_git_repo(path):
    try:
        git.Repo(path).git_dir
        return True
    except git.exc.InvalidGitRepositoryError:
        return False


def git_clone_with_refspec_and_commit(remote, refspec, commit, path):
    repo = git.Repo.init(path)
    repo.create_remote('origin', remote)
    repo.remotes.origin.fetch(refspec)
    repo.head.reset(commit, index=True, working_tree=True)
    print('Clone repo [{}]\nrefspec: [{}], commit: [{}]'.format(
        remote, refspec, commit
    ))
    return repo


class GitProgress(git.remote.RemoteProgress):
    def __init__(self):
        super(GitProgress, self).__init__()
        self.stdout = []

    def line_dropped(self, line):
        self.stdout.append(line)

    def update(self, *args):
        self.stdout.append(self._cur_line)
