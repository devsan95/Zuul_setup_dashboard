#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import traceback
import sys
import argparse
from api import gerrit_api


def _parse_args():
    parser = argparse.ArgumentParser(description='init ticket label')
    parser.add_argument('ssh_server', type=str,
                        help='server url of gerrit')
    parser.add_argument('ssh_user', type=str,
                        help='user of gerrit')
    parser.add_argument('ssh_key', type=str,
                        help='private key of the user')
    parser.add_argument('change_id', type=str,
                        help='change id of gerrit ticket')
    args = parser.parse_args()
    return vars(args)


def _main(ssh_server, ssh_user, ssh_key, change_id):
    info = gerrit_api.get_ticket_info(ssh_user, ssh_server, change_id, ssh_key)
    print('info is:')
    print('=====================')
    print(type(info))
    print('=====================')
    print(info)
    print('=====================')
    integration_value = 1
    if 'topic' in info and info['topic'].lower().startswith('integration'):
        print('Ticket with topic begin with integration, set the label to -1')
        integration_value = -1
    result = gerrit_api.review_patch_set(
        ssh_user, ssh_server, change_id,
        ['integrated={}'.format(integration_value)], None,
        ssh_key)
    print(result)


if __name__ == '__main__':
    try:
        param = _parse_args()
        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
