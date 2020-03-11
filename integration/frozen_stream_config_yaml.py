#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import re
import os
import git
import fire
import yaml
import shutil
import logging
import traceback

import integration_add_component
from api import gerrit_rest
from mod import utils
from mod import wft_tools
from mod import get_component_info
from mod.integration_change import RootChange
from mod.integration_change import ManageChange


VERSION_PATTERN = r'export VERSION_PATTERN=([0-9]+.[0-9]+)'


def get_branch_integration(branch):
    integration_dir = os.path.join(os.getcwd(), 'Integration')
    if os.path.exists(os.path.join(integration_dir)):
        shutil.rmtree(integration_dir)
    os.makedirs(integration_dir)
    g = git.Git(integration_dir)
    g.init()
    g.fetch(get_component_info.INTEGRATION_URL, branch)
    g.checkout('FETCH_HEAD')
    return g


def get_last_passed_package(branch):
    g = get_branch_integration(branch)
    stream_list = []
    base_load_dict = {}
    stream_dict = {}
    for x in os.listdir(g.working_dir):
        if x.startswith('.config'):
            with open(os.path.join(g.working_dir, x), 'r') as fr:
                content = fr.read()
                m = re.search(VERSION_PATTERN, content)
                if m:
                    stream_list.append(m.group(1))
                    stream_dict[x.split('.config-')[1]] = m.group(1)
    logging.info('Get pacakges by stream list %s', stream_list)
    base_load, base_load_list = wft_tools.get_latest_build_load(stream_list, strip_prefix=False)
    for base_load_name in base_load_list:
        for pipeline, stream in stream_dict.items():
            if '_{}.'.format(stream) in base_load_name:
                base_load_dict[pipeline] = base_load_name
    return base_load, base_load_dict, g.working_dir


def get_changed_in_global_config_yaml(rest, integration_repo_ticket):
    old_sections = {}
    change_content = rest.get_file_change('config.yaml', integration_repo_ticket)
    old_config_yaml = yaml.safe_load(change_content['old'])
    new_config_yaml = yaml.safe_load(change_content['new'])
    if not old_config_yaml:
        return old_sections
    for config_key, component_info in old_config_yaml['components'].items():
        if config_key in new_config_yaml['components']:
            new_component_info = new_config_yaml['components'][config_key]
            if component_info['version'] != new_component_info['version']:
                old_sections[config_key] = component_info
    return old_sections


def frozen_config_yaml(previous_comp_dict, integration_dir, rest, integration_repo_ticket):
    logging.info('Frozen config.yaml : %s', previous_comp_dict)
    stream_config_yaml_path = os.path.join(integration_dir, 'meta-5g-cb/config_yaml')
    logging.info('Find all config.yaml in %s', stream_config_yaml_path)
    stream_config_yaml_files = utils.find_files(stream_config_yaml_path, 'config.yaml')
    logging.info('Stream_config_yaml_files: %s', stream_config_yaml_files)
    old_sections = get_changed_in_global_config_yaml(rest, integration_repo_ticket)
    logging.info('Config_yaml old sections: %s', old_sections)
    feature_list = []
    for stream_config_yaml_file in stream_config_yaml_files:
        stream_config_yaml_file = stream_config_yaml_file.split(integration_dir)[1].lstrip('/')
        stream_config_yaml = {"components": {}, "version": 1}
        features = {}
        pipeline = os.path.basename(os.path.dirname(stream_config_yaml_file))
        try:
            stream_config_content = rest.get_file_content(stream_config_yaml_file, integration_repo_ticket)
            stream_config_yaml = yaml.safe_load(stream_config_content)
        except Exception:
            logging.warn('config yaml file %s not exists, created', stream_config_yaml_file)
        if not stream_config_yaml['components']:
            stream_config_yaml['components'] = {}
        else:
            for component_info in stream_config_yaml['components']:
                if 'features' in component_info:
                    features = component_info['features']
        for name, comp_dicts in previous_comp_dict.items():
            feature_id = comp_dicts['feature_id']
            feature_list.append(feature_id)
            platform_id = comp_dicts['platform_id']
            if pipeline not in comp_dicts:
                continue
            comp_dict = comp_dicts[pipeline]
            logging.info('Frozen comonent %s in %s', comp_dict, stream_config_yaml_file)
            component_yaml_key = '{}:{}'.format(comp_dict['project'], comp_dict['component'])
            if feature_id not in features:
                features[feature_id] = {
                    "feature_delivered": False,
                    "platform_id": platform_id
                }
            yaml_obj = {
                "commit": comp_dict['version'],
                "location": "config.yaml",
                "type": "submodule_meta-5g",
                "version": comp_dict['version'],
                "feature_component": name,
                "features": features
            }
            if not stream_config_yaml['components']:
                stream_config_yaml['components'] = {}
            stream_config_yaml['components'][component_yaml_key] = yaml_obj
        for config_key, section in old_sections.items():
            section['features'] = features
            if config_key not in stream_config_yaml['components']:
                stream_config_yaml['components'][config_key] = section
            else:
                stream_config_yaml['components'][config_key].update(section)
        new_stream_config_content = yaml.safe_dump(stream_config_yaml)
        rest.add_file_to_change(integration_repo_ticket, stream_config_yaml_file, new_stream_config_content)
    try:
        rest.publish_edit(integration_repo_ticket)
    except Exception as e:
        print(str(e))
        raise Exception('Publish edit is failed')
    rest.review_ticket(integration_repo_ticket, 'review', {'Code-Review': 2})


def get_comp_bbver(component_name, pass_packages, get_comp_info_objs={}):
    logging.info('Get bbver for %s', component_name)
    component_pvs = {}
    for pipeline, pass_package in pass_packages.items():
        pass_package = trans_wft_name_to_tag(pass_package)
        if pipeline not in get_comp_info_objs:
            new_get_comp_info = get_component_info.GET_COMPONENT_INFO(
                pass_package, no_dep_file=True, only_mapping_file=True)
            get_comp_info_objs[pipeline] = new_get_comp_info
            if not new_get_comp_info.if_bb_mapping:
                continue
            component_pv = new_get_comp_info.get_value_from_mapping_and_env(component_name, 'PV', 'pv')
            if component_pv:
                component_pv = re.sub(r'-r[0-9]+$', '', component_pv)
            component_pvs[pipeline] = component_pv
    return component_pvs


def trans_wft_name_to_tag(wft_name):
    if '_' in wft_name:
        return wft_name.split('_')[1]
    return wft_name


def run(gerrit_info_path, change_no, branch, component_config, mysql_info_path):
    # get last passed package
    last_pass_package, pass_packages, integration_dir = get_last_passed_package(branch)
    #  if integraiton ticket,  changed section in config.yaml.
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    root_change_obj = RootChange(rest, change_no)
    comp_change_list, integration_tickt = root_change_obj.get_components_changes_by_comments()
    manage_change_obj = ManageChange(rest, integration_tickt)
    integration_repo_ticket = ''
    if root_change_obj.get_project() == 'MN/5G/COMMON/integration':
        integration_repo_ticket = change_no
    component_list = manage_change_obj.get_all_components()
    logging.info('component_list: %s', component_list)
    if 'MN/5G/COMMON/integration' in [x[1] for x in component_list]:
        for component in component_list:
            if component[1] == 'MN/5G/COMMON/integration':
                integration_repo_ticket = component[2]
    # components in topic
    sub_builds = {}
    get_comp_info_objs = {}
    for pipeline, pass_package in pass_packages.items():
        sub_builds[pipeline] = wft_tools.get_subuild_from_wft(pass_package)
    logging.info('sub_builds: %s', sub_builds)
    previous_comp_dict = {}
    get_comp_info_objs = {}
    for component in component_list:
        component_name = component[0]
        previous_comp_dict[component_name] = {}
        logging.info('Find matched subbuild for : %s', component)
        for pipeline, sub_build_list in sub_builds.items():
            for sub_build in sub_build_list:
                if component_name == sub_build['component']:
                    previous_comp_dict[component_name][pipeline] = sub_build
        if component_name not in previous_comp_dict:
            component_pvs = {}
            component_pvs = get_comp_bbver(component_name, pass_packages, get_comp_info_objs)
            logging.info('Get bbver for %s is %s', component_name, component_pvs)
            if component_pvs:
                for pipeline, sub_build_list in sub_builds.items():
                    for sub_build in sub_build_list:
                        if pipeline in component_pvs and sub_build['version'] == component_pvs[pipeline]:
                            previous_comp_dict[component_name][pipeline] = sub_build
        if not previous_comp_dict[component_name]:
            previous_comp_dict.pop(component_name)
        if component_name not in previous_comp_dict:
            # all components should be in WFT && BB_Mapping file,
            # so may be we need to raise Exception here
            logging.warn('Not find %s in previous loads: %s', component_name, pass_packages)
        else:
            previous_comp_dict[component_name]['feature_id'] = root_change_obj.get_feature_id()
            previous_comp_dict[component_name]['platform_id'] = root_change_obj.get_platform_id()

    # create integration_repo ticket if not exists
    if not integration_repo_ticket:
        try:
            integration_repo_ticket = integration_add_component.main(
                change_no, 'integration_repo', component_config, gerrit_info_path,
                mysql_info_path, base_load=trans_wft_name_to_tag(last_pass_package))
        except Exception:
            traceback.print_exc()
            raise Exception('Cannot add integration_repo ticket')
    # frozen old section in stream config.yaml
    frozen_config_yaml(previous_comp_dict, integration_dir, rest, integration_repo_ticket)


if __name__ == '__main__':
    fire.Fire(run)
