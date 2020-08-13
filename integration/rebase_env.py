#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import os
import re
import shlex
import subprocess
import fire
import yaml
import urllib3
from functools import partial

import skytrack_database_handler
from api import retry
from api import gerrit_rest, jira_api
from api import env_repo as get_env_repo
from api import config
from mod import common_regex
from mod.integration_change import RootChange
from mod.integration_change import IntegrationChange
from difflib import SequenceMatcher

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


CONF = config.ConfigTool()
CONF.load('jira')
JIRA_DICT = CONF.get_dict('jira3')

DEFAULT_JIRA_URL = JIRA_DICT['server']
DEFAULT_USER = JIRA_DICT['user']
DEFAULT_PASSWD = JIRA_DICT['password']


def create_config_yaml_by_env_change(env_change_split, rest, change_id, config_yaml_file='config.yaml'):
    change_content = rest.get_file_change(config_yaml_file, change_id)
    old_config_yaml = yaml.safe_load(change_content['old'])
    if not old_config_yaml:
        try:
            old_config_yaml = yaml.safe_load(rest.get_file_content(config_yaml_file, change_id))
        except Exception:
            print('Cannot find {} in {}'.format(config_yaml_file, change_id))
    if not old_config_yaml:
        return {}
    changed = False
    if env_change_split:
        # update based on old config.yaml
        for component_info in old_config_yaml['components'].values():
            if 'env_key' in component_info and component_info['env_key']:
                comp_env_key = component_info['env_key']
                for env_line in env_change_split:
                    if '=' in env_line:
                        key, value = env_line.split('=', 1)
                        if key == comp_env_key:
                            if value != component_info['version'] and value != component_info['commit']:
                                print('Update {} to {} in {}'.format(key, value, config_yaml_file))
                                if component_info['commit'] == component_info['version']:
                                    component_info['commit'] = value
                                component_info['version'] = value
                                changed = True
    if changed:
        return {config_yaml_file: yaml.safe_dump(old_config_yaml)}
    return {}


def create_file_change_by_env_change(env_change_split, file_content, filename):
    lines = file_content.split('\n')
    for i, line in enumerate(lines):
        if '=' in line:
            key2, value2 = line.strip().split('=', 1)
            for env_line in env_change_split:
                if '=' in env_line:
                    key, value = env_line.split('=', 1)
                    if key.strip() == key2.strip():
                        lines[i] = key2 + '=' + value
    for env_line in env_change_split:
        if env_line.startswith('#'):
            lines.append(env_line)
    ret_dict = {filename: '\n'.join(lines)}
    return ret_dict


def clear_change(rest, change_id, only_clear_env=True):
    env_related = ['env/env-config.d/ENV', 'env-config.d/ENV', 'meta-ps-rel', 'meta-rcp', 'config.yaml']
    flist = rest.get_file_list(change_id)
    for file_path in flist:
        file_path = file_path.split('\n', 2)[0]
        if only_clear_env:
            if file_path in env_related:
                rest.restore_file_to_change(change_id, file_path)
        else:
            if file_path != '/COMMIT_MSG':
                rest.restore_file_to_change(change_id, file_path)
    rest.publish_edit(change_id)


def get_commit_msg(change_no, rest):
    origin_msg = retry.retry_func(
        retry.cfn(rest.get_commit, change_no),
        max_retry=10, interval=3
    )['message']
    return origin_msg


def find_new_version_by_distance(old_version, env_change_list):
    ratio = 0
    ret_version = None
    for line in env_change_list:
        values = line.split('=')
        if len(values) > 1:
            new_version = values[1]
            new_ratio = SequenceMatcher(None, old_version, new_version).ratio()
            if new_ratio > ratio:
                ratio = new_ratio
                ret_version = new_version
    return ret_version


def change_message_by_env_change(change_no, env_change_list, rest):
    try:
        origin_msg = get_commit_msg(change_no, rest)
        msg = " ".join(origin_msg.split("\n"))
        version_reg = re.compile(r'Version Keyword: <(.*)>')
        version_entry_search = version_reg.search(origin_msg)
        version_entry = version_entry_search.groups()[0] if version_entry_search else None
        reg = common_regex.int_firstline_reg
        to_be_replaced = reg.search(msg).groups()[1]
        to_be_replaced_string = '<{0}>'.format(to_be_replaced)
        to_be_replace_fifi = common_regex.fifi_reg.search(origin_msg).groups()[0]
        gnb_first_line = common_regex.gnb_firstline_reg.search(msg)
        pattern = re.sub(r"\d+", r"\d+", to_be_replaced)
        reg = re.compile(r"({})".format(pattern.encode("utf-8")))
        result = reg.search('\n'.join(env_change_list))

        to_replace = ''
        if version_entry:
            for line in env_change_list:
                if version_entry == line.split('=')[0]:
                    to_replace = line.split('=')[1]
                    break
        else:
            if result and not to_replace.strip():
                to_replace = result.groups()[0]
            if not to_replace.strip():
                to_replace = find_new_version_by_distance(
                    to_be_replaced, env_change_list)
            if not to_replace.strip():
                raise Exception('Cannot find new version')
        to_replace_string = '<{0}>'.format(to_replace)
        if to_be_replaced_string == to_replace_string:
            return to_be_replaced, to_replace
        print(u"replace |{}| with |{}|...".format(to_be_replaced_string, to_replace_string))

        try:
            rest.delete_edit(change_no)
        except Exception as e:
            print('delete edit failed, reason:')
            print(str(e))
        new_msg = origin_msg.replace(to_be_replaced_string, to_replace_string).replace(
            '%FIFI={0}'.format(to_be_replace_fifi), '%FIFI={0}'.format(to_replace))
        new_msg = new_msg.replace(gnb_first_line.groups()[3], to_replace) if gnb_first_line else new_msg
        rest.change_commit_msg_to_edit(change_no, new_msg)
        rest.publish_edit(change_no)
        return to_be_replaced, to_replace
    except Exception as e:
        print(e)


def get_current_ps(rest, change_no):
    current_ps = None
    env_content = rest.get_file_content("env/env-config.d/ENV", change_no)
    env_content_list = shlex.split(env_content)
    for line in env_content_list:
        if re.match(r'^ENV_PS_REL *=', line):
            current_ps = line.strip().split('=', 1)[1]
            print("current ps: {}".format(current_ps))
            break
    return current_ps


def need_vcf_diff(current_ps, change_info_dict):
    if "ENV_PS_REL" in change_info_dict:
        if current_ps == change_info_dict["ENV_PS_REL"]:
            print("PS version no change.")
            return False
        else:
            print("PS version changed need run vcf_diff.bash.")
            return True
    else:
        print("PS version no change.")
        return False


def call_vcf_diff(current_ps, new_ps):
    param_dict = {
        "PLATFORM_MODULES": "FCTL ASCB FCTM",
        "OLD_PLATFORM": current_ps,
        "NEW_PLATFORM": new_ps
    }
    env = os.environ
    env.update(param_dict)
    if not os.path.exists(os.path.join(os.environ['WORKSPACE'], "ci_scripts")):
        process = subprocess.Popen("${get_ci_scripts}", shell=True, cwd=os.environ['WORKSPACE'])
        process.wait()
    process = subprocess.Popen(
        "{}/ci_scripts/tools/vcf_diff/vcf_diff.bash".format(os.environ['WORKSPACE']),
        shell=True,
        env=env
    )
    process.wait()
    if process.returncode == 0:
        print("vcf_diff check passed.")
        return "SUCCESS"
    else:
        print("vcf_diff check failed.")
        return "FAILURE"


def update_component_config_yaml(env_change_list, rest, change_no, config_yaml_dict):
    change_file_dict = {}
    op = RootChange(rest, change_no)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    for comp_change in comp_change_list:
        int_change_obj = IntegrationChange(rest, comp_change)
        comp_project = int_change_obj.get_project()
        if comp_project in config_yaml_dict:
            local_config_yaml = config_yaml_dict[comp_project]
            change_file_dict[comp_change] = create_config_yaml_by_env_change(
                env_change_list, rest, comp_change, config_yaml_file=local_config_yaml)
    for comp_change, file_dict in change_file_dict.items():
        for key, value in file_dict.items():
            print('update file {} in {}'.format(key, comp_change))
            print(value)
            rest.add_file_to_change(comp_change, key, value)
        rest.publish_edit(comp_change)
    return change_file_dict


def run(gerrit_info_path, change_no, comp_config, change_info=None, database_info_path=None):
    env_change_list = []
    commit_msg_update = False
    env_change_dict = dict()
    env_change = change_info
    if env_change is not None:
        env_change = env_change.strip()
        env_change_list = shlex.split(env_change)
        for line in env_change_list:
            print(line)
            if '=' in line:
                key, value = line.strip().split('=', 1)
                env_change_dict[key] = value
    config_yaml_dict = {}
    if comp_config:
        comp_config_dict = {}
        with open(comp_config, 'r') as fr:
            comp_config_dict = yaml.load(fr.read(), Loader=yaml.Loader)
        if 'config_yaml' in comp_config_dict:
            config_yaml_dict = comp_config_dict['config_yaml']
    # use rest gerrit user info to do the operation, and the ssh gerrit
    # user to do the labeling (to sync with zuul)
    # if no ssh gerrit info is provided then use rest user to do labeling
    print('Gathering infomation...')
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    root_msg = get_commit_msg(change_no, rest)
    auto_rebase = False if re.findall(r'<without-zuul-rebase>', root_msg) else True
    current_ps = get_current_ps(rest, change_no)
    if need_vcf_diff(current_ps, env_change_dict):
        check_result = call_vcf_diff(current_ps, env_change_dict["ENV_PS_REL"])
        if "I_KNOW_WHAT_I_AM_DOING" in root_msg and check_result == "FAILURE":
            commit_msg_update = True
            new_commit_msg = re.sub(r'I_KNOW_WHAT_I_AM_DOING\n', '', root_msg)
            new_commit_msg = re.sub(r'(\n)*Change-Id: [a-zA-Z0-9]{41}(\n)*$', '', new_commit_msg)

    env_path = get_env_repo.get_env_repo_info(rest, change_no)[1]

    # 1 try rebase env change (if fail then pass)
    if auto_rebase and not env_change:
        print('rebase the change {}'.format(change_no))
        try:
            rest.rebase(change_no)
        except Exception as e:
            print('Change cannot be rebased, reason:')
            print(str(e))

    # 1.5 try modify env file
    if env_change:
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
        if auto_rebase:
            print('rebase the change {}'.format(change_no))
            try:
                rest.rebase(change_no)
            except Exception as e:
                print('Change cannot be rebased, reason:')
                print(str(e))
        # add new env
        print('add new env for change {}'.format(change_no))
        old_env = rest.get_file_content(env_path, change_no)
        # update env/env-config.d/ENV content
        change_map = create_file_change_by_env_change(
            env_change_list,
            old_env,
            env_path
        )

        # update config.yaml content
        change_map.update(create_config_yaml_by_env_change(
            env_change_list,
            rest,
            change_no))
        update_component_config_yaml(
            env_change_list,
            rest,
            change_no,
            config_yaml_dict)
        print('Change map: {}'.format(change_map))

        # get root ticket
        root_change = skytrack_database_handler.get_specified_ticket(
            change_no,
            database_info_path,
            gerrit_info_path
        )
        # replace commit message
        op = RootChange(rest, root_change)
        commits = op.get_all_changes_by_comments()
        change_message = partial(change_message_by_env_change, env_change_list=env_change_list, rest=rest)
        map(change_message, commits)
        old_str, new_str = change_message(root_change)
        # replace jira title.
        try:
            origin_msg = get_commit_msg(change_no, rest)
            msg = " ".join(origin_msg.split("\n"))
            reg = re.compile(r'%JR=(\w+-\d+)')
            jira_ticket = reg.search(msg).groups()[0]
            jira_op = jira_api.JIRAPI(user=DEFAULT_USER, passwd=DEFAULT_PASSWD,
                                      server=DEFAULT_JIRA_URL)
            jira_title = jira_op.get_issue_title(jira_ticket)
            if old_str in jira_title:
                jira_op.replace_issue_title(jira_ticket, old_str, new_str)
            else:
                jira_title_re = common_regex.jira_title_reg.search(jira_title)
                if jira_title_re:
                    jira_op.replace_issue_title(jira_ticket, jira_title_re.groups()[4], new_str)
        except Exception as e:
            print('Jira update error')
        if database_info_path:
            skytrack_database_handler.update_events(
                database_info_path=database_info_path,
                integration_name=jira_ticket,
                description="Integration Topic Change To {0}".format(new_str),
                highlight=True
            )
        for key, value in change_map.items():
            print('update file {}'.format(key))
            print(value)
            rest.add_file_to_change(change_no, key, value)
        rest.publish_edit(change_no)
        if commit_msg_update:
            rest.set_commit_message(change_no, content=new_commit_msg)


if __name__ == '__main__':
    fire.Fire(run)
