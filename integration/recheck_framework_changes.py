import re
import fire
import time
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


def check_verified_status(rest, change_no, timeout):
    info_with_labels = rest.get_ticket(change_no, fields='LABELS')
    verified_result = False
    time_used = 0
    while time_used < timeout:
        try:
            verified_result = 'approved' in info_with_labels['labels']['Verified']
        except Exception:
            print("WARN: Cannot get Verified value from {}".format(verified_result))
        if verified_result:
            return
        else:
            print("Current verified status is {}".format(verified_result))
            print("Already wait {} mins".format(time_used))
            print("Waitting one more min to check the verified status")
            time.sleep(60)
            time_used += 1
            info_with_labels = rest.get_ticket(change_no, fields='LABELS')
    raise Exception("ERROR: {} mins exceed to wait verfied +1 for {}".format(timeout, change_no))


def run(gerrit_info_path, change_no, timeout=30):
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

    # wait <timeout> mins for verified+1 in change
    if timeout > 0:
        check_verified_status(rest, change_no, timeout)

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
