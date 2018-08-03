#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import fire
import urllib3

from api import gerrit_rest
from mod import integration_change

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def run(gerrit_info_path, root_change_no):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    root_change = integration_change.RootChange(rest, root_change_no)
    all_changes = root_change.get_all_changes_by_comments(with_root=False)
    for change_no in all_changes:
        change = integration_change.IntegrationChange(rest, change_no)
        lv = change.get_label_status('Verified')
        lcr = change.get_label_status('Code-Review')
        lgk = change.get_label_status('Gatekeeper')
        print('Change {} v {} cr {} gk {}'.format(change_no, lv, lcr, lgk))
        if lv == 'approved' and lcr == 'approved' and lgk != 'approved':
            print('Change {} need regate'.format(change_no))
            change.review('regate', None)


if __name__ == '__main__':
    fire.Fire(run)
