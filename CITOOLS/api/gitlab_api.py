#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
# Copyright 2018 Nokia
# Copyright 2018 Shawn Zhiqi Xie
# Copyright 2018 HZ 5G SCM Team

"""
A module to do gerrit rest operation.
"""

import sys
import yaml
import gitlab


def init_from_yaml(path, repo):
    with open(path) as f:
        obj = yaml.load(f)
        gitlab_obj = obj[repo]
        return GitlabClient(gitlab_obj['url'], gitlab_obj['token'])


class GitlabClient(object):

    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.gitlab = gitlab.Gitlab(url, private_token=token)
        self.project = None

    def check_project(self):
        if not self.project:
            print('Error: Project is null, \
                   please set Project first')
            sys.exit(2)

    def set_project(self, proj_name):
        project = self.gitlab.projects.get(proj_name)
        print('Info: get project {}'.format(project.name))
        if project:
            self.project = project

    def create_branch(self, branch, ref='master', project=''):
        if project:
            self.set_project(project)
        self.check_project()
        self.project.branches.create({
            'branch': branch,
            'ref': ref})

    def create_mr(self, source_branch, title, target_branch='master'):
        self.check_project()
        return self.project.mergerequests.create(
            {'source_branch': source_branch,
             'target_branch': target_branch,
             'title': title})

    def get_mr(self, srch_dict, state='all', per_page=100, page=1):
        mr_list = self.project.mergerequests.list(state=state, per_page=per_page, page=page)
        mr_rets = []
        for mr_obj in mr_list:
            matched = True
            for k, v in srch_dict.items():
                if not (hasattr(mr_obj, k) and getattr(mr_obj, k) == v):
                    matched = False
            if matched:
                mr_rets.append(mr_obj)
        return mr_rets

    def merge_mr(self, srch_dict, state='all', onlyone=True):
        mr_rets = self.get_mr(srch_dict, state)
        if onlyone and len(mr_rets) > 1:
            print('Error: Find multi Merge Requests \
                   %s, please reset search dict',
                  mr_rets)
            sys.exit(2)
        elif not mr_rets:
            print('Warnning: No Merge Requests find \
                   please reset search dict')
        for mr_ret in mr_rets:
            mr_ret.merge()
