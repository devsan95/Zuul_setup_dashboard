#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import traceback
import sys
import argparse
import json
import api.gerrit_api


def _parse_args():
    parser = argparse.ArgumentParser(description='Monitor ticket status')
    parser.add_argument('ssh_server', type=str,
                        help='server url of gerrit')
    parser.add_argument('ssh_user', type=str,
                        help='user of gerrit')
    parser.add_argument('ssh_key', type=str,
                        help='private key of the user')
    parser.add_argument('ticket_json', type=str,
                        help='Example: {"root": "123", '
                             '"tickets": ["124", "125"], '
                             '"manager": "126"}')
    args = parser.parse_args()
    return vars(args)


def _main(ssh_server, ssh_user, ssh_key, ticket_json):
    targets = json.loads(ticket_json)
    print('Integration test done, make root and manager ticket into gating...')
    api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['manager'],
                                    ['Verified=+1', 'Integration=+1',
                                     'Code-Review=+2'], None,
                                    ssh_key)
    api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['root'],
                                    ['Verified=+1', 'Integration=+1',
                                     'Code-Review=+2'], None,
                                    ssh_key)


if __name__ == '__main__':
    try:
        traceback.print_exc()
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
