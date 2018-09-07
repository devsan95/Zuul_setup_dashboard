#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
from pprint import pprint
import json
import re
import fire
import urllib3
from requests.structures import CaseInsensitiveDict

from api import gerrit_api
from api import gerrit_rest

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def check_user_label_from_detail(detail_json, username, label):
    value = 0
    if 'labels' in detail_json:
        label_dict = CaseInsensitiveDict(detail_json['labels'])
        if label in label_dict:
            if 'all' in label_dict[label]:
                all_labels = label_dict[label]['all']
                for label in all_labels:
                    if label['username'] == username:
                        value = label['value']
                        break
    return value


def get_change_list_from_comments(info):
    json_re = re.compile(r'Tickets-List: ({.*})')
    for msg in reversed(info['messages']):
        result_list = json_re.findall(msg['message'])
        if len(result_list) > 0:
            return json.loads(result_list[-1])
    return None


def run(gerrit_info_path, change_no,
        ssh_gerrit_server=None, ssh_gerrit_port=None,
        ssh_gerrit_user=None, ssh_gerrit_key=None, auto_recheck=True):
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

    change_info = rest.get_detailed_ticket(change_no)
    # 1 detect integration label. if label is ok then quit.
    print('Check if change {} need reintegration'.format(change_no))
    print(rest.get_change_address(change_no))
    username = rest.user
    if use_ssh:
        username = ssh_gerrit_user

    label_value = check_user_label_from_detail(change_info,
                                               username, 'Integrated')
    if label_value == -1 or label_value == -2 or label_value == 2:
        raise Exception('Integrated is {} and \
                no need to do anything'.format(label_value))
    else:
        print('Integrated is {} and will relabel'.format(label_value))

    # 2 relabel
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

    # 3 find all changes
    print('Looking for all changes...')
    change_list = get_change_list_from_comments(change_info)
    print('Changes are:')
    pprint(change_list)

    if auto_recheck:
        # 4 recheck all changes
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


if __name__ == '__main__':
    fire.Fire(run)
