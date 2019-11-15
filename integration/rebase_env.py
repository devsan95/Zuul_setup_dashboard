#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import re
import shlex

import fire
import urllib3
from functools import partial

import skytrack_database_handler
from api import retry
from api import gerrit_rest, jira_api
from api import env_repo as get_env_repo
from mod import common_regex
from mod.integration_change import RootChange
from difflib import SequenceMatcher

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
    env_related = ['env/env-config.d/ENV', 'env-config.d/ENV', 'meta-ps-rel', 'meta-rcp']
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
        reg = common_regex.int_firstline_reg
        to_be_replaced = reg.search(msg).groups()[1]
        pattern = re.sub(r"\d+", r"\d+", to_be_replaced)
        reg = re.compile(r"({})".format(pattern.encode("utf-8")))
        result = reg.search('\n'.join(env_change_list))
        if result:
            to_replace = result.groups()[0]
        else:
            to_replace = find_new_version_by_distance(
                to_be_replaced, env_change_list)
            if not to_replace:
                raise Exception('Cannot find new version')
        if to_be_replaced == to_replace:
            return to_be_replaced, to_replace
        print(u"replace |{}| with |{}|...".format(to_be_replaced, to_replace))

        try:
            rest.delete_edit(change_no)
        except Exception as e:
            print('delete edit failed, reason:')
            print(str(e))

        new_msg = origin_msg.replace(to_be_replaced, to_replace)
        rest.change_commit_msg_to_edit(change_no, new_msg)
        rest.publish_edit(change_no)
        return to_be_replaced, to_replace
    except Exception as e:
        print(e)


def run(gerrit_info_path, change_no, change_info=None, database_info_path=None):
    env_change_list = []
    env_change = change_info
    if env_change is not None:
        env_change = env_change.strip()
        env_change_list = shlex.split(env_change)
        for line in env_change_list:
            print(line)
    # use rest gerrit user info to do the operation, and the ssh gerrit
    # user to do the labeling (to sync with zuul)
    # if no ssh gerrit info is provided then use rest user to do labeling
    print('Gathering infomation...')
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    root_msg = get_commit_msg(change_no, rest)
    auto_rebase = False if re.findall(r'<without-zuul-rebase>', root_msg) else True

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
                raise Exception(str(e))
        # add new env
        print('add new env for change {}'.format(change_no))
        old_env = rest.get_file_content(env_path, change_no)
        # update env/env-config.d/ENV content
        change_map = create_file_change_by_env_change(
            env_change_list,
            old_env,
            env_path
        )

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
            jira_op = jira_api.JIRAPI("autobuild_c_ou", "a4112fc4")
            jira_op.replace_issue_title(jira_ticket, old_str, new_str)
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
            rest.add_file_to_change(change_no, key, value)
        rest.publish_edit(change_no)


if __name__ == '__main__':
    fire.Fire(run)
