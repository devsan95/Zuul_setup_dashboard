#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import fire
import ruamel.yaml as yaml
import urllib3
import re
from api import gerrit_rest
from mod import integration_change as inte_change
from mod import get_component_info
import operate_integration_change as operate_int

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
    root['manager_change'] = root_change_obj.get_components_changes_by_comments()[1]
    return root


def generate_commit_message(comp, root):
    msg_list = []
    if 'MN/5G/NB/gnb' in comp['repo']:
        msg_list.append('[none] {} {} {}'.format(comp['name'], root['feature_id'], root['branch']))
    msg_list.append('<{}> on <{}> of <{}> topic <{}>'.format(comp['name'], root['feature_id'], root['branch'], root['topic']))
    msg_list.append('Platform ID: <{}>'.format(root['platform_id']))
    msg_list.append('\n')
    msg_list.append('%JR={}'.format(root['jira_id']))
    msg_list.append('%FIFI={}'.format(root['feature_id']))
    msg_list.append('\n')
    msg_list.append('Remarks:')
    msg_list.append('---')
    msg_list.append('Apply adaption using format, update_bb:COMPONENT_NAME,REPO_URL,REPO_VER')
    msg_list.append('{}'.format(root['zuul_rebase']))
    msg_list.append('---')
    msg_list.append('\n')
    msg_list.append('This change contains following component(s):')
    if isinstance(comp['ric'], str):
        msg_list.append('  - COMP <{}>'.format(comp['ric']))
    if isinstance(comp['ric'], list):
        for ric in comp['ric']:
            msg_list.append('  - COMP <{}>'.format(ric))
    msg_list.append('\n')
    return '\n'.join(msg_list)


def create_comp_change(rest, comp, base_commit, root):
    commit_message = generate_commit_message(comp, root)
    change_id, ticket_id, rest_id = rest.create_ticket(
        comp['repo'], None, root['branch'], commit_message, base_change=base_commit
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
            base_load = base_load_re.match(comments)[1]
            break
    if not base_load:
        raise Exception('[Error] Failed to get base load info in manager change {}'.format(manager_change))
    return base_load


def get_base_commit(rest, comp, root):
    int_mode = root['zuul_rebase']
    commit_hash = None
    base_commit = None
    if 'with-zuul-rebase' in int_mode:
        print('[Info] Integration mode is Head mode')
        commit_info = rest.get_latest_commit_from_branch(comp['repo'], root['branch'])
        commit_hash = commit_info['revision']
    elif 'without-zuul-rebase' in int_mode:
        base_load = get_base_load(rest, root['manager_change'])
        if 'MN/SCMTA/zuul/inte_ric' in comp['repo']:
            commit_info = rest.get_latest_commit_from_branch(comp['repo'], root['branch'])
            commit_hash = commit_info['revision']
        else:
            inte_repo = get_component_info.init_integration(base_load)
            commit_hash = get_component_info.get_comp_hash(inte_repo, comp['ric'])
    if commit_hash:
        change_info = rest.query_ticket('commit:{}'.format(commit_hash), count=1)
        if change_info:
            change_info = change_info[0]
            base_commit = change_info['_number']
    return base_commit


def parse_hierarchy(hierarchy):
    comp_list = {}
    for key in hierarchy:
        comp_list['key'] = []
        if isinstance(key, dict):
            for sub_key in hierarchy['key']:
                comp_list['sub_key'] = []
                if isinstance(sub_key, list):
                    for e in hierarchy['key']['sub_key']:
                        comp_list['sub_key'].append(e)
                        comp_list['key'].append(e)
                comp_list['sub_key'] = list(set(comp_list['sub_key']))
                print('[Info] component {} contains sub components {}'.format(sub_key, comp_list['sub_key']))
        if isinstance(key, list):
            for e in hierarchy['key']:
                comp_list['key'].append(e)
        comp_list['key'] = list(set(comp_list['key']))
        print('[Info] component {} contains sub components {}'.format(key, comp_list['key']))
    return comp_list


def main(root_change, comp_name, component_config, gerrit_info_path, mysql_info_path, base_commit=None):
    comp_config = yaml.load(open(component_config),
                            Loader=yaml.Loader, version='1.1')
    comp = {}
    comp['name'] = comp_name
    comp_found = False
    comp_dict = parse_hierarchy(comp_config['hierarchy'])
    for component in comp_config['components']:
        if comp_name not in component['name']:
            continue
        comp_found = True
        if 'ric' in component and component['ric']:
            comp['ric'] = component['ric']
        if 'repo' in component:
            comp['repo'] = component['repo']
        elif 'type' in component and 'external' in component['type']:
            comp['repo'] = 'MN/SCMTA/zuul/inte_ric'
        else:
            raise Exception('[Error] Failed to find project for this component')
        break
    if not comp_found:
        if comp_name in comp_dict:
            comp['ric'] = comp_dict['comp_name']
            for component in comp_config['components']:
                if comp['ric'][0] not in component['name']:
                    continue
                if 'repo' in component:
                    comp['repo'] = component['repo']
                elif 'type' in component and 'external' in component['type']:
                    comp['repo'] = 'MN/SCMTA/zuul/inte_ric'
        else:
            raise Exception('[Error] component name is invalid, please refer to the name in skytrack create page')

    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    root = parse_root_change(rest, root_change)
    if not base_commit:
        base_commit = get_base_commit(rest, comp, root)
    comp_change_number = create_comp_change(rest, comp, base_commit, root)

    int_operator = operate_int.OperateIntegrationChange(gerrit_info_path, root['manager_change'], mysql_info_path)
    int_operator.add(comp_change_number)


if __name__ == '__main__':
    fire.Fire(main)
