#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import os
import json
import yaml
import click
from api import gerrit_rest
from api import gerrit_api
from mod import config_yaml
from mod.integration_change import RootChange
import update_depends


def check_root_integrated(ssh_server, ssh_port, ssh_user, ssh_key, root_change):
    root_integrated = True
    try:
        minus_one = gerrit_api.does_patch_set_match_condition(
            ssh_user, ssh_server, root_change,
            ['label:Integrated=-1'],
            ssh_key, port=ssh_port)
        if minus_one:
            print('The root change is integrated-1')
            root_integrated = False
    except Exception:
        print('[Info] root change is not integrated-1')
    try:
        minus_two = gerrit_api.does_patch_set_match_condition(
            ssh_user, ssh_server, root_change,
            ['label:Integrated=-2'],
            ssh_key, port=ssh_port)
        if minus_two:
            print('The root change is integrated-2')
            root_integrated = False
    except Exception:
        print('[Info] root change is not integrated-2')
    print('[Info] root change get integrated+1 label: {}'.format(root_integrated))
    return root_integrated


def get_config_yaml_change(rest, change_no):
    config_yaml_change = {}
    try:
        config_yaml_change = rest.get_file_change('config.yaml', change_no)
    except Exception:
        print('Cannot find config.yaml for %s', change_no)

    updated_dict = None
    if 'new_diff' in config_yaml_change and config_yaml_change['new_diff']:
        config_yaml_obj = config_yaml.ConfigYaml(config_yaml_content=config_yaml_change['new'])
        updated_dict, removed_dict = config_yaml_obj.get_changes(yaml.safe_load(config_yaml_change['old']))
    print('[Info] The changed config yaml content: {}'.format(updated_dict))
    return updated_dict


def prepare_trigger_file(rest, root_change, skytrack_log_collector):
    root_obj = RootChange(rest, root_change)
    if not root_obj.get_ecl_branch():
        print('[Info] no ecl branc info, no need to prepare trigger file')
        return

    skytrack_log_collector.append('ECL branch existed, trying to increment new build in WFT')
    config_yaml_change_dict = get_config_yaml_change(rest, root_change)
    if not config_yaml_change_dict:
        print('[Warning]No change in config yaml!')
        return
    param_dict = {}
    for k, v in config_yaml_change_dict.items():
        for key, value in v.items():
            if key == 'version':
                param_dict[k] = {'version': value}
    param_str = json.dumps(param_dict)
    print('[Info] The changed content is: {}'.format(param_str))

    trigger_file = os.path.join(os.environ['WORKSPACE'], "increment_ecl.prop")
    with open(trigger_file, 'w') as trigger_file_fd:
        trigger_file_fd.write(
            "ecl_branch={}\nchanged_content={}\n".format(
                root_obj.get_ecl_branch(),
                param_str
            )
        )


@click.command()
@click.option('--root_change', help='the root gerrit change number')
@click.option('--gerrit_info_path', help='gerrit info path')
@click.option('--ssh_server', help='ssh_server')
@click.option('--ssh_port', help='ssh_port')
@click.option('--ssh_user', help='ssh_user')
@click.option('--ssh_key', help='ssh_key')
def main(root_change, gerrit_info_path, ssh_server, ssh_port, ssh_user, ssh_key):

    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    update_depends.remove_meta5g_change(rest, root_change)
    skytrack_log_collector = []
    if not check_root_integrated(ssh_server, ssh_port, ssh_user, ssh_key, root_change):
        gerrit_api.review_patch_set(ssh_user, ssh_server, root_change,
                                    ['Verified=+1', 'Integrated=+2'], None,
                                    ssh_key, port=ssh_port)
    rest.review_ticket(root_change, 'going to deliver this feature, code review+2 given to root change', {'Code-Review': 2})
    skytrack_log_collector.append('Go Succeed! Trigger integration changes start to merge!')

    prepare_trigger_file(rest, root_change, skytrack_log_collector)

    if len(skytrack_log_collector) > 0:
        print('integration framework web output start')
        for log in skytrack_log_collector:
            print(log)
        print('integration framework web output end')


if __name__ == '__main__':
    main()
