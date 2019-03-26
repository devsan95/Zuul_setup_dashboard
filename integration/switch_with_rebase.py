#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import os
import git
import fire
import shutil
import traceback

from api import config
from api import gitlab_api
from api import gerrit_rest
from mod import get_component_info
from update_with_zuul_rebase import update_with_rebase_info
from int_gitlab_opt import get_branch_and_srv
from mod.integration_change import RootChange, IntegrationChange

CONF = config.ConfigTool()
CONF.load('repo')


def get_branch_out_commits(g, org_branch):
    print('get out parent for {}'.format(org_branch))
    out_parent = g.reflog('show', org_branch).split()[0]
    print('out parent : {}'.format(out_parent))
    commit_list = g.rev_list('{}..HEAD'.format(out_parent)).splitlines()
    commit_list.reverse()
    return commit_list


def rebase_gitlab_branch(repo, branch, org_branch, comp_hash, token):
    repo_path = os.path.join(os.getcwd(), os.path.basename(repo))
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)
    try:
        repo_url = 'https://gitlab-ci-token:{}@{}.git'.format(token, repo)
        print('repo_url: {}'.format(repo_url))
        print('repo_path: {}'.format(repo_path))
        git.Repo.clone_from(repo_url, repo_path)
        g = git.Git(repo_path)
        g.checkout(branch)
        g.pull()
        adapt_commits = get_branch_out_commits(g, org_branch)
        print('Reset commit to {}'.format(comp_hash))
        print('Adapt commits : {}'.format(adapt_commits))
        g.reset(comp_hash, '--hard')
        for adapt_commit in adapt_commits:
            print('Cherry-pick commit {}'.format(adapt_commit))
            g.cherry_pick(adapt_commit)
        g.push('origin', 'HEAD:{}'.format(branch), '--force')
    except Exception:
        traceback.print_exc()
        raise Exception(
            'Failed in rebase {} in {} to {}'.format(branch, repo, comp_hash))


def rebase_by_load(rest, change_no, base_package, gitlab_info_path=''):
    op = RootChange(rest, change_no)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    base_int_obj = None
    if base_package != 'HEAD':
        base_int_obj = get_component_info.init_integration(base_package)
    rebase_failed = {}
    rebase_succed = {}
    comp_change_list.append(change_no)
    for comp_change in comp_change_list:
        print('Find component info for change: {}'.format(comp_change))
        comp_change_obj = IntegrationChange(rest, comp_change)
        comp_names = comp_change_obj.get_components()
        if not comp_names:
            print('No component info for change: {}'.format(comp_change))
            continue
        comp_name = comp_names[0]
        project = comp_change_obj.get_project()
        branch = comp_change_obj.get_branch()
        comp_name_with_change = '{}-{}'.format(comp_name, comp_change)
        if base_package != 'HEAD':
            try:
                comp_hash = get_component_info.get_comp_hash(
                    base_int_obj, comp_name)
            except Exception:
                print('Cannot get hash for {}'.format(comp_name))
                traceback.print_exc()
                rebase_failed[comp_name_with_change] = 'NONE'
                continue
        else:
            comp_hash = 'HEAD'
        if not project == 'MN/SCMTA/zuul/inte_ric':
            try:
                if comp_hash == 'HEAD':
                    rest.rebase(comp_change)
                else:
                    rest.rebase(comp_change, comp_hash)
                rebase_succed[comp_name_with_change] = comp_hash
            except Exception:
                traceback.print_exc()
                rebase_failed[comp_name_with_change] = comp_hash
        else:
            mr_repo, mr_brch = comp_change_obj.get_mr_repo_and_branch()
            if mr_repo:
                try:
                    comp_branch, comp_repo_srv, project = get_branch_and_srv(
                        comp_name,
                        branch)
                    gitlab_obj = init_gitlab_obj(gitlab_info_path,
                                                 comp_repo_srv,
                                                 project)
                    if comp_hash == 'HEAD':
                        comp_hash = get_gitlab_branch_hash(
                            gitlab_obj, project, comp_branch)
                    rebase_gitlab_branch(mr_repo, mr_brch, comp_branch,
                                         comp_hash, gitlab_obj.token)
                    rebase_succed[comp_name_with_change] = comp_hash
                except Exception:
                    traceback.print_exc()
                    rebase_failed[comp_name_with_change] = comp_hash
    rest.review_ticket(
        change_no,
        'Rebase tickets to {}, results:\nSucced: {}\nFailed: {}'.format(
            base_package, rebase_succed, rebase_failed))
    if rebase_succed:
        for comp, ver in rebase_succed.items():
            print('### Rebase {} to {} Succed ###'.format(comp, ver))
    if rebase_failed:
        for comp, ver in rebase_failed.items():
            print('*** Rebase {} to {} Failed ***'.format(comp, ver))
        raise Exception(
            'Not able to rebase all components: {}'.format(rebase_failed))


def init_gerrit_rest(gerrit_info_path):
    return gerrit_rest.init_from_yaml(gerrit_info_path)


def init_gitlab_obj(gitlab_info_path, comp_repo_srv, project):
    gitlab_obj = gitlab_api.init_from_yaml(gitlab_info_path, comp_repo_srv)
    gitlab_obj.set_project(project)
    return gitlab_obj


def get_gitlab_branch_hash(gitlab_obj, project_name, branch):
    gitlab_obj.set_project(project_name)
    branch_info = gitlab_obj.project.branches.get(branch)
    return branch_info.commit['id']


def switch_with_rebase_mod(root_change, rest,
                           base_package, gitlab_info_path=''):
    op = RootChange(rest, root_change)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    if base_package == 'HEAD':
        update_with_rebase_info(rest, root_change, 'with-zuul-rebase')
        rebase_by_load(rest, root_change, base_package, gitlab_info_path)
        rest.review_ticket(int_change, 'use_default_base')
    else:
        update_with_rebase_info(rest, root_change, 'without-zuul-rebase')
        rebase_by_load(rest, root_change, base_package, gitlab_info_path)
        ver_partten = '.'.join(base_package.split('.')[0:2])
        rest.review_ticket(
            int_change,
            'update_base:{},{}'.format(ver_partten, base_package))


def run(root_change, gerrit_info_path,
        gitlab_info_path='', base_package='HEAD'):
    rest = init_gerrit_rest(gerrit_info_path)
    switch_with_rebase_mod(root_change, rest, base_package, gitlab_info_path)


if __name__ == '__main__':
    fire.Fire()
