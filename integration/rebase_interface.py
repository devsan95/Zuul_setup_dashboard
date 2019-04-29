import sys
import fire

from api import gerrit_rest
from operate_commit_message import OperateCommitMessage
from mod.integration_change import RootChange


mandotory_info = ['bb_version', 'commit_id']


def run(gerrit_info_path, change_no, change_info=None):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    op = RootChange(rest, change_no)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    for mandotory_param in mandotory_info:
        if mandotory_param not in change_info:
            print('Error , {} not in change info'.format(mandotory_param))
            sys.exit(2)
    comp_name = change_info['bb_version'].split('_', 1)[0]
    comp_ver = change_info['bb_version'].split('_', 1)[1]
    rest.review_ticket(int_change, 'update_bb,{},bb,{}'.format(
        change_info['comp_name'], change_info['commit_id']))
    op_commit_msg = OperateCommitMessage(gerrit_info_path, change_no)
    op_commit_msg.update_interface_information(
        '{}-{}'.format(comp_name, comp_ver),
        change_info['commit_id'], comp_name)


if __name__ == '__main__':
    fire.Fire(run)
