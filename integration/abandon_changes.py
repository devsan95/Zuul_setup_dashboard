#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import traceback
import sys
import argparse
import api.gerrit_api
import api.gerrit_rest
import api.file_api
import re
import json


def _parse_args():
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('change_id', type=str,
                        help='change id')
    parser.add_argument('rest_url', type=str,
                        help='')
    parser.add_argument('rest_user', type=str,
                        help='')
    parser.add_argument('rest_pwd', type=str,
                        help='')
    parser.add_argument('auth_type', type=str, default='digest',
                        help='')
    args = parser.parse_args()
    return vars(args)


def strip_begin(text, prefix):
    if not text.startswith(prefix):
        return text
    return text[len(prefix):]


def parse_comments(change_id, rest):
    json_re = re.compile(r'Tickets-List: ({.*})')
    comment_list = rest.generic_get('/changes/{}/detail'.format(change_id))
    for msg in reversed(comment_list['messages']):
        msg = msg['message']
        result_list = json_re.findall(msg)
        if len(result_list) > 0:
            return json.loads(result_list[0])
    return None


def _main(change_id,
          rest_url, rest_user, rest_pwd, auth_type):
    rest = api.gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()
    changes = parse_comments(change_id, rest)
    if 'root' in changes and changes['root']:
        print('Abandoning {}'.format(changes['root']))
        try:
            rest.abandon_change(changes['root'])
        except Exception as e:
            print(e)
    if 'manager' in changes and changes['manager']:
        print('Abandoning {}'.format(changes['manager']))
        try:
            rest.abandon_change(changes['manager'])
        except Exception as e:
            print(e)
    if 'tickets' in changes and changes['tickets']:
        for change_id in changes['tickets']:
            print('Abandoning {}'.format(change_id))
            try:
                rest.abandon_change(change_id)
            except Exception as e:
                print(e)


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
