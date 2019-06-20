#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import fire
import re
import sys
import requests
from api import gerrit_rest


def get_ps_version(msg):
    reg = re.compile('<(.*?)> on <(.*?)> of <PS Integration (.*?)>')
    ps_version = reg.search(msg).group(2)
    if not ps_version:
        raise Exception("Cannot find related PS version")
    return ps_version


def jenkins_remote_trigger(data):
    proxies = {"http": "", "https": ""}
    try:
        jenkins_url = data.pop('jenkins_url')
        job_name = data.pop('job_name')
    except Exception:
        print "jenkins_url or job_name is not provided!"
    url = '{}/job/{}/buildWithParameters'.format(jenkins_url, job_name)
    res = requests.post(url, data, proxies=proxies)
    print(res.content)
    return res.ok


def get_component_list(change_list):
    component_list = []
    for i in change_list:
        reg = re.compile('ps/(.*?)/')
        component_name = reg.search(i)
        if component_name:
            component_list.append(component_name.group(1))
    return component_list


def get_component_extend_data(component):
    component_info = {
        'sma-lite': {'jenkins_url': 'http://10.66.13.21:8080/jenkins/', 'job_name': 'ASI_SMA_Trunk_5G_PS_REL_Trigger', 'token': '123456'},
        'scoam-asi-controller': {'jenkins_url': 'http://krak150.emea.nsn-net.net:8080/', 'job_name': 'ASIR_CPI_Trigger', 'token': 'BNM732V5K6J3J4OP43'}
    }
    try:
        return component_info[component]
    except Exception:
        print "This component is not defined."
        sys.exit(2)


def main(gerrit_info_path, change_id, branch, pipeline, repo_url, repo_ver):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    git_hash_review = rest.get_commit(change_id)['commit']
    msg = rest.get_commit(change_id)['message']
    change_list = rest.get_file_list(change_id).keys()
    ps_version = get_ps_version(msg)
    env_repo = '{}/MN/5G/COMMON/env'.format(repo_url)
    env_version = repo_ver
    component_list = get_component_list(change_list)
    data = {'PS_VERSION': ps_version, 'ENV_REPO': env_repo, 'ENV_VERSION': env_version, 'PIPELINE': pipeline, 'BRANCH': branch, 'GIT_HASH_REVIEW': git_hash_review}
    for component in component_list:
        print "[INFO] Triggering component {} with {} integration ...".format(component, ps_version)
        component_extend_data = get_component_extend_data(component)
        data = dict(data.items() + component_extend_data.items())
        jenkins_remote_trigger(data)
        print "[INFO] Triggered component {} with {} integration successfully".format(component, ps_version)


if __name__ == '__main__':
    fire.Fire(main)
