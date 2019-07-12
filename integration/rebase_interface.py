import sys
import fire

import skytrack_database_handler
from api import gerrit_rest
from operate_commit_message import OperateCommitMessage
from mod.integration_change import RootChange


mandotory_info = ['bb_version', 'commit_id']


def update_interfaces_refs(rest, comp_change_list, comp_name, commit_id):
    interfaces_change = rest.query_ticket('commit:{0}'.format(commit_id))[0]['_number']
    revisions = rest.query_ticket(interfaces_change, obtained='ALL_REVISIONS')[0]['revisions']
    refs = ''
    for rev in revisions:
        if rev == commit_id:
            refs = revisions[rev]['ref']
            break
    if refs:
        for change in comp_change_list:
            rest.review_ticket(change, '{0}:{1}'.format(comp_name, refs))
    else:
        print ['WARN: Can not get interfaces refs']


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
    update_interfaces_refs(rest, comp_change_list, comp_name, change_info['commit_id'])
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
