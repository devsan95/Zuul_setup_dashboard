#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import re
import fire

from api import gerrit_rest
from api import config
from mod.integration_change import RootChange


CONF = config.ConfigTool()
CONF.load('repo')
COMP_INFO_DICT = {}
SBTS_RE = re.compile(r'^SBTS\d{2}(.\d)?_ENB_\d{4}_\d{6}_\d{6}$')

def update_base(root_change, gerrit_info_path, base_package):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    op = RootChange(rest, root_change)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    base_list = base_package.split(',')
    for base_pkg_name in base_list:
        if base_pkg_name == 'use_default_base':
            rest.review_ticket(int_change, 'use_default_base')
        else:
            ver_partten = base_pkg_name.split('_')[0] if SBTS_RE.match(base_pkg_name) \
                else '.'.join(base_pkg_name.split('.')[0:2])
            rest.review_ticket(
                int_change,
                'update_base:{},{}'.format(ver_partten, base_pkg_name))


if __name__ == '__main__':
    fire.Fire()
