#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-


import fire
import re
import xml.etree.ElementTree as ET
from api import gerrit_rest
from api import retry
from mod import integration_change as inte_change
from mod import wft_tools


def get_root_change(rest, zuul_change):
    zuul_change_obj = inte_change.IntegrationChange(rest, zuul_change)
    depends_comps = zuul_change_obj.get_depends()
    for depends_comp in depends_comps:
        print('depends_comp: {}'.format(depends_comp))
        if depends_comp[2] == 'root':
            return depends_comp[1]
    raise Exception('Cannot get root change for {}'.format(inte_change))


def get_ps_change(rest, flist, change_no):
    ps_ver = ''
    for f in flist:
        if "env-config.d/ENV" in f:
            file_change = rest.get_file_change(f, change_no)
            ps_ver = re.search(r'ENV_PS_REL=(.*)', file_change['new']).group(1)
            break

    return ps_ver


def get_trs_with_ps(ps_ver):
    custom_filter = 'custom_filter[branch_for_names][]=5G_CPI&' \
                    'custom_filter[sorting_direction]=desc'
    build_list = wft_tools.get_build_list_from_custom_filter(custom_filter)
    root = ET.fromstring(build_list)
    baseline = ''

    for build in root.findall('build'):
        baseline = build.find('baseline').text.strip()
        if ps_ver in wft_tools.get_ps(baseline):
            print ('{} with {} found in WFT CPI branch'.format(baseline, ps_ver))
            return baseline

    print ('No TRS with {} found in WFT CPI branch'.format(ps_ver))
    return baseline


def update_trs_in_root(rest, trs_ver, root_change):
    env_path = 'env/env-config.d/ENV'
    env_content = rest.get_file_content(env_path, root_change)

    reg = re.compile(r'ENV_TRS=(.*)')
    base_trs = reg.search(env_content).groups()[0]
    if not base_trs:
        status = 'Error'
        return status
    if not trs_ver:
        status = 'Notrs'
        return status
    if base_trs == trs_ver:
        status = 'Same'
        return status

    new_env_content = env_content.replace(base_trs, trs_ver)
    rest.add_file_to_change(root_change, env_path, new_env_content)
    rest.publish_edit(root_change)
    status = 'Updated'
    return status


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
        status = update_trs_in_root(rest, new_trs, root_change)
        if 'Updated' in status:
            review_trs_ticket(rest, zuul_change,
                              'update TRS in ENV successfully', {'Code-Review': 2})
        elif 'Same' in status:
            print ('{} already in ENV'.format(new_trs))
            review_trs_ticket(rest, zuul_change,
                              'update TRS in ENV successfully', {'Code-Review': 2})
        elif 'Notrs' in status:
            print ('TRS not ready, need to wait TRS deliver')
            exit(1)
        else:
            print ('[ERROR]Can not get trs in ENV, please check root ticket!')
            exit(1)
    else:
        print ('[ERROR]No PS found in ENV, please check root ticket!')
        exit(1)


if __name__ == '__main__':
    fire.Fire(main)
