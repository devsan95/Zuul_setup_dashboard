import sys
import fire

import skytrack_database_handler
from api import gerrit_rest
from operate_commit_message import OperateCommitMessage
from mod.integration_change import RootChange


mandotory_info = ['bb_version', 'commit_id']


def run(gerrit_info_path, change_no, change_info=None, database_info_path=None):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    op = RootChange(rest, change_no)
    jira_ticket = op.get_jira_id()
    comp_change_list, int_change = op.get_components_changes_by_comments()
    for mandotory_param in mandotory_info:
        if mandotory_param not in change_info:
            print('Error , {} not in change info'.format(mandotory_param))
            sys.exit(2)
    comp_name = change_info['bb_version'].split('_', 1)[0]
    comp_ver = change_info['bb_version'].split('_', 1)[1]
    rest.review_ticket(int_change, 'update_bb:{},bb,{}'.format(
        change_info['comp_name'], comp_ver))
    op_commit_msg = OperateCommitMessage(gerrit_info_path, change_no)
    op_commit_msg.update_interface_information(
        '{}-{}'.format(comp_name, comp_ver),
        change_info['commit_id'], comp_name)
    if database_info_path:
        skytrack_database_handler.update_events(
            database_info_path=database_info_path,
            integration_name=jira_ticket,
            description="Integration Topic Change To {0}".format(change_info['bb_version']),
            highlight=True
        )


if __name__ == '__main__':
    fire.Fire(run)
