#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import os
import git
import sys
import copy
import fire
import shutil
import traceback

from api import config
from api import gitlab_api
from api import gerrit_rest
from mod import mailGenerator
from mod import get_component_info
from update_with_zuul_rebase import update_with_rebase_info
from generate_bb_json import parse_comments_mail
from int_gitlab_opt import get_branch_and_srv
from rebase_env import clear_change, create_file_change_by_env_change
from mod.integration_change import RootChange, IntegrationChange


CONF = config.ConfigTool()
CONF.load('repo')
CONF.load('mail')


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


def rebase_by_load(rest, change_no, base_package,
                   gitlab_info_path='', mail_list=None):
    op = RootChange(rest, change_no)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    int_change_obj = IntegrationChange(rest, int_change)
    topic = '{} of {}'.format(int_change_obj.get_version(),
                              int_change_obj.get_title())
    base_int_obj = None
    if base_package != 'HEAD':
        base_int_obj = get_component_info.init_integration(base_package)
    rebase_failed = {}
    rebase_succeed = {}
    comp_change_list.append(change_no)
    for comp_change in comp_change_list:
        print('Find component info for change: {}'.format(comp_change))
        comp_change_obj = IntegrationChange(rest, comp_change)
        comp_names = comp_change_obj.get_components()
        if not comp_names:
            print('No component info for change: {}'.format(comp_change))
            continue
        comp_name = comp_names[0]
        if 'env' in comp_names:
            comp_name = 'env'
        project = comp_change_obj.get_project()
        branch = comp_change_obj.get_branch()
        comp_name_with_change = '{} {}'.format(comp_name, comp_change)
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
                rebase_succeed[comp_name_with_change] = comp_hash
            except Exception:
                traceback.print_exc()
                # if is env:
                if comp_name == 'env':
                    try:
                        clear_and_rebase_file(rest, change_no,
                                              'env-config.d/ENV', comp_hash)
                        rebase_succeed['env-{}'.format(change_no)] = comp_hash
                    except Exception:
                        rebase_failed[comp_name_with_change] = comp_hash
                else:
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
                    rebase_succeed[comp_name_with_change] = comp_hash
                except Exception:
                    traceback.print_exc()
                    rebase_failed[comp_name_with_change] = comp_hash
    rest.review_ticket(
        change_no,
        'Rebase tickets to {}, results:\nSucceed: {}\nFailed: {}'.format(
            base_package, rebase_succeed, rebase_failed))
    mail_params = {'topic': topic, 'base_package': base_package}
    mail_params['mode'] = 'fixed_rebase'
    if base_package == 'HEAD':
        mail_params['mode'] = 'HEAD'
    send_rebase_results(mail_list, mail_params, rebase_succeed, rebase_failed)
    if rebase_succeed:
        for comp, ver in rebase_succeed.items():
            print('### Rebase {} to {} Succeed ###'.format(comp, ver))
    if rebase_failed:
        for comp, ver in rebase_failed.items():
            print('*** Rebase {} to {} Failed ***'.format(comp, ver))
        print('Not able to rebase all components: {}'.format(rebase_failed))
        sys.exit(2)


def clear_and_rebase_file(rest, change_no, file_path, env_hash):
    env_change = rest.get_file_change(file_path, change_no)
    print('Env change {}'.format(env_change))
    # Get current ENV changes
    if 'new_diff' in env_change and env_change['new_diff']:
        env_change_list = env_change['new_diff']
        print('Update env for change {}'.format(change_no))
        # delete edit
        print('delete edit for change {}'.format(change_no))
        try:
            rest.delete_edit(change_no)
        except Exception as e:
            print('delete edit failed, reason:')
            print(str(e))
        # clear change
        print('clear change {}'.format(change_no))
        try:
            clear_change(rest, change_no)
        except Exception as e:
            print('clear change failed, reason:')
            print(str(e))
        # rebase change
        print('rebase the change {}'.format(change_no))
        try:
            if env_hash != 'HEAD':
                rest.rebase(change_no, env_hash)
            else:
                rest.rebase(change_no)
        except Exception as e:
            print('Change cannot be rebased, reason: {}')
            print(str(e))
            raise Exception(str(e))
        # add new env
        print('add new env for change {}'.format(change_no))
        base_env = rest.get_file_content('env-config.d/ENV', change_no)
        create_file_change_by_env_change(
            env_change_list,
            base_env,
            file_path)


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
    mail_list = get_mail_list(comp_change_list, int_change, root_change, rest)
    if base_package == 'HEAD':
        update_with_rebase_info(rest, root_change, 'with-zuul-rebase')
        rest.review_ticket(int_change, 'use_default_base')
        rebase_by_load(rest, root_change, base_package,
                       gitlab_info_path=gitlab_info_path, mail_list=mail_list)
    else:
        update_with_rebase_info(rest, root_change, 'without-zuul-rebase')
        ver_partten = '.'.join(base_package.split('.')[0:2])
        rest.review_ticket(
            int_change,
            'update_base:{},{}'.format(ver_partten, base_package))
        rebase_by_load(rest, root_change, base_package,
                       gitlab_info_path=gitlab_info_path, mail_list=mail_list)


def get_mail_list(comp_change_list, int_change, root_change, rest):
    change_list = copy.deepcopy(comp_change_list)
    change_list.append(int_change)
    change_list.append(root_change)
    mail_list = parse_comments_mail(int_change, rest, using_cache=False)
    for change_id in change_list:
        reviews_json = rest.get_reviewer(change_id)
        reviews_mail_list = [x['email'] for x in reviews_json if 'email' in x]
        mail_list.extend(reviews_mail_list)
    return mail_list


def send_rebase_results(mail_list, mail_params, rebase_succeed, rebase_failed):
    dt = CONF.get_dict('integration_rebase')
    dt.update(mail_params)
    rebase_result = []
    for comp_name_with_change, comp_hash in rebase_succeed.items():
        comp_name = comp_name_with_change.split()[0]
        change_id = comp_name_with_change.split()[1]
        comp_name_with_link = '<a href="https://gerrit.ext.net.nokia.com/gerrit/#/c/{}">{}</a>'.format(change_id, comp_name)
        rebase_result.append(('Succeed - {}'.format(comp_name_with_link), comp_hash))
    for comp_name_with_change, comp_hash in rebase_failed.items():
        comp_name = comp_name_with_change.split()[0]
        change_id = comp_name_with_change.split()[1]
        comp_name_with_link = '<a href="https://gerrit.ext.net.nokia.com/gerrit/#/c/{}">{}</a>'.format(change_id, comp_name)
        rebase_result.append(('[red]Failed', '{} - {}'.format(comp_name_with_link, comp_hash)))
    dt['rebase_result'] = rebase_result
    dt['receiver'] = ';'.join(mail_list)
    print('Send email to {}'.format(mail_list))
    mail_generator = mailGenerator.MailGenerator(
        'integration_rebase',
        dt,
        dt['import_tools'].split(','))
    mail_generator.generate()


def run(root_change, gerrit_info_path,
        gitlab_info_path='', base_package='HEAD'):
    rest = init_gerrit_rest(gerrit_info_path)
    switch_with_rebase_mod(root_change, rest, base_package, gitlab_info_path)


if __name__ == '__main__':
    fire.Fire()
