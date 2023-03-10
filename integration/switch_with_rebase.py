#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import os
import re
import git
import sys
import copy
import fire
import yaml
import shlex
import shutil
import traceback

import update_depends
import skytrack_database_handler
from api import config
from api import gitlab_api
from api import gerrit_rest
from api import env_repo as get_env_repo
from mod import utils
from mod import wft_tools
from mod import env_changes
from mod import mailGenerator
from mod import get_component_info
from update_with_zuul_rebase import update_with_rebase_info
from generate_bb_json import parse_comments_mail
from int_gitlab_opt import get_branch_and_srv
from rebase_env import clear_change
from mod.integration_change import RootChange, IntegrationChange, IntegrationCommitMessage


CONF = config.ConfigTool()
CONF.load('repo')
CONF.load('mail')
COMP_INFO_DICT = {}


def get_comp_info_obj(base_load):
    if base_load in COMP_INFO_DICT:
        return COMP_INFO_DICT[base_load]
    else:
        comp_info = get_component_info.GET_COMPONENT_INFO(base_load)
        COMP_INFO_DICT[base_load] = comp_info
        return comp_info


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
        print('repo_branch: {}'.format(branch))
        git.Repo.clone_from(repo_url, repo_path)
        g = git.Git(repo_path)
        g.checkout(org_branch)
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


def update_base_commit(rest, comp_change, comp_change_obj, comp_hash):
    commit_msg_obj = IntegrationCommitMessage(comp_change_obj)
    old_commit_msg = commit_msg_obj.get_msg()
    if not comp_hash:
        return
    elif comp_hash == 'HEAD':
        for msg_line in commit_msg_obj.msg_lines:
            if msg_line.startswith('base_commit:'):
                commit_msg_obj.msg_lines.remove(msg_line)
                print('[Info]Remove base commit info since it is HEAD mode!')
    else:
        begin_line = -1
        for msg_line in commit_msg_obj.msg_lines:
            begin_line = begin_line + 1
            if msg_line.startswith('base_commit:'):
                commit_msg_obj.msg_lines.remove(msg_line)
                break
        if begin_line > -1:
            line_value = 'base_commit:{}'.format(comp_hash)
            commit_msg_obj.msg_lines.insert(begin_line, line_value)
    new_commit_msg = commit_msg_obj.get_msg()
    if new_commit_msg == old_commit_msg:
        print('[Info] New commit message is the same as existing commit message,no need to UPDATE!')
    else:
        try:
            rest.delete_edit(comp_change)
        except Exception as e:
            print(e)
        rest.change_commit_msg_to_edit(comp_change, new_commit_msg)
        rest.publish_edit(comp_change)


def _get_component_hash(base_package, comp_names, get_comp_info, branch):
    print('Try to get hash for {} in branch {}'.format(comp_names, branch))
    comp_hash = ''
    try:
        if 'integration' in comp_names:
            base_pkg_obj = utils.BasePkgHandler(branch=branch)
            base_package_name = base_package
            if not base_package.startswith('SBTS'):
                base_package_name = base_package.split('_')[-1]
            wft_version = wft_tools.get_wft_release_name(base_package_name)
            ecl_sack_base = wft_tools.get_subbuild_version(wft_version, 'ECL_SACK_BASE')
            ecl_sack_base_commit = base_pkg_obj.get_ecl_sack_base_commit(ecl_sack_base)
            if not ecl_sack_base_commit:
                print('[WARNING] Can not get ecl_sack_base commit in integration repo for {0}'.format(ecl_sack_base))
            else:
                comp_hash = ecl_sack_base_commit
                base_pkg_obj.push_base_tag(comp_hash)
        else:
            for sub_comp_name in comp_names:
                comp_hash = get_comp_info.get_comp_hash(sub_comp_name)
                if comp_hash:
                    print('Find hash for {}'.format(sub_comp_name))
                    break
    except Exception:
        print('Cannot get hash for {}'.format(comp_names))
        traceback.print_exc()
    return comp_hash


def get_component_hash(base_package, extra_bases, comp_names, get_comp_info, branch):
    comp_hash = _get_component_hash(base_package, comp_names, get_comp_info, branch)
    if not comp_hash:
        print('Try get hash for {}'.format(comp_names))
        print('Try get hash from {}'.format(extra_bases))
        for extra_base in extra_bases:
            extra_base_get_comp_info = get_comp_info_obj(extra_base)
            comp_hash = _get_component_hash(extra_base, comp_names, extra_base_get_comp_info, branch)
            if comp_hash:
                print('Try get hash from {} is {}'.format(extra_bases, comp_hash))
                break
    return comp_hash


def rebase_by_load(rest, change_no, base_package,
                   gitlab_info_path='', mail_list=None, extra_bases=[], config_yaml_dict={}):
    op = RootChange(rest, change_no)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    int_change_obj = IntegrationChange(rest, int_change)
    topic = '{} of {}'.format(int_change_obj.get_version(),
                              int_change_obj.get_title())
    if base_package != 'HEAD':
        get_comp_info = get_comp_info_obj(base_package)
    rebase_failed = {}
    rebase_skipped = {}
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
        if 'env' in comp_names or 'integration' in comp_names:
            comp_name = 'env'
        project = comp_change_obj.get_project()
        branch = comp_change_obj.get_branch()
        change_name = comp_change_obj.get_change_name()
        comp_name_with_change = '{} {}'.format(change_name, comp_change)
        comp_hash = 'HEAD'
        if base_package != 'HEAD':
            comp_hash = get_component_hash(base_package, extra_bases,
                                           comp_names, get_comp_info, branch)
            if not comp_hash:
                rebase_skipped[comp_name_with_change] = 'No source component in packages: {},{}'.format(
                    base_package, extra_bases)
                continue
        parent_hash = rest.get_parent(comp_change)
        print('Parent for [{}] now is [{}]'.format(comp_change, parent_hash))
        print('need to rebase to [{}]'.format(comp_hash))
        if parent_hash == comp_hash:
            print('{} parent is already {},'
                  ' no need rebase'.format(comp_change, parent_hash))
            rebase_succeed[comp_name_with_change] = comp_hash
            continue
        if not project == 'MN/SCMTA/zuul/inte_ric':
            try:
                if comp_hash == 'HEAD':
                    rest.rebase(comp_change)
                    rebase_succeed[comp_name_with_change] = comp_hash
                else:
                    if '@' in comp_hash:
                        rebase_skipped[comp_name_with_change] = 'svn revision {} not fit for git repo'.format(comp_hash)
                    else:
                        rest.rebase(comp_change, comp_hash)
                        rebase_succeed[comp_name_with_change] = comp_hash
            except Exception:
                traceback.print_exc()
                # if is env:
                if comp_name == 'env' or project == 'MN/5G/COMMON/integration':
                    if base_package.startswith('SBTS'):
                        rebase_skipped['env {}'.format(comp_change)] = 'no need rebase root[{}] for SBTS'.format(comp_change)
                        continue
                    env_path = get_env_repo.get_env_repo_info(rest, comp_change)[1]
                    try:
                        # after all streams not use config.yaml disabled
                        # we can use 'rebase_integration_change()' instead
                        clear_and_rebase_file(rest, comp_change,
                                              env_path, comp_hash)
                        rebase_succeed['env {}'.format(comp_change)] = comp_hash
                    except Exception:
                        traceback.print_exc()
                        rebase_failed[comp_name_with_change] = comp_hash
                elif project in config_yaml_dict:
                    print('Try to solve config yaml conflict for {}'.format(comp_change))
                    try:
                        rebase_ret = env_changes.get_yaml_change_and_rebase(
                            rest, change_no, comp_change, config_yaml_dict[project], comp_hash)
                        if not rebase_ret:
                            rebase_failed[comp_name_with_change] = comp_hash
                        else:
                            rebase_succeed[comp_name_with_change] = comp_hash
                    except Exception:
                        traceback.print_exc()
                        rebase_failed[comp_name_with_change] = comp_hash
                else:
                    print('Cannot solve conflict for {}'.format(comp_change))
                    rebase_failed[comp_name_with_change] = comp_hash
        else:
            update_base_commit(rest, comp_change, comp_change_obj, comp_hash)

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
            else:
                rebase_succeed[comp_name_with_change] = comp_hash
    rest.review_ticket(
        change_no,
        'Rebase tickets to {}, results:\nSucceed: {}\nFailed: {}'.format(
            base_package, rebase_succeed, rebase_failed))
    mail_params = {'topic': topic, 'base_package': base_package}
    mail_params['mode'] = 'fixed_rebase'
    if base_package == 'HEAD':
        mail_params['mode'] = 'HEAD'
    send_rebase_results(mail_list, mail_params, rebase_succeed, rebase_failed)
    rebase_out_msg = 'integration framework web output start'
    if rebase_succeed:
        for comp, ver in rebase_succeed.items():
            rebase_out_msg += '\n### Rebase {} to {} Succeed ###'.format(comp, ver)
    if rebase_skipped:
        for comp, ver in rebase_skipped.items():
            rebase_out_msg += '\n### No need to rebase {} as {} ###'.format(comp, ver)
    if rebase_failed:
        for comp, ver in rebase_failed.items():
            rebase_out_msg += '\n*** Rebase {} to {} Failed ***'.format(comp, ver)
        print('Not able to rebase all components: {}'.format(rebase_failed))
    rebase_out_msg += '\nintegration framework web output end'
    print(rebase_out_msg)
    if rebase_failed:
        return False
    return True


def clear_and_rebase_file(rest, change_no, file_path, env_hash):
    env_change = {}
    if file_path:
        try:
            env_change = rest.get_file_change(file_path, change_no)
        except Exception:
            print('Cannot find {0} for {1}'.format(file_path, change_no))

    config_yaml_change = {}
    try:
        config_yaml_change = rest.get_file_change('config.yaml', change_no)
    except Exception:
        print('Cannot find config.yaml for %s', change_no)
    print('Env change {}'.format(env_change))
    # Get current ENV changes
    if ('new_diff' in env_change and env_change['new_diff']) \
            or ('new_diff' in config_yaml_change and config_yaml_change['new_diff']) \
            or ('old_diff' in config_yaml_change and config_yaml_change['old_diff']):
        env_change_list = []
        env_change_dict = dict()
        if 'new_diff' in env_change and env_change['new_diff']:
            env_change = env_change['new_diff']
            env_change = env_change.strip()
            env_change_list = shlex.split(env_change)
            for line in env_change_list:
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_change_dict[key] = value
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
        rebase_result = False
        try:
            if env_hash != 'HEAD':
                rest.rebase(change_no, env_hash)
            else:
                rest.rebase(change_no)
            rebase_result = True
        except Exception as e:
            print('Change cannot be rebased, reason: {}')
            print(str(e))
        # add new env entry
        print('add new env for change {}'.format(change_no))
        change_map = {}
        if env_change_list:
            env_path = get_env_repo.get_env_repo_info(rest, change_no)[1]
            if env_path:
                base_env = rest.get_file_content(env_path, change_no)
                change_map = env_changes.create_file_change_by_env_change(
                    env_change_list,
                    base_env,
                    file_path)
            # update config.yaml content
            change_map.update(env_changes.create_config_yaml_by_env_change(
                env_change_dict,
                rest,
                change_no)[0])
        if ('new_diff' in config_yaml_change and config_yaml_change['new_diff']) \
                or ('old_diff' in config_yaml_change and config_yaml_change['old_diff']):
            # get changed config_yaml dict
            change_map.update(env_changes.create_config_yaml_by_content_change(
                rest,
                config_yaml_change['old'],
                config_yaml_change['new'],
                change_no))
        for key, value in change_map.items():
            rest.add_file_to_change(change_no, key, value)
        rest.publish_edit(change_no)
        if not rebase_result:
            raise Exception('Change {} rebase failed, add back ENV file content'.format(change_no))
    else:
        raise Exception('Change {} no modification in config.yaml or ENV file'.format(change_no))


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
                           base_package, gitlab_info_path='', config_yaml_dict={}):
    op = RootChange(rest, root_change)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    mail_list = get_mail_list(comp_change_list, int_change, root_change, rest)
    if base_package == 'HEAD':
        update_with_rebase_info(rest, root_change, 'with-zuul-rebase')
        rest.review_ticket(int_change, 'use_default_base')
        rebase_result = rebase_by_load(rest, root_change, base_package,
                                       gitlab_info_path=gitlab_info_path,
                                       mail_list=mail_list,
                                       config_yaml_dict=config_yaml_dict)
    else:
        update_with_rebase_info(rest, root_change, 'without-zuul-rebase')
        # get last package if multi pacakges
        base_list = base_package.split(',')
        for base_pkg_name in base_list:
            ver_partten = '.'.join(base_pkg_name.split('.')[0:2])
            if ver_partten == base_pkg_name:
                ver_partten = base_pkg_name.split('_')[0]
            rest.review_ticket(
                int_change,
                'update_base:{},{}'.format(ver_partten, base_pkg_name))
        extra_bases = []
        print('Base_package is {}'.format(base_package))
        if ',' in base_package:
            base_package = wft_tools.get_newer_base_load(base_list)
            print('Last base_package is {}'.format(base_package))
            base_list.remove(base_package)
            extra_bases = base_list
        rebase_result = rebase_by_load(rest, root_change, base_package,
                                       gitlab_info_path=gitlab_info_path,
                                       mail_list=mail_list,
                                       extra_bases=extra_bases,
                                       config_yaml_dict=config_yaml_dict)
    return rebase_result


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
    print('rebase_succeed info: {}'.format(rebase_succeed))
    print('rebase_failed info: {}'.format(rebase_failed))
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


def get_config_yaml_dict(comp_config):
    config_yaml_dict = {}
    if comp_config:
        comp_config_dict = {}
        with open(comp_config, 'r') as fr:
            comp_config_dict = yaml.load(fr.read(), Loader=yaml.Loader)
        if 'config_yaml' in comp_config_dict:
            config_yaml_dict = comp_config_dict['config_yaml']
    print('Config yaml dict: {}'.format(config_yaml_dict))
    return config_yaml_dict


def run(root_change, gerrit_info_path,
        gitlab_info_path='', base_package='HEAD', database_info_path=None, comp_config=''):
    rest = init_gerrit_rest(gerrit_info_path)
    update_depends.remove_meta5g_change(rest, root_change)
    config_yaml_dict = get_config_yaml_dict(comp_config)
    rebase_result = switch_with_rebase_mod(root_change, rest, base_package, gitlab_info_path, config_yaml_dict)
    update_depends.add_interface_bb_to_root(rest, root_change)
    origin_msg = rest.get_commit(root_change)['message']
    msg = " ".join(origin_msg.split("\n"))
    reg = re.compile(r'%JR=(\w+-\d+)')
    jira_ticket = reg.search(msg).groups()[0]
    if ',' in base_package:
        base_list = base_package.split(',')
        base_package = ''
        for base in base_list:
            wft_name = wft_tools.get_wft_release_name(base)
            base_package = base_package + wft_name + ','
        base_package = base_package[:-1]
    if base_package != 'HEAD' and ',' not in base_package and 'SBTS' not in base_package:
        base_package = wft_tools.get_wft_release_name(base_package)
    if database_info_path:
        skytrack_database_handler.update_integration_mode(
            database_info_path=database_info_path,
            issue_key=jira_ticket,
            integration_mode='HEAD' if base_package == 'HEAD' else 'FIXED_BASE',
            fixed_build=base_package
        )
        skytrack_database_handler.update_events(
            database_info_path=database_info_path,
            integration_name=jira_ticket,
            description='Integration mode switch to {0}'.format(base_package) if
            base_package == "HEAD" else 'Integration mode switch to fixed base mode, base load: {0}'
            .format(base_package),
            highlight=True
        )
    if not rebase_result:
        sys.exit(213)


if __name__ == '__main__':
    fire.Fire()
