import fire
import yaml
import logging
import traceback

import update_depends
import integration_add_component
from api import gerrit_rest
from mod.integration_change import RootChange
from mod import config_yaml
from rebase_env import update_component_config_yaml


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

    # update component config.yaml
    config_yaml_dict = {}
    with open(component_config, 'r') as fr:
        comp_config_dict = yaml.load(fr.read(), Loader=yaml.Loader)
    if 'config_yaml' in comp_config_dict:
        config_yaml_dict = comp_config_dict['config_yaml']

    config_yaml_change = {}
    try:
        config_yaml_change = rest.get_file_change('config.yaml', integration_repo_ticket)
    except Exception:
        print('Cannot find config.yaml for %s', integration_repo_ticket)
    if ('new_diff' in config_yaml_change and config_yaml_change['new_diff']) \
            or ('old_diff' in config_yaml_change and config_yaml_change['old_diff']):
        config_yaml_obj = config_yaml.ConfigYaml(config_yaml_content=config_yaml_change['new'])
        updated_dict, removed_dict = config_yaml_obj.get_changes(yaml.safe_load(config_yaml_change['old']))
        update_component_config_yaml(
            {},
            rest,
            integration_repo_ticket,
            config_yaml_dict,
            config_yaml_updated_dict=updated_dict,
            config_yaml_removed_dict=removed_dict)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fire.Fire()
