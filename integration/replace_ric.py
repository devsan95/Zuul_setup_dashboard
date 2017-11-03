#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import traceback
import sys
import argparse
import time
import api.gerrit_api
import api.gerrit_rest
import api.file_api
import re


def _parse_args():
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('ric_path', type=str,
                        help='')
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


def fetch_ric(rest, ric_path, description):
    ric = None
    lines = description.split('\n')
    ric_repo = None
    ric_change = None
    r = re.compile(r'  - RICREPO <(.*)> <(.*)>')
    for line in lines:
        m = r.match(line)
        if m:
            ric_repo = m.group(1)
            ric_change = m.group(2)
            break
    if not ric_change:
        raise Exception('Cannot find ric change')

    print(ric_repo)

    data = rest.query_ticket(ric_change)
    rest_id = data['id']

    content = rest.get_file_change('ric', rest_id)
    ric = content['new']

    if not ric:
        raise Exception('ric is empty')

    api.file_api.save_file(ric, ric_path, False)

    return ric


def parse_ric_list(subject):
    ret_dict = {}
    lines = subject.split('\n')
    r = re.compile(r'  - RIC <(.*)> <(.*)>')
    for line in lines:
        m = r.match(line)
        if m:
            ret_dict[m.group(1)] = m.group(2)
    return ret_dict


def update_ric(ric_path, ric_dict, zuul_url, zuul_ref):
    with open(ric_path) as f:
        ric = f.read()
        ric_lines = ric.split('\n')
    for comp, repo in ric_dict.items():
        for line in ric_lines:
            if comp in line:
                if ''.startswith('VNE;'):
                    slices = line.split(';;')
                    line = '{};;{};;{};{};'.format(
                        slices[0], comp, '{}/{}'.format(zuul_url, repo),
                        zuul_ref)
                else:
                    slices = line.split(';')
                    slices[3] = '{}/{}'.format(zuul_url, repo)
                    slices[4] = zuul_ref
                    line = ';'.join(slices)
    new_ric = '\n'.join(ric_lines)
    api.file_api.save_file(new_ric, ric_path, False)


def _main(ric_path, change_id, rest_url, rest_user, rest_pwd, auth_type):
    rest = api.gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()

    rest_id = ''
    description = ''

    while True:
        try:
            data = rest.query_ticket(change_id)
        except Exception as e:
            print(str(e))
            time.sleep(10)

        if data and 'id' in data:
            rest_id = data['id']
            break

    while True:
        try:
            data = rest.get_commit(rest_id)
        except Exception as e:
            print(str(e))
            time.sleep(10)

        if data and 'message' in data:
            description = data['message']
            break

    fetch_ric(rest, ric_path, description)
    ric_dict = parse_ric_list(description)
    if len(ric_dict) > 0:
        update_ric(ric_path, ric_dict)


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
