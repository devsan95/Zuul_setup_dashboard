import fire
import yaml
import logging
import traceback

import update_depends
import integration_add_component
from api import gerrit_rest
from mod.integration_change import RootChange
from mod.integration_change import ManageChange


def update_config_yaml(rest, integration_repo_ticket, interface_infos):
    config_yaml_content = rest.get_file_content('config.yaml', integration_repo_ticket)
    config_dict = yaml.safe_load(config_yaml_content)
    for interface_info in interface_infos:
        compoent_dict = {
            'commit': interface_info['repo_version'],
            'version': interface_info['comp_version'],
            'location': 'config.yaml',
            'type': 'submodule_meta-5g'
        }
        component_key = 'Common:{}'.format(interface_info['component'])
        if component_key in config_dict['components']:
            config_dict['components'][component_key].update(compoent_dict)
        else:
            config_dict['components'][component_key] = compoent_dict
    config_yaml_content = yaml.safe_dump(config_dict, default_flow_style=False,
                                         encoding='utf-8', allow_unicode=True)
    rest.add_file_to_change(integration_repo_ticket, 'config.yaml', content=config_yaml_content)
    rest.publish_edit(integration_repo_ticket)


def run(gerrit_info_path, mysql_info_path, change_id, component_config):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    find_interfaces, interface_infos = update_depends.search_interfaces(rest, change_id)
    # check if integration_repo ticket exists
    if not find_interfaces:
        logging.warn('Not find interfaces in commit-msg')
        return
    root_change_obj = RootChange(rest, change_id)
    comp_change_list, integration_tickt = root_change_obj.get_components_changes_by_comments()
    manage_change_obj = ManageChange(rest, integration_tickt)
    integration_exists = False
    integration_repo_ticket = ''
    if root_change_obj.get_project() == 'MN/5G/COMMON/integration':
        integration_repo_ticket = change_id
        integration_exists = True
    component_list = manage_change_obj.get_all_components()
    print('component_list')
    print(component_list)
    if 'MN/5G/COMMON/integration' in [x[1] for x in component_list]:
        for component in component_list:
            if component[1] == 'MN/5G/COMMON/integration':
                integration_repo_ticket = component[2]
        integration_exists = True

    # create integration_repo ticket if not exists
    if not integration_exists:
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
    update_config_yaml(rest, integration_repo_ticket, interface_infos)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fire.Fire()
