#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import fire
import ruamel.yaml as yaml
import urllib3
import re
from slugify import slugify
from datetime import datetime
from api import gerrit_rest
from mod import integration_change as inte_change
from mod import get_component_info
from mod import config_yaml
from mod import parse_integration_config_yaml
import operate_integration_change as operate_int
import skytrack_database_handler

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def parse_root_change(rest, root_change):
    root = {}
    root_change_obj = inte_change.RootChange(rest, root_change)
    root['feature_id'] = root_change_obj.get_feature_id()
    root['jira_id'] = root_change_obj.get_jira_id()
    root['zuul_rebase'] = root_change_obj.get_with_without()
    root['branch'] = root_change_obj.get_branch()
    root['topic'] = root_change_obj.get_topic()
    root['platform_id'] = root_change_obj.get_platform_id()
    root['component_changes'] = root_change_obj.get_all_changes_by_comments()
    root['manager_change'] = root_change_obj.get_components_changes_by_comments()[1]
    root['project'] = root_change_obj.get_project()
    return root


def generate_commit_message(comp, root, base_commit):
    msg_list = []
    if 'MN/5G/NB/gnb' in comp['repo']:
        if 'without-zuul-rebase' in root['zuul_rebase']:
            msg_list.append('[none] [NOREBASE] {} {} {}'.format(comp['name'], root['feature_id'], root['branch']))
        else:
            msg_list.append('[none] {} {} {}'.format(comp['name'], root['feature_id'], root['branch']))
    msg_list.append(' ')
    msg_list.append('<{}> on <{}> of <{}> topic <{}>'.format(comp['name'], root['feature_id'], root['branch'], root['topic']))
    msg_list.append('Platform ID: <{}>'.format(root['platform_id']))
    msg_list.append('%JR={}'.format(root['jira_id']))
    msg_list.append('%FIFI={}'.format(root['feature_id']))
    msg_list.append('Remarks:')
    msg_list.append('---')
    msg_list.append('Apply adaption using format, update_bb:COMPONENT_NAME,REPO_URL,REPO_VER')
    msg_list.append('{}'.format(root['zuul_rebase']))
    if base_commit:
        msg_list.append('base_commit:{}'.format(base_commit))
    msg_list.append('---')
    msg_list.append('This change contains following component(s):')
    if 'ric' in comp:
        if isinstance(comp['ric'], str):
            for ric_name in comp['ric'].split(','):
                msg_list.append('  - COMP <{}>'.format(ric_name))
        if isinstance(comp['ric'], list):
            for ric in comp['ric']:
                msg_list.append('  - COMP <{}>'.format(ric))
    return '\n'.join(msg_list)


def create_comp_change(rest, comp, base_commit, base_change, root):
    commit_message = generate_commit_message(comp, root, base_commit)
    change_id, ticket_id, rest_id = rest.create_ticket(
        comp['repo'], None, root['branch'], commit_message, base_change=base_change
    )
    return ticket_id


def get_base_load(rest, manager_change):
    base_load = None
    base_load_re = re.compile(r'update_base:(.*),(.*)')
    detail_info = rest.get_detailed_ticket(manager_change)
    comments_list = detail_info['messages']
    for comments in reversed(comments_list):
        comments = comments['message']
        result_list = base_load_re.findall(comments)
        if len(result_list) > 0:
            base_load = result_list[0][1]
            break
    if not base_load:
        raise Exception('[Error] Failed to get base load info in manager change {}'.format(manager_change))
    return base_load


def get_base_commit(rest, comp, root, base_load):
    int_mode = root['zuul_rebase']
    commit_hash = None
    base_commit = None
    base_change = None
    if 'with-zuul-rebase' in int_mode:
        print('[Info] Integration mode is Head mode')
        commit_info = rest.get_latest_commit_from_branch(comp['repo'], root['branch'])
        commit_hash = commit_info['revision']
    elif 'without-zuul-rebase' in int_mode:
        if not base_load:
            base_load = get_base_load(rest, root['manager_change'])
        get_comp_info = get_component_info.GET_COMPONENT_INFO(base_load)
        if 'MN/SCMTA/zuul/inte_ric' in comp['repo']:
            commit_info = rest.get_latest_commit_from_branch(comp['repo'], root['branch'])
            commit_hash = commit_info['revision']
            if isinstance(comp['ric'], str):
                comp['ric'] = comp['ric'].split(',')
            for ric_name in comp['ric']:
                try:
                    base_commit = get_comp_info.get_comp_hash(ric_name)
                    break
                except Exception:
                    print("Get {}'s base_commit failed".format(ric_name))
                    continue
            else:
                raise Exception("Get {}'s base_commit failed".format(comp['ric']))
        else:
            if isinstance(comp['ric'], str):
                if comp['ric'] == 'integration':
                    commit_hash = base_load
                else:
                    commit_hash = get_comp_info.get_comp_hash(comp['ric'])
            if isinstance(comp['ric'], list):
                commit_hash = get_comp_info.get_comp_hash(comp['ric'][0])
    if commit_hash:
        change_info = rest.query_ticket('commit:{}'.format(commit_hash), count=1)
        if change_info:
            change_info = change_info[0]
            base_change = change_info['_number']
    return base_commit, base_change


def add_tmp_file(rest, change_number, files, topic):
    need_publish = False
    if len(files) > 0:
        for f in files:
            file_path = f + slugify(topic) + '.inte_tmp'
            rest.add_file_to_change(change_number, file_path, datetime.utcnow().strftime('%Y%m%d%H%M%S'))
            need_publish = True
    if need_publish:
        rest.publish_edit(change_number)


def get_changed_in_global_config_yaml(rest, integration_repo_ticket):
    changed_sections = {}
    change_content = rest.get_file_change('config.yaml', integration_repo_ticket)
    old_config_yaml = yaml.safe_load(change_content['old'])
    new_config_yaml = yaml.safe_load(change_content['new'])
    if not new_config_yaml:
        return changed_sections
    for config_key, component_info in new_config_yaml['components'].items():
        if config_key in old_config_yaml['components']:
            old_component_info = old_config_yaml['components'][config_key]
            if component_info['version'] != old_component_info['version'] or \
                    component_info['commit'] != old_component_info['commit']:
                changed_sections[config_key] = component_info
        else:
            print("Info: component {} not exist in old config.yaml".format(config_key))
            changed_sections[config_key] = component_info
    return changed_sections


def update_component_local_config_yaml(rest, change_number, component, comp_config, changed_section):
    if component['repo'] in comp_config['config_yaml'].keys():
        print("Local config.yaml found for component {}".format(component['name']))
        if changed_section:
            local_config_yaml = comp_config['config_yaml'][component['repo']]
            local_yaml_content = ''
            try:
                local_yaml_content = rest.get_file_content(local_config_yaml, change_number)
            except Exception:
                print('Warn: no local config.yaml in this repo: {}'.format(component['repo']))
            if local_yaml_content:
                local_yaml_obj = config_yaml.ConfigYaml(config_yaml_content=local_yaml_content)
                local_yaml_obj.components.update(changed_section)
                config_yaml_content = yaml.safe_dump(local_yaml_obj.config_yaml, default_flow_style=False)

                rest.add_file_to_change(change_number, local_config_yaml, config_yaml_content)
                rest.publish_edit(change_number)


def check_external_change(rest, root_change):
    root_change_obj = inte_change.RootChange(rest, root_change)
    comp_change_list, manager_change = root_change_obj.get_components_changes_by_comments()
    parent_commit = None
    for comp in comp_change_list:
        comp_change_obj = inte_change.IntegrationChange(rest, comp)
        change_type = comp_change_obj.get_type()
        if 'external' in change_type:
            parent_commit = rest.get_parent(comp)
            break
    return parent_commit


def add_depends_info(rest, comp_change, depends_change):
    change_obj = inte_change.IntegrationChange(rest, comp_change)
    depends_change_obj = inte_change.IntegrationChange(rest, depends_change)
    msg_obj = inte_change.IntegrationCommitMessage(change_obj)
    msg_obj.add_depends(depends_change_obj)
    msg_obj.add_depends_on(depends_change_obj)
    message = msg_obj.get_msg()
    try:
        rest.delete_edit(comp_change)
    except Exception as e:
        print(e)
    try:
        rest.change_commit_msg_to_edit(comp_change, message)
    except Exception as e:
        if "New commit message cannot be same as existing commit message" in str(e):
            pass
        else:
            raise Exception(e)
    rest.publish_edit(comp_change)


def main(root_change, comp_name, component_config, gerrit_info_path, mysql_info_path, base_commit=None, base_load=None):
    comp_config = yaml.load(open(component_config),
                            Loader=yaml.Loader, version='1.1')
    comp = {}
    comp['name'] = comp_name
    comp_found = False
    comp_dict = parse_integration_config_yaml.parse_hierarchy(comp_config['hierarchy'])
    comp['files'] = []
    depends_components = comp_config['depends_components']
    components = parse_integration_config_yaml.get_component_list(comp_config)
    for component in components:
        if not comp_name == component['name']:
            continue
        comp_found = True
        if 'ric' in component and component['ric']:
            comp['ric'] = component['ric'].split(",")
        if 'files' in component and component['files']:
            comp['files'].append(component['files'])
        if 'repo' in component:
            comp['repo'] = component['repo']
        elif 'type' in component and 'external' in component['type']:
            comp['repo'] = 'MN/SCMTA/zuul/inte_ric'
        else:
            raise Exception('[Error] Failed to find project for this component')
        break
    if not comp_found:
        if comp_name in comp_dict:
            comp['ric'] = comp_dict[comp_name]
            for component in components:
                if comp['ric'][0] not in component['name']:
                    continue
                if 'repo' in component:
                    comp['repo'] = component['repo']
                elif 'type' in component and 'external' in component['type']:
                    comp['repo'] = 'MN/SCMTA/zuul/inte_ric'
            for com in comp_dict[comp_name]:
                for c in components:
                    if com == c['name']:
                        if 'files' in c and c['files']:
                            comp['files'].append(c['files'])
        else:
            raise Exception('[Error] component name is invalid, please refer to the name in skytrack create page')

    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    root = parse_root_change(rest, root_change)
    list_obj = inte_change.ManageChange(rest, root['manager_change'])
    component_list = list_obj.get_all_components()

    if not base_commit:
        base_commit, base_change = get_base_commit(rest, comp, root, base_load=base_load)
    parent_commit = None
    if comp['repo'] == 'MN/SCMTA/zuul/inte_ric':
        parent_commit = check_external_change(rest, root_change)
        if parent_commit:
            base_commit = parent_commit
    comp_list = []
    for i in component_list:
        comp_list.append(i[0])
    if comp_name in comp_list:
        raise Exception("component {} has been already added before".format(comp_name))

    comp_change_number = create_comp_change(rest, comp, base_commit, base_change, root)
    print("[Info] The new add component change number is: {}".format(comp_change_number))

    if 'files' in comp and comp['files']:
        add_tmp_file(rest, comp_change_number, comp['files'], root['topic'])

    # update local_config.yaml according to global_config.yaml if component has one
    if root['project'] == 'MN/5G/COMMON/integration':
        changed_section = get_changed_in_global_config_yaml(rest, root_change)
        if changed_section:
            update_component_local_config_yaml(rest, comp_change_number,
                                               comp, comp_config, changed_section)

    if comp_name in depends_components:
        for comp_change in root['component_changes']:
            if rest.get_ticket(comp_change)['status'] in ['MERGED', 'ABANDONED']:
                continue
            add_depends_info(rest, comp_change, depends_change=comp_change_number)

    int_operator = operate_int.OperateIntegrationChange(gerrit_info_path, root['manager_change'], mysql_info_path)
    int_operator.add(comp_change_number)
    skytrack_database_handler.add_integration_tickets(jira_key=root['jira_id'], change_list=[comp_change_number], database_info_path=mysql_info_path)
    return comp_change_number


if __name__ == '__main__':
    fire.Fire(main)
