from api import gerrit_rest
import fire
from mod import integration_change as inte_change
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class OperateIntegrationChange(object):
    def __init__(self, gerrit_info_path, integration_change):
        self.rest = gerrit_rest.init_from_yaml(gerrit_info_path)
        self.inte_change = inte_change.ManageChange(self.rest, integration_change)
        self.inte_change_no = integration_change

    def remove(self, component_change):
        commit_msg_obj = inte_change.IntegrationCommitMessage(self.inte_change)
        to_remove = inte_change.IntegrationChange(self.rest, component_change)

        commit_msg_obj.remove_depends(to_remove)
        commit_msg_obj.remove_ric(to_remove)
        commit_msg_obj.remove_depends_on(to_remove)

        try:
            self.rest.delete_edit(self.inte_change_no)
        except Exception as e:
            print(e)

        self.rest.change_commit_msg_to_edit(self.inte_change_no, commit_msg_obj.get_msg())
        self.rest.publish_edit(self.inte_change_no)

    def add(self, component_change):
        commit_msg_obj = inte_change.IntegrationCommitMessage(self.inte_change)
        to_add = inte_change.IntegrationChange(self.rest, component_change)

        commit_msg_obj.add_depends(to_add)
        commit_msg_obj.add_ric(to_add)
        commit_msg_obj.add_depends_on(to_add)

        try:
            self.rest.delete_edit(self.inte_change_no)
        except Exception as e:
            print(e)

        self.rest.change_commit_msg_to_edit(self.inte_change_no, commit_msg_obj.get_msg())
        self.rest.publish_edit(self.inte_change_no)


if __name__ == '__main__':
    fire.Fire(OperateIntegrationChange)
