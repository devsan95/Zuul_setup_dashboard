import re
import fire
import json
import shlex
from pprint import pprint
from requests.structures import CaseInsensitiveDict

import skytrack_database_handler
import rebase_env
import rebase_interface
from api import gerrit_api
from api import gerrit_rest


def get_change_list_from_comments(info):
    json_re = re.compile(r'Tickets-List: ({.*})')
    for msg in reversed(info['messages']):
        result_list = json_re.findall(msg['message'])
        if len(result_list) > 0:
            return json.loads(result_list[-1])
    return None


def check_user_label_from_detail(detail_json, username, label):
    value = 0
    if 'labels' in detail_json:
        label_dict = CaseInsensitiveDict(detail_json['labels'])
        if label in label_dict:
            if 'all' in label_dict[label]:
                all_labels = label_dict[label]['all']
                for lab in all_labels:
                    if lab['username'] == username:
                        if 'value' in lab:
                            value = lab['value']
                        else:
                            print("ERROR: {} value missing!".format(label))
                            value = 0
                        break
    return value


def getting_env_check_result(rest, change_no, username):
    change_detail = rest.get_detailed_ticket(change_no)
    return check_user_label_from_detail(change_detail, username, 'Verified')


def run(gerrit_info_path, change_no,
        ssh_gerrit_server=None, ssh_gerrit_port=None,
        ssh_gerrit_user=None, ssh_gerrit_key=None,
        auto_reexperiment=True,
        change_info=None, database_info_path=None):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    use_ssh = False
    if ssh_gerrit_key and ssh_gerrit_port \
            and ssh_gerrit_server and ssh_gerrit_user:
        use_ssh = True
        print('SSH used')
    comp_name = 'env'
    change_info_dict = {}
    change_info = change_info
    if change_info is not None:
        change_info = change_info.strip()
        change_info_list = shlex.split(change_info)
        for line in change_info_list:
            print(line)
            if '=' in line:
                key, value = line.strip().split('=', 1)
                change_info_dict[key] = value
    if 'bb_version' in change_info_dict:
        comp_name = change_info_dict['bb_version'].split('_', 1)[0]
    if comp_name == 'env':
        env_change = change_no
        if rest.get_change(change_no)['project'] not in ['MN/5G/COMMON/integration', 'MN/5G/COMMON/env']:
            env_change = skytrack_database_handler.get_env_change(
                change_no,
                database_info_path,
                gerrit_info_path
            )
        rebase_env.run(
            gerrit_info_path,
            env_change,
            change_info=change_info,
            database_info_path=database_info_path
        )
    else:
        rebase_interface.run(
            gerrit_info_path, change_no, change_info=change_info_dict, database_info_path=database_info_path)

    change_detail = rest.get_detailed_ticket(change_no)
    # 2 detect integration label. if label is ok then quit.
    print('Check if change {} need reintegration'.format(change_no))
    print(rest.get_change_address(change_no))
    username = rest.user
    if use_ssh:
        username = ssh_gerrit_user

    label_value = check_user_label_from_detail(change_detail,
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

    # 3 relabel env with integrated-1 label
    print('relabel change {}'.format(change_no))
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

    change_detail = rest.get_detailed_ticket(change_no)
    label_value = check_user_label_from_detail(change_detail,
                                               username, 'Integrated')
    if label_value == -1:
        print('Success')
    else:
        print('Fail')
        raise Exception('Label integrated -1 failed')

    # 4 find all changes
    print('Looking for all changes...')
    change_list = get_change_list_from_comments(change_detail)
    print('Changes are:')
    pprint(change_list)

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
