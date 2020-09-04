#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import re
import os
import git
import copy
import fire
import yaml
import shutil
import logging
import traceback

import update_feature_yaml as bitbake_tools
import integration_add_component
from api import gerrit_rest
from mod import utils
from mod import wft_tools
from mod import integration_repo
from mod import get_component_info
from distutils.version import LooseVersion
from mod.integration_change import RootChange
from mod.integration_change import ManageChange


VERSION_PATTERN = r'export VERSION_PATTERN=([0-9]+.[0-9]+)'
INTEGRATION_REPO = 'ssh://gerrit.ext.net.nokia.com:29418/MN/5G/COMMON/integration'
FEATURE_STREAM_MAP = {r'RCP[0-9]+\.[0-9]+_[0-9\.]+': r'.*_cloudbts_',
                      r'RCPvDU[0-9]+\.[0-9]+_[0-9\.]+': r'.*_allincloud_'}


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


def get_last_passed_package(branch, feature_id):
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
    # filter by FEATURE_STREAM_MAP
    new_streams = []
    for feature_regex, stream_regex in FEATURE_STREAM_MAP.items():
        for stream_name, stream_parttern in stream_dict.items():
            logging.info('Try to match %s by %s', feature_id, feature_regex)
            if re.match(feature_regex, feature_id):
                logging.info('Try to match %s by %s', stream_name, stream_regex)
                m = re.match(stream_regex, stream_name)
                if m:
                    new_streams.append(stream_parttern)
    if new_streams:
        stream_list = new_streams
    logging.info('Get packges by stream list %s', stream_list)
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


def frozen_config_yaml(previous_comp_dict, integration_dir, rest, integration_repo_ticket, old_sections):
    logging.info('Frozen config.yaml : %s', previous_comp_dict)
    stream_config_yaml_path = os.path.join(integration_dir, 'meta-5g-cb/config_yaml')
    logging.info('Find all config.yaml in %s', stream_config_yaml_path)
    stream_config_yaml_files = utils.find_files(stream_config_yaml_path, 'config.yaml')
    logging.info('Stream_config_yaml_files: %s', stream_config_yaml_files)
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
        for name, comp_dicts in previous_comp_dict.items():
            component_value = {}
            for config_key, component_info in stream_config_yaml['components'].items():
                if 'feature_component' in component_info and component_info['feature_component'] == name:
                    if 'features' in component_info:
                        features = component_info['features']
                        component_value = component_info
                    else:
                        logging.warn('Cannot find compnoent info for %s', name)
                    break
            feature_id = comp_dicts['feature_id']
            feature_list.append(feature_id)
            platform_id = comp_dicts['platform_id']
            if pipeline not in comp_dicts:
                continue
            comp_dict = comp_dicts[pipeline]
            logging.info('Frozen component %s in %s', comp_dict, stream_config_yaml_file)
            component_yaml_key = '{}:{}'.format(comp_dict['project'], comp_dict['component'])
            if feature_id not in features:
                features[feature_id] = {
                    "feature_delivered": False,
                    "platform_id": platform_id
                }
            if component_value:
                logging.info('Already frozened %s', component_value)
            else:
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
        if feature_id not in features:
            continue
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


def get_pipeline_comp_info(pass_packages, pipeline, get_comp_info_objs):
    if pipeline in get_comp_info_objs:
        return get_comp_info_objs[pipeline]
    elif pipeline in pass_packages:
        pass_package = pass_packages[pipeline]
        pass_package = trans_wft_name_to_tag(pass_package)
        return get_component_info.GET_COMPONENT_INFO(pass_package, no_dep_file=True, only_mapping_file=True)
    return {}


def get_comp_bbver(component_name, pass_packages, get_comp_info_objs={}):
    logging.info('Get bbver for %s', component_name)
    component_pvs = {}
    for pipeline, pass_package in pass_packages.items():
        pass_package = trans_wft_name_to_tag(pass_package)
        pipeline_comp_info_obj = get_pipeline_comp_info(pass_packages, pipeline, get_comp_info_objs)
        if not pipeline_comp_info_obj.if_bb_mapping:
            continue
        component_pv = pipeline_comp_info_obj.get_value_from_mapping_and_env(component_name, 'PV', 'pv')
        wft_component = pipeline_comp_info_obj.get_value_from_mapping_and_env(component_name, 'WFT_COMPONENT', 'pv')
        wft_name = pipeline_comp_info_obj.get_value_from_mapping_and_env(component_name, 'WFT_NAME', 'pv')
        component_obj = {}
        if component_pv:
            component_pv = re.sub(r'-r[0-9]+$', '', component_pv)
            component_obj['PV'] = component_pv
        if wft_component:
            component_obj['WFT_COMPONENT'] = wft_component
        if wft_name:
            component_obj['WFT_NAME'] = wft_name
        component_pvs[pipeline] = component_obj
    return component_pvs


def trans_wft_name_to_tag(wft_name):
    if '_' in wft_name:
        return wft_name.split('_')[1]
    return wft_name


def update_comps_frozen_together(previous_comp_dict, together_repo_dict):
    new_previous_comp_dict = {}
    for repo, repo_compoents in together_repo_dict.items():
        for name, comp_dict in previous_comp_dict.items():
            if name not in repo_compoents:
                continue
            for repo_compoent in repo_compoents:
                if repo_compoent in previous_comp_dict:
                    continue
                logging.info('Add component %s to previous_comp_dict', repo_compoent)
                new_comp_dict = copy.deepcopy(comp_dict)
                for comp_value in new_comp_dict.values():
                    if isinstance(comp_value, dict) and 'component' in comp_value:
                        comp_value['component'] = repo_compoent
                    new_previous_comp_dict[repo_compoent] = new_comp_dict
    previous_comp_dict.update(new_previous_comp_dict)


def get_version_from_work_dir(integration_obj, recipe_file, component_pv, component_run_infos):
    component_version = component_pv
    get_last_succeed = False
    if component_version:
        component_version = re.sub(r'-r[0-9]+$', '', component_version)
    for component_run_info in component_run_infos:
        component_name = component_run_info['name']
        component_regex = component_run_info['regex']
        if recipe_file.endswith('_{}.bb'.format(component_version)) and component_regex:
            recipe_dir = os.path.join(integration_obj.work_dir, os.path.dirname(recipe_file))
            recipe_filename = os.path.basename(recipe_file)
            recipe_filename_prefix = recipe_filename.split(component_version)[0].rstrip('_')
            # use recipe file to find latest version
            if not component_regex.startswith(recipe_filename_prefix):
                component_regex = component_regex.replace(component_name, recipe_filename_prefix)
            component_regex = component_regex.replace('{}-'.format(recipe_filename_prefix),
                                                      '{}_'.format(recipe_filename_prefix))
            logging.info('Find recipes by  %s', component_regex)
            logging.info('Find recipes from  %s', recipe_dir)
            recipe_list = utils.find_files(recipe_dir, '{}*.bb'.format(component_regex))
            logging.info('Find recipes %s', recipe_list)
            latest_version = '0'
            for recipe_candidate in recipe_list:
                logging.info('recipe file %s', recipe_candidate)
                recipe_candidate_file = os.path.basename(recipe_candidate)
                recipe_candidate_version = recipe_candidate_file.split('{}_'.format(recipe_filename_prefix))[1].replace('.bb', '')
                logging.info('recipe version %s', recipe_candidate_version)
                if LooseVersion(recipe_candidate_version) > LooseVersion(latest_version):
                    latest_version = recipe_candidate_version
            if latest_version != '0':
                component_version = latest_version
                get_last_succeed = True
                logging.info('Last version get from recipe files is %s', component_version)
                break
        elif component_regex:
            # run bitbake -e to get lastest version
            # generate component_run_obj for bitbake command
            bitbake_env_out = ''
            try:
                bitbake_env_out = bitbake_tools.get_component_env(component_run_info, integration_obj)
                component_version = bitbake_tools.get_component_env_value(bitbake_env_out, ['PV'])
                get_last_succeed = True
                logging.info('Last version get from bitbake is %s', component_version)
            except Exception:
                traceback.print_exc()
                logging.warn('Cannot run bitbake -e for %s', component_run_info)
    return component_version, get_last_succeed


def get_component_frozen_version(
        component_name, sub_builds, old_sections, integration_obj,
        previous_comp_dict, together_repo_dict, pass_packages,
        get_comp_info_objs, previous_succ_comp_dict):
    # if in together_repo component list and other component
    # already in previous_comp_dict, copy and continue
    for repo, repo_compoents in together_repo_dict.items():
        if component_name in repo_compoents:
            for repo_compoent in repo_compoents:
                if repo_compoent in previous_comp_dict and previous_comp_dict[repo_compoent]:
                    logging.info('Copy frozen info from: %s to: %s', repo_compoent, component_name)
                    logging.info(previous_comp_dict[repo_compoent])
                    previous_comp_obj = copy.deepcopy(previous_comp_dict[repo_compoent])
                    for previous_comp_obj_value in previous_comp_obj.values():
                        if 'component' in previous_comp_obj_value:
                            previous_comp_obj_value['component'] = component_name
                    previous_comp_dict[component_name] = previous_comp_obj
                    previous_succ_comp_obj = copy.deepcopy(previous_succ_comp_dict[repo_compoent])
                    for previous_succ_comp_obj_value in previous_succ_comp_obj.values():
                        if 'component' in previous_succ_comp_obj_value:
                            previous_succ_comp_obj_value['component'] = component_name
                    previous_succ_comp_dict[component_name] = previous_succ_comp_obj
                    return
    logging.info('Find matched subbuild for : %s', component_name)
    component_run_infos = bitbake_tools.gen_component_info(component_name, integration_obj)
    if not component_run_infos:
        logging.error('Cannot get %s from inc files', component_name)
    # get  component's old versoin with wft_name/wft_project
    for pipeline, sub_build_list in sub_builds.items():
        for sub_build in sub_build_list:
            if component_name == sub_build['component']:
                previous_comp_dict[component_name][pipeline] = copy.deepcopy(sub_build)
                previous_succ_comp_dict[component_name][pipeline] = copy.deepcopy(sub_build)
                # find version from old sections
                find_in_old_section = False
                for old_comp_value in old_sections.values():
                    if 'feature_component' in old_comp_value and old_comp_value['feature_component'] == component_name:
                        previous_comp_dict[component_name][pipeline]['version'] = old_comp_value['version']
                        previous_succ_comp_dict[component_name][pipeline]['version'] = old_comp_value['version']
                        find_in_old_section = True
                if find_in_old_section:
                    continue
    if component_name not in previous_comp_dict or not previous_comp_dict[component_name]:
        for pipeline, sub_build_list in sub_builds.items():
            pipeline_comp_info_obj = get_pipeline_comp_info(pass_packages, pipeline, get_comp_info_objs)
            if pipeline_comp_info_obj:
                component_pv = pipeline_comp_info_obj.get_value_from_mapping_and_env(component_name, 'PV', 'pv')
                wft_component = pipeline_comp_info_obj.get_value_from_mapping_and_env(component_name, 'WFT_COMPONENT', 'pv')
                wft_name = pipeline_comp_info_obj.get_value_from_mapping_and_env(component_name, 'WFT_NAME', 'pv')
                if component_pv:
                    matched_subs = []
                    for sub_build in sub_build_list:
                        logging.info('Compare %s and sub_build: %s', component_pv, sub_build)
                        logging.info('Compare wft_name %s and sub_build: %s', wft_name, sub_build)
                        if wft_component and wft_name:
                            if wft_component == sub_build['component'] and wft_name == sub_build['version']:
                                matched_sub = copy.deepcopy(sub_build)
                                if component_pv != sub_build['version']:
                                    matched_sub['version'] = component_pv
                                matched_subs = [matched_sub]
                                break
                        elif component_pv == sub_build['version']:
                            matched_subs.append(sub_build)
                    if matched_subs and len(matched_subs) == 1:
                        previous_comp_dict[component_name][pipeline] = copy.deepcopy(matched_subs[0])
                        previous_succ_comp_dict[component_name][pipeline] = copy.deepcopy(matched_subs[0])
    use_last_build = []
    if 'use_last_build' in previous_succ_comp_dict and previous_succ_comp_dict['use_last_build']:
        use_last_build = previous_succ_comp_dict['use_last_build']
    if component_name in previous_comp_dict and previous_comp_dict[component_name] and component_run_infos:
        logging.info('Get last version for %s', previous_comp_dict[component_name])
        for pipeline, sub_build in previous_comp_dict[component_name].items():
            if pipeline in use_last_build:
                logging.info('Already diceded to use version from last buid for %s', pipeline)
                continue
            pipeline_comp_info_obj = get_pipeline_comp_info(pass_packages, pipeline, get_comp_info_objs)
            recipe_file = pipeline_comp_info_obj.get_recipe_from_mapping(component_name)
            logging.info('Get last version for %s from work dir', pipeline)
            new_version, get_last_succeed = get_version_from_work_dir(integration_obj, recipe_file,
                                                                      sub_build['version'], component_run_infos)
            if not get_last_succeed:
                logging.error('Cannot get latest version for %s', component_name)
                for comp in previous_succ_comp_dict.keys():
                    if pipeline in previous_succ_comp_dict[comp]:
                        previous_comp_dict[comp][pipeline] = copy.deepcopy(previous_succ_comp_dict[comp][pipeline])
                if 'use_last_build' not in previous_succ_comp_dict:
                    previous_succ_comp_dict['use_last_build'] = []
                previous_succ_comp_dict['use_last_build'].append(pipeline)
            elif new_version != sub_build['version']:
                sub_build['version'] = new_version
    else:
        logging.error('Cannot get version for %s', component_name)


def prepare_workspace(work_dir, repo_url, repo_ver):
    """
    Clone and checkout proper integration/ revision
    """
    if os.path.exists(os.path.join(work_dir)):
        logging.info("Removing existing integration/ in %s", work_dir)
        shutil.rmtree(work_dir)

    os.makedirs(work_dir)
    git_integration = git.Git(work_dir)
    git_integration.init()
    git_integration.remote('add', 'origin', repo_url)
    logging.info("Executing git fetch %s %s", repo_url, repo_ver)
    git_integration.fetch(repo_url, repo_ver)
    git_integration.checkout('FETCH_HEAD')
    logging.info("Executing git fetch %s %s", repo_url, 'staging')
    git_integration.fetch(repo_url, 'staging')
    logging.info("Executing git submodule init + sync + update --init")
    git_integration.submodule("init")
    git_integration.submodule("sync")
    git_integration.submodule("update", "-f", "--init", "--recursive")


def run(gerrit_info_path, change_no, branch, component_config, mysql_info_path, *together_comps):
    # remove CR+2 first to aovid change merged
    # get together_comps
    logging.info('Together_comps: %s', together_comps)
    together_repo_dict = {}
    for together_string in together_comps:
        together_repo = together_string.split(':')[0]
        together_repo_dict[together_repo] = together_string.split(':')[1].split()
    logging.info('Together reop dict: %s', together_repo_dict)
    #  if integraiton ticket,  changed section in config.yaml.
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    root_change_obj = RootChange(rest, change_no)
    feature_id = root_change_obj.get_feature_id()
    platform_id = root_change_obj.get_platform_id()
    # get last passed package
    last_pass_package, pass_packages, integration_dir = get_last_passed_package(branch, feature_id)
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
    # rebase integration_repo_ticket
    if integration_repo_ticket:
        rest.rebase(integration_repo_ticket)
    # prepare integration workspace:
    integration_work_dir = os.path.join(os.getcwd(), 'integration_frozen')
    prepare_workspace(integration_work_dir, INTEGRATION_REPO, 'master')
    integration_obj = integration_repo.INTEGRATION_REPO('', '', work_dir=integration_work_dir)
    # get changed sections in global config_yaml
    old_sections = get_changed_in_global_config_yaml(rest, integration_repo_ticket)
    logging.info('Config_yaml old sections: %s', old_sections)
    # components in topic
    sub_builds = {}
    for pipeline, pass_package in pass_packages.items():
        sub_builds[pipeline] = wft_tools.get_subuild_from_wft(pass_package)
    logging.info('sub_builds: %s', sub_builds)
    previous_comp_dict = {}
    previous_succ_comp_dict = {}
    get_comp_info_objs = {}
    for component in component_list:
        if component[1] == 'MN/5G/COMMON/integration':
            logging.info('Skip component %s in integration repo ticket', component[0])
            continue
        component_name = component[0]
        previous_comp_dict[component_name] = {}
        previous_succ_comp_dict[component_name] = {}
        get_component_frozen_version(
            component_name, sub_builds, old_sections, integration_obj,
            previous_comp_dict, together_repo_dict, pass_packages,
            get_comp_info_objs, previous_succ_comp_dict)
        if not previous_comp_dict[component_name]:
            previous_comp_dict.pop(component_name)
        if component_name not in previous_comp_dict:
            # all components should be in WFT && BB_Mapping file,
            # so may be we need to raise Exception here
            logging.warn('Not find %s in previous loads: %s', component_name, pass_packages)
        else:
            previous_comp_dict[component_name]['feature_id'] = feature_id
            previous_comp_dict[component_name]['platform_id'] = platform_id

    if not previous_comp_dict:
        logging.info('No component adaption needed')
        return
    # frozen all gnb components together
    update_comps_frozen_together(previous_comp_dict, together_repo_dict)
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
    frozen_config_yaml(previous_comp_dict, integration_dir, rest, integration_repo_ticket, old_sections)


if __name__ == '__main__':
    fire.Fire(run)
