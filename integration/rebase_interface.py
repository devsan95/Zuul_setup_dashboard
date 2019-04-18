import sys
import fire

from api import gerrit_api
from api import gerrit_rest
from operate_commit_message import OperateCommitMessage
from mod.integration_change import RootChange


mandotory_info = ['bb_version', 'commit_id']


def run(gerrit_info_path, change_no,
        ssh_gerrit_server=None, ssh_gerrit_port=None,
        ssh_gerrit_user=None, ssh_gerrit_key=None,
        auto_recheck=False, auto_reexperiment=True, change_info=None):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    use_ssh = False
    if ssh_gerrit_key and ssh_gerrit_port \
            and ssh_gerrit_server and ssh_gerrit_user:
        use_ssh = True
        print('SSH used')
    op = RootChange(rest, change_no)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    for mandotory_param in mandotory_info:
        if mandotory_param not in change_info:
            print('Error , {} not in change info'.format(mandotory_param))
            sys.exit(2)
    comp_name = change_info['bb_version'].split('_', 1)[0]
    comp_ver = change_info['bb_version'].split('_', 1)[1]
    if use_ssh:
        gerrit_api.review_patch_set(ssh_gerrit_user, ssh_gerrit_server,
                                    change_no,
                                    [],
                                    'update_bb,{},bb,{}'.format(
                                        comp_name,
                                        change_info['commit_id']),
                                    ssh_gerrit_key, ssh_gerrit_port)
    else:
        rest.review_ticket(int_change, 'update_bb,{},bb,{}'.format(
            change_info['comp_name'], change_info['commit_id']))
    op_commit_msg = OperateCommitMessage(gerrit_info_path, change_no)
    op_commit_msg.update_interface_information(
        '{}-{}'.format(comp_name, comp_ver), change_info['commit_id'])
    if auto_recheck:
        # recheck
        print('not supported yet')
    if auto_reexperiment:
        # reexperiment
        print('reexperiment manager')
        rest.review_ticket(int_change, 'reexperiment')


if __name__ == '__main__':
    fire.Fire(run)
