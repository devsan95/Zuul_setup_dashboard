#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
from __future__ import print_function

import json
import os
import re
from pprint import pprint

import fire

from api import file_api
from api import gerrit_rest
from api import git_api


def safe_get(v_list, idx, default=None):
    try:
        return v_list[idx]
    except IndexError:
        return default


def parse_changes(zuul_changes):
    change_map = {}
    change_list = zuul_changes.split('^')
    for item in change_list:
        slices = item.split(':')
        change_map[safe_get(slices, 0)] = {
            'branch': safe_get(slices, 1),
            'ref': safe_get(slices, 2)
        }
    return change_map


def parse_component(msg):
    components = set()
    reg = re.compile(r'  - COMP <(.*?)>')
    miter = reg.findall(msg)
    for m in miter:
        components.add(m)
    return list(components)


def run(info_path,
        gerrit_url='https://gerrit.ext.net.nokia.com/gerrit',
        env_path=None):
    # get info from parameter
    pipeline = os.environ.get('ZUUL_PIPELINE')
    # change_ids = os.environ.get('ZUUL_CHANGE_IDS')
    change = os.environ.get('ZUUL_CHANGE')
    patchset = os.environ.get('ZUUL_PATCHSET')
    branch = os.environ.get('ZUUL_BRANCH')
    url = os.environ.get('ZUUL_URL')
    changes = os.environ.get('ZUUL_CHANGES')
    repo = os.environ.get('ZUUL_PROJECT')
    zuul_ref = os.environ.get('ZUUL_REF')

    # get commit msg and parse component
    rest = gerrit_rest.GerritRestClient(gerrit_url, None, None)
    commit = rest.get_commit(change)
    component = parse_component(commit.get('message'))
    changes_map = parse_changes(changes)

    # info list
    # repo
    # branch
    # changeset
    # module
    info_dict = {
        'component': component,
        'pipeline': pipeline,
        'repo': repo,
        'changeid': '{},{}'.format(change, patchset),
        'branch': branch
    }

    info_json = json.dumps(info_dict)
    print(info_json)
    file_api.save_file(info_json, info_path)

    if env_path:
        # check if there are env
        pprint(changes_map)
        if 'MN/5G/COMMON/env' in changes_map:
            env_path = 'env-config.d/ENV'
            env_repo = 'MN/5G/COMMON/env'
        else:
            env_path = 'env/env-config.d/ENV'
            env_repo = 'MN/5G/COMMON/integration'

        if env_repo in changes_map:
            print('{} is in the dependency'.format(env_repo))
            # get env
            temp = file_api.TempFolder('env_repo')
            env_temp_path = temp.get_directory('env')
            git_api.git_clone_with_refspec_and_commit(
                '{}/{}'.format(url, env_repo),
                zuul_ref,
                'FETCH_HEAD',
                env_temp_path
            )

            # save env file
            content = None
            try:
                with open(os.path.join(env_temp_path, env_path)) as f:
                    content = f.read()
                    print(content)
            except Exception as e:
                print(str(e))
                print("There's no env file {0}/{1}, will not update env file".format(env_temp_path, env_path))
            if content:
                print('Write env')
                file_api.save_file(content, env_path)


if __name__ == '__main__':
    fire.Fire(run)
