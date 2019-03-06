#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import json
import re
import shlex
from pprint import pprint

import fire
import urllib3
from requests.structures import CaseInsensitiveDict
from functools import partial

from api import gerrit_api, retry
from api import gerrit_rest, jira_api
from mod.integration_change import RootChange
from difflib import SequenceMatcher

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def check_user_label_from_detail(detail_json, username, label):
    value = 0
    if 'labels' in detail_json:
        label_dict = CaseInsensitiveDict(detail_json['labels'])
        if label in label_dict:
            if 'all' in label_dict[label]:
                all_labels = label_dict[label]['all']
                for lab in all_labels:
                    if lab['username'] == username:
                        value = lab['value']
                        break
    return value


def get_change_list_from_comments(info):
    json_re = re.compile(r'Tickets-List: ({.*})')
    for msg in reversed(info['messages']):
        result_list = json_re.findall(msg['message'])
        if len(result_list) > 0:
            return json.loads(result_list[-1])
    return None


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


def clear_change(rest, change_id):
    flist = rest.get_file_list(change_id)
    for file_path in flist:
        file_path = file_path.split('\n', 2)[0]
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
        reg = re.compile(r'<(.*?)> on <(.*?)> of <(.*?)> topic')
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


def run(gerrit_info_path, change_no,
        ssh_gerrit_server=None, ssh_gerrit_port=None,
        ssh_gerrit_user=None, ssh_gerrit_key=None,
        auto_rebase=False, auto_recheck=True, auto_reexperiment=True,
        env_change=None):
    env_change_list = []
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
    use_ssh = False

    if ssh_gerrit_key and ssh_gerrit_port \
            and ssh_gerrit_server and ssh_gerrit_user:
        use_ssh = True
        print('SSH used')
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
        print('rebase the change {}'.format(change_no))
        try:
            rest.rebase(change_no)
        except Exception as e:
            print('Change cannot be rebased, reason:')
            print(str(e))
        # add new env
        print('add new env for change {}'.format(change_no))
        old_env = rest.get_file_content('env-config.d/ENV', change_no)
        change_map = create_file_change_by_env_change(
            env_change_list,
            old_env,
            'env-config.d/ENV')

        # replace commit message
        op = RootChange(rest, change_no)
        commits = op.get_all_changes_by_comments()
        change_message = partial(change_message_by_env_change, env_change_list=env_change_list, rest=rest)
        map(change_message, commits)
        old_str, new_str = change_message(change_no)
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

        for key, value in change_map.items():
            rest.add_file_to_change(change_no, key, value)
        rest.publish_edit(change_no)

    change_info = rest.get_detailed_ticket(change_no)
    # 2 detect integration label. if label is ok then quit.
    print('Check if change {} need reintegration'.format(change_no))
    print(rest.get_change_address(change_no))
    username = rest.user
    if use_ssh:
        username = ssh_gerrit_user

    label_value = check_user_label_from_detail(change_info,
                                               username, 'Integrated')
    if label_value == -1 or label_value == -2:
        print('Integrated is {} and '
              'no need to do anything'.format(label_value))
    elif label_value == 2:
        print('Integrated is {} and '
              'no need to do anything'.format(label_value))
        return
    else:
        print('Integrated is {} and will relabel'.format(label_value))

    # 3 relabel and reintegrate env
    print('relabel change {} and reintegrate'.format(change_no))
    if use_ssh:
        gerrit_api.review_patch_set(ssh_gerrit_user, ssh_gerrit_server,
                                    change_no,
                                    ['Integrated=-1'],
                                    'relabel for new patchset',
                                    ssh_gerrit_key, ssh_gerrit_port)
    else:
        rest.review_ticket(change_no, 'relabel for new patchset',
                           {'Integrated': -1})

    print('Check if label is successfully given')

    change_info = rest.get_detailed_ticket(change_no)
    label_value = check_user_label_from_detail(change_info,
                                               username, 'Integrated')
    if label_value == -1:
        print('Success')
    else:
        print('Fail')
        raise Exception('Label integrated -1 failed')

    rest.review_ticket(change_no, 'reintegrate')

    # 4 find all changes
    print('Looking for all changes...')
    change_list = get_change_list_from_comments(change_info)
    print('Changes are:')
    pprint(change_list)

    if auto_recheck:
        # 5 recheck all changes
        print('recheck all changes')
        if 'tickets' in change_list and change_list['tickets']:
            comp_list = change_list['tickets']
            sorted(comp_list)
            for op_change_no in comp_list:
                op_change_info = rest.get_detailed_ticket(op_change_no)
                # judge if it is before check, in check or after check
                op_check = check_user_label_from_detail(
                    op_change_info, username, 'verified')
                if op_check == -1 or op_check == 1:
                    # check is over
                    print('Change {} is done with check, '
                          'just recheck it'.format(op_change_no))
                    rest.review_ticket(op_change_no, 'recheck')
                else:
                    # check is running or not starting
                    # abandon to abort check
                    print('Change {} is not done with check, '
                          'dequeue and recheck'.format(op_change_no))
                    rest.review_ticket(op_change_no, 'abandon to reset check')
                    rest.abandon_change(op_change_no)
                    rest.restore_change(op_change_no)
                    rest.review_ticket(op_change_no, 'recheck')
                print(rest.get_change_address(op_change_no))

    # 6 reintegrate integration change
    if 'manager' in change_list and change_list['manager']:
        inte_change_no = change_list['manager']
        print('handle integration change {}'.format(inte_change_no))
        print(rest.get_change_address(inte_change_no))
        # abandon to abort experiment and integrate
        rest.review_ticket(inte_change_no,
                           'abandon to abort experiment and integrate')
        rest.abandon_change(inte_change_no)
        rest.restore_change(inte_change_no)
        if auto_reexperiment:
            # reexperiment
            print('reexperiment manager')
            rest.review_ticket(inte_change_no, 'reexperiment')


if __name__ == '__main__':
    fire.Fire(run)
