#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import fire
import re
import sys
import requests
from api import gerrit_rest
from api import env_repo as get_env_repo
from mod import config_yaml
from mod import integration_change
from mod import wft_tools
from integration_add_component import get_base_load

GERRT_SERVICE_URL = "ssh://gerrit.ext.net.nokia.com:29418/"


def get_ps_version(rest, root_change, env_file_path):
    change_files = rest.get_file_list(root_change)
    if env_file_path in change_files:
        if not env_file_path:
            config_yaml_change = rest.get_file_change('config.yaml', root_change)
            old_config_yaml = config_yaml.ConfigYaml(config_yaml_content=config_yaml_change['old'])
            updated_changes = old_config_yaml.get_changes(config_yaml_change['new'])[0]
            if 'PS:PS' in updated_changes:
                return updated_changes['PS:PS']['version']
        else:
            for line in rest.get_file_change(env_file_path, root_change)['new_diff'].split('\n'):
                if 'ENV_PS_REL' in line:
                    return line.split('=')[-1]
    return ''


def service_remote_trigger(data):
    proxies = {"http": "", "https": ""}
    try:
        jenkins_url = data.pop('jenkins_url')
        job_name = data.pop('job_name')
        url = '{}/job/{}/buildWithParameters'.format(jenkins_url, job_name)
    except Exception:
        url = data.pop('url')

    res = requests.post(url, data, proxies=proxies)
    print(res.content)
    return res.ok


def get_component_list(change_list):
    component_list = []
    for i in change_list:
        component_name = re.search('ps/(.*?)/', i) or re.search('(vl1-hi)/integration_tmp/', i)
        if component_name:
            component_list.append(component_name.group(1))
    return component_list


def get_component_extend_data(component):
    component_info = {
        'sma-lite': {'jenkins_url': 'http://10.66.13.21:8080/jenkins/', 'job_name': 'ASI_SMA_5G_PS_REL_Trigger', 'token': '123456'},
        'scoam-asi-controller': {'jenkins_url': 'http://krak150.emea.nsn-net.net:8080/', 'job_name': 'ASIR_CPI_Trigger', 'token': 'BNM732V5K6J3J4OP43'},
        'vl1-hi': {'url': 'https://gitlab.l1.nsn-net.net/api/v4/projects/2604/trigger/pipeline', 'token': 'e3c8754f1fdc94fb2fbf379a977892'}
    }
    try:
        return component_info[component]
    except Exception:
        print "This component is not defined."
        sys.exit(2)


def get_repo_and_version(rest, change_no):
    change_dict = rest.get_change(change_no)
    commit_dict = rest.get_commit(change_no)
    env_repo = GERRT_SERVICE_URL + str(change_dict.get("project"))
    env_version = str(commit_dict.get("commit"))
    return env_repo, env_version


def main(gerrit_info_path, change_id, branch, pipeline):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    git_hash_review = rest.get_commit(change_id)['commit']
    change_list = rest.get_file_list(change_id).keys()
    int_change_obj = integration_change.IntegrationChange(rest, change_id)
    depends_comps = int_change_obj.get_depends()
    root_change_no = None
    depends_on = int_change_obj.get_depends_on()
    if not depends_on:
        print('This component has been detached')
        return
    for depends_comp in depends_comps:
        print('depends_comp: {}'.format(depends_comp))
        if depends_comp[2] == 'root':
            root_change_no = depends_comp[1]
    if not root_change_no:
        raise Exception("Can not get root ticket")
    env_repo, env_version = get_repo_and_version(rest, root_change_no)
    env_info = get_env_repo.get_env_repo_info(rest, root_change_no)
    env_repo_info = env_info[0]
    print env_repo_info
    ps_version = get_ps_version(root_change=root_change_no, rest=rest, env_file_path=env_info[1])
    component_list = get_component_list(change_list)
    print "[INFO] env repo: {0}".format(env_repo)
    integration_mode = int_change_obj.get_integration_mode()
    change_name = int_change_obj.get_change_name()
    print('integration_mode:{}'.format(integration_mode))
    if integration_mode == 'FIXED_BASE':
        root_change = integration_change.RootChange(rest, root_change_no)
        inte_change_no = root_change.get_components_changes_by_comments()[1]
        base_load = get_base_load(rest, inte_change_no, with_sbts=False)
        base_load = wft_tools.get_wft_release_name(base_load)
        print('base_load:{}'.format(base_load))
        subbuilds = wft_tools.get_subuild_from_wft(base_load)
        for build in subbuilds:
            if build['component'] == change_name:
                component_baseline = build['version']
    else:
        component_baseline = 'head'
    data = {'ENV_REPO': env_repo, 'ENV_VERSION': env_version, 'PIPELINE': pipeline, 'BRANCH': branch, 'GIT_HASH_REVIEW': git_hash_review, 'COMPONENT_BASELINE': component_baseline}
    ps_prompt = ''
    for component in component_list:
        if component in ['vl1-hi']:
            data = dict([('variables[{}]'.format(key), value) for key, value in data.items()])
            data.update({'ref': branch})
        else:
            if not ps_version:
                print "[INFO] No PS changes for {}, skip component trigger".format(component)
                continue
            ps_prompt = 'with PS version {} '.format(ps_version)
            data.update({'PS_VERSION': ps_version})
        component_extend_data = get_component_extend_data(component)
        data = dict(data.items() + component_extend_data.items())
        print('data:\n{}'.format(data))
        service_remote_trigger(data)
        print "[INFO] Triggered component {} {}integration successfully".format(component, ps_prompt)


if __name__ == '__main__':
    fire.Fire(main)
