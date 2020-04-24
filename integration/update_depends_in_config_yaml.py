import fire
import logging
import traceback

import update_depends
import integration_add_component
from api import gerrit_rest
from mod.integration_change import RootChange


def run(gerrit_info_path, mysql_info_path, change_id, component_config):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    find_interfaces, interface_infos = update_depends.search_interfaces(rest, change_id)
    # check if integration_repo ticket exists
    if not find_interfaces:
        logging.warn('Not find interfaces in commit-msg')
        return

    root_change_obj = RootChange(rest, change_id)
    comp_change_list, integration_ticket = root_change_obj.get_components_changes_by_comments()
    integration_repo_ticket = update_depends.get_integration_repo_ticket(rest, change_id)

    # create integration_repo ticket if not exists
    if not integration_repo_ticket:
        try:
            integration_add_component.main(change_id, 'integration_repo',
                                           component_config, gerrit_info_path, mysql_info_path)
        except Exception:
            traceback.print_exc()
            raise Exception('Cannot add integration_repo ticket')
        new_root_change_obj = RootChange(rest, change_id)
        new_comp_changes, integration_tickt = new_root_change_obj.get_components_changes_by_comments()
        integration_repo_ticket = [x for x in new_comp_changes if x not in comp_change_list][0]

    # add component change to config.yaml
    update_depends.update_config_yaml(rest, integration_repo_ticket, interface_infos)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fire.Fire()
