#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import argparse
import sys
import traceback

from api import gerrit_rest


def strip_end(text, suffix):
    if not text.endswith(suffix):
        return text
    return text[:len(text) - len(suffix)]


def strip_begin(text, prefix):
    if not text.startswith(prefix):
        return text
    return text[len(prefix):]


def _parse_args():
    parser = argparse.ArgumentParser(description='Update Submodule')
    parser.add_argument('rest_url', type=str,
                        help='')
    parser.add_argument('rest_user', type=str,
                        help='')
    parser.add_argument('rest_pwd', type=str,
                        help='')
    parser.add_argument('auth_type', type=str, default='digest',
                        help='')
    parser.add_argument('changeid', type=str,
                        help='')
    parser.add_argument('reviewer', type=str,
                        help='')
    args = parser.parse_args()
    return vars(args)


def run(rest_url, rest_user, rest_pwd, auth_type, changeid, reviewer):
    rest = gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()

    rest_id = rest.get_ticket(changeid)['id']
    rest.add_reviewer(rest_id, reviewer)


if __name__ == '__main__':
    try:
        param = _parse_args()

        run(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
