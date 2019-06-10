#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import fire
import urllib3

from api import gerrit_rest
from mod import integration_change as inte_change

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class OperateCommitMessage(object):
    def __init__(self, gerrit_info_path, root_change):
        self.rest = gerrit_rest.init_from_yaml(gerrit_info_path)
        self.root_change = inte_change.RootChange(self.rest, root_change)
        self.root_change_no = root_change
        self.all_changes = self.root_change.get_all_changes_by_comments(with_root=True)

    def update_interface_information(self, bb_version, commit_ID, comp_name):
        for change in self.all_changes:
            print('[Info] Going to update interface info for change: [{}]'.format(change))
            change_obj = inte_change.IntegrationChange(self.rest, change)
            if comp_name in change_obj.get_components():
                continue
            commit_msg_obj = inte_change.IntegrationCommitMessage(change_obj)
            commit_msg_obj.update_interface_info(bb_version, commit_ID, comp_name)
            try:
                self.rest.delete_edit(change)
            except Exception as e:
                print(e)
            self.rest.change_commit_msg_to_edit(change, commit_msg_obj.get_msg())
            self.rest.publish_edit(change)
            self.rest.review_ticket(change, 'update interface info')


if __name__ == '__main__':
    fire.Fire(OperateCommitMessage)
