import fire
import json
import urllib3

from api import gerrit_rest
from api import mysql_api
from mod import integration_change as inte_change

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class OperateIntegrationChange(object):
    def __init__(self, gerrit_info_path, integration_change, mysql_info_path):
        self.rest = gerrit_rest.init_from_yaml(gerrit_info_path)
        self.inte_change = inte_change.ManageChange(
            self.rest, integration_change)
        self.inte_change_no = integration_change
        self.mysql = mysql_api.init_from_yaml(mysql_info_path, 'skytrack')
        self.mysql.init_database('skytrack')
        self.root_change = self.get_root_change(integration_change)

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

        self.rest.change_commit_msg_to_edit(
            self.inte_change_no, commit_msg_obj.get_msg())
        self.rest.publish_edit(self.inte_change_no)
        self.rest.review_ticket(component_change, 'detached')
        self.mysql.update_info(
            table='t_commit_component',
            replacements={
                'is_detached': 1
            },
            conditions={'`change`': component_change}
        )
        self.add_ticket_list(self.root_change, component_change, 'remove')

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

        self.rest.change_commit_msg_to_edit(
            self.inte_change_no, commit_msg_obj.get_msg())
        self.rest.publish_edit(self.inte_change_no)
        if self.mysql.executor(
                'SELECT * FROM t_commit_component where `change` = {0}'.format(
                    component_change),
                output=True):
            self.mysql.update_info(
                table='t_commit_component',
                replacements={
                    'is_detached': 0
                },
                conditions={
                    '`change`': component_change
                }
            )
        self.add_ticket_list(self.root_change, component_change, 'add')

    def get_root_change(self, int_change):
        int_change_obj = inte_change.IntegrationChange(self.rest, int_change)
        depends_comps = int_change_obj.get_depends()
        for depends_comp in depends_comps:
            print('depends_comp: {}'.format(depends_comp))
            if depends_comp[2] == 'root':
                return depends_comp[1]
        raise Exception('Cannot get root change for {}'.format(inte_change))

    def add_ticket_list(self, root_change, comp_change, action):
        root_change_obj = inte_change.RootChange(self.rest, root_change)
        comp_change_list, int_change = root_change_obj.get_components_changes_by_comments()
        if action == 'add':
            comp_change_list.append(comp_change)
        if action == 'remove':
            comp_change_list.remove(comp_change)
        comps_dict = {
            'tickets': comp_change_list,
            'manager': int_change,
            'root': root_change}
        self.rest.review_ticket(
            root_change, 'Tickets-List: {}'.format(json.dumps(comps_dict)))


if __name__ == '__main__':
    fire.Fire(OperateIntegrationChange)
