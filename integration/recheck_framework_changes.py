import re
import fire
from pprint import pprint
from requests.structures import CaseInsensitiveDict

from api import gerrit_rest
from mod.integration_change import RootChange


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


def run(gerrit_info_path, change_no):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    op = RootChange(rest, change_no)
    username = rest.user

    commit_msg = rest.get_commit(change_no)['message']
    if not re.search(r'%JR=SCM', commit_msg):
        print('{} is not from integration framework'.format(change_no))
        return
    change_files = rest.get_file_list(change_no)
    if 'env/env-config.d/ENV' not in change_files and 'config.yaml' not in change_files:
        print('{} is not contains ENV and config.yaml file'.format(change_no))
        return

    # find all changes
    print('Looking for all changes...')
    change_list = op.get_all_changes_by_comments()
    print('Changes are:')
    pprint(change_list)

    print('recheck all changes')
    if change_list:
        sorted(change_list)
        for op_change_no in change_list:
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
