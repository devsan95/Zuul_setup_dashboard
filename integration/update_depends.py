import re
import fire
import yaml
import logging

from api import gerrit_rest
from mod import common_regex
from mod.integration_change import RootChange
from mod.integration_change import IntegrationChange
from integration_trigger import get_comp_obj


def update_depends(rest, change_id, dep_file_list,
                   dep_submodule_dict, comp_config):
    # check if there is interfaces info in commit-msg
    commit_msg = rest.get_commit(change_id).get('message')
    commit_lines = commit_msg.splitlines()
    find_interfaces = False
    interface_infos = []
    for idx, commit_line in enumerate(commit_lines):
        if commit_line.startswith('interface info:'):
            component = ''
            comp_version = ''
            repo_version = ''
            comp_line = commit_lines[idx + 1]
            bb_ver_line = commit_lines[idx + 2]
            version_line = commit_lines[idx + 3]
            m = re.match(r'[\s]+comp_name:\s+(\S+)', comp_line)
            if not m:
                logging.warn(
                    'not find comp_name for interfaces in %s', comp_line)
                continue
            else:
                component = m.group(1)
            m = re.match(r'[\s]+bb_version:\s+(\S+)', bb_ver_line)
            if not m:
                logging.warn(
                    'not find bb_version for interfaces in %s', bb_ver_line)
                continue
            else:
                comp_version = m.group(1).split(component)[1].lstrip('-')
            m = re.match(r'[\s]+commit-ID:\s+(\S+)', version_line)
            if not m:
                logging.warn(
                    'not find commit-ID for interfaces in %s', version_line)
                continue
            else:
                repo_version = m.group(1)
            find_interfaces = True
            interface_infos.append({"component": component,
                                    "comp_version": comp_version,
                                    "repo_version": repo_version})

    if not find_interfaces:
        logging.warn('Not find interfaces in commit-msg')
        return

    op = RootChange(rest, change_id)
    comp_change_list, int_change = op.get_components_changes_by_comments()

    for interface_info in interface_infos:
        component = interface_info['component']
        comp_version = interface_info['comp_version']
        repo_version = interface_info['repo_version']
        for dep_file_line in dep_file_list:
            dep_str_list = dep_file_line.split(':')
            dep_file = dep_str_list[0].strip()
            dep_file_comps = []
            if len(dep_str_list) > 1:
                dep_file_comps = dep_str_list[1].strip().split(',')
            for comp_change in comp_change_list:
                logging.info('Try to update %s, %s', comp_change, dep_file)
                replace_depdends_file(rest, comp_change,
                                      dep_file, component, comp_version,
                                      comp_config, dep_file_comps)
                if component in dep_submodule_dict:
                    replace_submodule_content(
                        rest, comp_change,
                        dep_submodule_dict[component], repo_version)
                else:
                    logging.warn('%s not in dep submodule dict %s',
                                 component, dep_submodule_dict)
                try:
                    rest.publish_edit(comp_change)
                except Exception as e:
                    logging.warn('Publish edit is failed')
                    print(str(e))


def replace_depdends_file(rest, change_id, file_path, component, version,
                          comp_config, dep_file_comps):
    logging.info('Try to update depends for %s', file_path)
    # if component is match
    int_change_obj = IntegrationChange(rest, change_id)
    ticket_comps = int_change_obj.get_components()
    comps_for_interfaces = get_comp_obj(component, comp_config)
    for t_comp in ticket_comps:
        if t_comp not in comps_for_interfaces.values():
            logging.warn(
                'Not in %s or %s', comps_for_interfaces, dep_file_comps)
            return
        if dep_file_comps and t_comp not in dep_file_comps:
            logging.warn(
                'Not in %s or %s', comps_for_interfaces, dep_file_comps)
            return
    # get file content from change_id
    try:
        recipe_content = rest.get_file_content(file_path, change_id)
    except Exception as e:
        logging.warn('Not able to find file %s in %s', file_path, change_id)
        logging.warn(str(e))
        return
    logging.info('Update depend file for %s: %s', change_id, file_path)
    logging.info('Update dependence info: %s, %s', component, version)
    new_recipe_content = replace_depdends_content(recipe_content,
                                                  component, version)
    if new_recipe_content != recipe_content:
        rest.add_file_to_change(change_id, file_path, new_recipe_content)


def replace_depdends_content(old_recipe_content, component, version):
    # find matched list
    # list == 1 , replace
    # list == 0 , skip
    # list > 1, raise Exception
    matched = False
    for ver_regex in common_regex.COMP_VERSION_REGEX:
        prefer_regex = re.compile(r'{}{}[\s"]'.format(component, ver_regex))
        last_regex = re.compile(r'{}{}'.format(component, ver_regex))
        new_regex = r"{}-{}".format(component, version)
        for cur_regex in [prefer_regex, last_regex]:
            match_elems = re.findall(cur_regex, old_recipe_content)
            if len(match_elems) == 1:
                old_component_str = match_elems[0].rstrip().rstrip('"')
                return re.sub(old_component_str, new_regex, old_recipe_content)
            if len(match_elems) > 1:
                logging.warn('Get multi match elems %s for %s',
                             match_elems, cur_regex)
                matched = True
            if len(match_elems) == 0:
                continue
    if not matched:
        logging.warn('No match elem for %s %s',
                     component, common_regex.COMP_VERSION_REGEX)
    else:
        logging.warn('Get multi match elems for %s %s',
                     component, common_regex.COMP_VERSION_REGEX)
    return old_recipe_content


def replace_submodule_content(rest, change_id, file_path, version):
    # get submodule content
    try:
        submodule_content = rest.get_file_content(file_path, change_id)
    except Exception as e:
        logging.warn('Not able to find file %s in %s', file_path, change_id)
        logging.warn(str(e))
        return
    submodule_regex = re.compile(r'^([0-9a-z]+)$')
    print('Submodule content: {}'.format(submodule_content))
    m = submodule_regex.match(submodule_content)
    if m:
        rest.add_file_to_change(change_id, file_path, version)
    else:
        raise Exception(
            'Cannot find matched submodule format for {}'.format(file_path))
    # find 'Subproject commit xxxxx' and replaced


def run(gerrit_info_path, change_id, dep_files,
        dep_submodules, component_yaml_path):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    dep_file_list = dep_files.splitlines()
    dep_submodule_dict = {}
    comp_config = {}
    with open(component_yaml_path, 'r') as fr:
        comp_config = yaml.load(fr.read(), Loader=yaml.Loader)
    for dep_submodule_line in dep_submodules.splitlines():
        if ':' in dep_submodule_line:
            component = dep_submodule_line.split(':', 1)[0].strip()
            submodule_path = dep_submodule_line.split(':', 1)[1].strip()
            dep_submodule_dict[component] = submodule_path
        else:
            logging.warn('Cannot find ":" in line: %s', dep_submodule_line)
    update_depends(rest, change_id, dep_file_list,
                   dep_submodule_dict, comp_config)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fire.Fire()
