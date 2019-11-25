#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import fire
import urllib3

from api import gerrit_rest
from mod import integration_change as inte_change
from mod import common_regex

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
            skip_update = False
            for change_comp in change_obj.get_components():
                if comp_name == change_comp:
                    print('[Info] Skip  self ticket {}'.format(change))
                    skip_update = True
                    continue
                if change_comp.startswith('interfaces'):
                    print('[Info] Skip  interfaces ticket {}'.format(change))
                    skip_update = True
                    continue
            if skip_update:
                continue
            commit_msg_obj = inte_change.IntegrationCommitMessage(change_obj)
            commit_msg_obj.update_interface_info(bb_version, commit_ID, comp_name)
            try:
                self.rest.delete_edit(change)
            except Exception as e:
                print(e)
            try:
                self.rest.change_commit_msg_to_edit(change, commit_msg_obj.get_msg())
            except Exception as e:
                if "New commit message cannot be same as existing commit message" in str(e):
                    pass
                else:
                    raise Exception(e)
            self.rest.publish_edit(change)
            self.rest.review_ticket(change, 'update interface info')

    def update_topic(self, to_replace):
        to_be_replaced = ''
        for change in self.all_changes:
            print change
            try:
                origin_msg = self.rest.get_commit(change)['message']
                msg = " ".join(origin_msg.split("\n"))
                reg = common_regex.int_firstline_reg
                to_be_replaced = reg.search(msg).groups()[1]
                if to_be_replaced == to_replace:
                    continue
                print(u"replace |{}| with |{}|...".format(to_be_replaced, to_replace))
                try:
                    self.rest.delete_edit(change)
                except Exception as e:
                    print('delete edit failed, reason:')
                    print(str(e))

                new_msg = origin_msg.replace(to_be_replaced, to_replace)
                self.rest.change_commit_msg_to_edit(change, new_msg)
                self.rest.publish_edit(change)
            except Exception as e:
                print(e)
        return to_be_replaced, to_replace


if __name__ == '__main__':
    fire.Fire(OperateCommitMessage)
