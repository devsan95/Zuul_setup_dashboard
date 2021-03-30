#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-


import fire
import re
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
        zuul_change_obj = inte_change.IntegrationChange(rest, zuul_change)
        new_trs = get_trs_with_ps(ps_ver)
        if not new_trs:
            raise Exception("TRS not ready, need to wait TRS deliver")
        # delete edit
        try:
            rest.delete_edit(root_change)
        except Exception as e:
            print('delete edit failed, reason:')
            print(str(e))

        if [x for x in zuul_change_obj.get_components() if x.startswith('FTM') or x == 'ftm']:
            update_comment_msg = 'update_component:ftm,bb_ver,{}'.format(new_trs)
            print(update_comment_msg)
            rest.review_ticket(zuul_change, update_comment_msg)
    else:
        raise Exception("No PS found in ENV, please check root ticket!")


if __name__ == '__main__':
    fire.Fire(main)
