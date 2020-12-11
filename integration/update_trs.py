#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-


import fire
import re
import yaml
import xml.etree.ElementTree as ET
from api import gerrit_rest
from api import retry
from mod import integration_change as inte_change
from mod import wft_tools
from mod import config_yaml


def get_root_change(rest, zuul_change):
    zuul_change_obj = inte_change.IntegrationChange(rest, zuul_change)
    root_change = zuul_change_obj.get_root_change()
    if not root_change:
        raise Exception('Cannot get root change for {}'.format(inte_change))
    return root_change


def get_ps_change(rest, flist, change_no):
    ps_ver = ''
    for f in flist:
        if "env-config.d/ENV" in f:
            print('Getting PS version from {}...'.format('env-config.d/ENV'))
            file_change = rest.get_file_change(f, change_no)
            ps_ver = re.search(r'ENV_PS_REL=(.*)', file_change['new']).group(1)
            break
        elif "config.yaml" in f:
            # get ps version from config.yaml
            try:
                print('Getting PS version from {}...'.format('config.yaml'))
                config_yaml_content = rest.get_file_content('config.yaml', change_no)
                config_yaml_obj = config_yaml.ConfigYaml(config_yaml_content=config_yaml_content)
                ps_ver = config_yaml_obj.get_section_value('PS:PS', 'version')
            except Exception:
                print('Cannot find {} in {}'.format('config.yaml', change_no))
            break
    return ps_ver


def get_trs_with_ps(ps_ver):
    custom_filter = 'custom_filter[branch_for_names][]=5G_CPI&' \
                    'custom_filter[sorting_direction]=desc'
    build_list = wft_tools.get_build_list_from_custom_filter(custom_filter)
    root = ET.fromstring(build_list)

    for build in root.findall('build'):
        trs = build.find('baseline').text.strip()
        if ps_ver in wft_tools.get_ps(trs):
            print ('{} with {} found in WFT CPI branch'.format(trs, ps_ver))
            return trs

    print ('No TRS with {} found in WFT CPI branch'.format(ps_ver))
    return None


def update_trs_in_env_file(rest, trs_ver, root_change, zuul_change):
    print("Trying to update TRS in env/env-config.d/ENV")
    env_path = 'env/env-config.d/ENV'
    env_content = rest.get_file_content(env_path, root_change)

    reg = re.compile(r'ENV_TRS=(.*)')
    base_trs = reg.search(env_content).groups()[0]

    if base_trs == trs_ver:
        print('{} already in ENV'.format(trs_ver))
    else:
        print("Updating TRS from {0} to {1}".format(base_trs, trs_ver))
        new_env_content = env_content.replace(base_trs, trs_ver)
        rest.add_file_to_change(root_change, env_path, new_env_content)
        rest.publish_edit(root_change)
    review_trs_ticket(rest, zuul_change,
                      'update TRS in ENV successfully', {'Code-Review': 2})


def update_trs_in_config_yaml(rest, trs_ver, root_change, zuul_change):
    print("Trying to update TRS in config.yaml")
    config_yaml_file = 'config.yaml'
    yaml_content = rest.get_file_content(config_yaml_file, root_change)
    config_yaml_obj = config_yaml.ConfigYaml(config_yaml_content=yaml_content)

    base_trs = config_yaml_obj.get_section_value('Common:FTM', 'version')

    if base_trs == trs_ver:
        print('{} already in config.yaml'.format(trs_ver))
    else:
        print("Updating TRS from {0} to {1}".format(base_trs, trs_ver))
        config_yaml_obj.update_by_env_change({'Common:FTM': trs_ver})
        config_yaml_content = yaml.safe_dump(config_yaml_obj.config_yaml, default_flow_style=False)
        rest.add_file_to_change(root_change, config_yaml_file, config_yaml_content)
        rest.publish_edit(root_change)
    review_trs_ticket(rest, zuul_change,
                      'update TRS in config.yaml successfully', {'Code-Review': 2})


def check_if_env_exists(change_file_list):
    env_exists, config_yaml_exists = False, False
    for f in change_file_list:
        if "env-config.d/ENV" in f:
            env_exists = True
        elif "config.yaml" in f:
            config_yaml_exists = True
    return env_exists, config_yaml_exists


def review_trs_ticket(rest, zuul_change, message, code_review):
    retry.retry_func(
        retry.cfn(rest.review_ticket, zuul_change, message, code_review),
        max_retry=10, interval=3
    )


def main(gerrit_info_path, zuul_change):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    review_trs_ticket(rest, zuul_change,
                      'remove code-review', {'Code-Review': 0})
    root_change = get_root_change(rest, zuul_change)
    flist = retry.retry_func(
        retry.cfn(rest.get_file_list, root_change),
        max_retry=10, interval=3
    )
    ps_ver = get_ps_change(rest, flist, root_change)

    if ps_ver:
        new_trs = get_trs_with_ps(ps_ver)
        if not new_trs:
            raise Exception("TRS not ready, need to wait TRS deliver")
        # delete edit
        try:
            rest.delete_edit(root_change)
        except Exception as e:
            print('delete edit failed, reason:')
            print(str(e))

        env_exists, config_yaml_exists = check_if_env_exists(flist)
        if env_exists:
            update_trs_in_env_file(rest, new_trs, root_change, zuul_change)
        elif config_yaml_exists:
            update_trs_in_config_yaml(rest, new_trs, root_change, zuul_change)
    else:
        raise Exception("No PS found in ENV, please check root ticket!")


if __name__ == '__main__':
    fire.Fire(main)
