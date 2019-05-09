#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import click
from api import gerrit_rest
from api import gerrit_api


def check_root_integrated(ssh_server, ssh_port, ssh_user, ssh_key, root_change):
    root_integrated = True
    try:
        minus_one = gerrit_api.does_patch_set_match_condition(
            ssh_user, ssh_server, root_change,
            ['label:Integrated=-1'],
            ssh_key, port=ssh_port)
        if minus_one:
            print('The root change is integrated-1')
        minus_two = gerrit_api.does_patch_set_match_condition(
            ssh_user, ssh_server, root_change,
            ['label:Integrated=-2'],
            ssh_key, port=ssh_port)
        if minus_two:
            print('The root change is integrated-2')
        if minus_one or minus_two:
            root_integrated = False
    except Exception:
        print('Give integrated label met problem')
    print('root change integrated value: {}'.format(root_integrated))
    return root_integrated


@click.command()
@click.option('--root_change', help='the root gerrit change number')
@click.option('--gerrit_info_path', help='gerrit info path')
@click.option('--ssh_server', help='ssh_server')
@click.option('--ssh_port', help='ssh_port')
@click.option('--ssh_user', help='ssh_user')
@click.option('--ssh_key', help='ssh_key')
def main(root_change, gerrit_info_path, ssh_server, ssh_port, ssh_user, ssh_key):

    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    if not check_root_integrated(ssh_server, ssh_port, ssh_user, ssh_key, root_change):
        gerrit_api.review_patch_set(ssh_user, ssh_server, root_change,
                                    ['Verified=+1', 'Integrated=+2'], None,
                                    ssh_key, port=ssh_port)
    rest.review_ticket(root_change, 'going to deliver this feature, code review+2 given to root change', {'Code-Review': 2})


if __name__ == '__main__':
    main()
