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
import json
import submodule_handle
from slugify import slugify


def _parse_args():
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('zuul_url', type=str,
                        help='')
    parser.add_argument('zuul_ref', type=str,
                        help='')
    parser.add_argument('output_path', type=str,
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


def strip_begin(text, prefix):
    if not text.startswith(prefix):
        return text
    return text[len(prefix):]


def parse_ric_list(subject, zuul_url, zuul_ref):
    ret_dict = {}
    lines = subject.split('\n')
    r = re.compile(r'  - RIC <(.*)> <(.*)>')
    for line in lines:
        m = r.match(line)
        if m:
            key = m.group(1).strip('"').strip()
            value = m.group(2).strip('"').strip()
            ret_dict[key] = {'repo_url': '{}/{}'.format(zuul_url, value),
                             'repo_ver': zuul_ref}
    return ret_dict


def parse_ric_commit_list(subject):
    ret_dict = {}
    lines = subject.split('\n')
    r = re.compile(r'  - RICCOMMIT <(.*)> <(.*)>')
    for line in lines:
        m = r.match(line)
        if m:
            key = m.group(1)
            key = key.strip('"')
            value = m.group(2)
            value = value.strip('"')
            ret_dict[key] = {'repo_ver': value}
    return ret_dict


def get_env_commit(msg, rest):
    retd = {}
    topic = submodule_handle.get_topic_from_commit_message(msg)
    branch_name = 'inte_test/{}'.format(slugify(topic))

    repo = submodule_handle.get_temp_repo_info_from_commit_message(msg)
    if 'MN/5G/COMMON/env' in repo:
        branches = rest.list_branches('MN/5G/COMMON/env')
        for branch in branches:
            branch['ref'] = strip_begin(branch['ref'], 'refs/heads/')

        for branch in branches:
            if branch['ref'] == branch_name:
                print(branch['revision'])
                retd['env'] = {'repo_ver': branch['revision']}

    return retd


def parse_comments(change_id, rest, zuul_url, zuul_ref):
    retd = {}
    r = re.compile(r'update_bb:(.*),(.*),(.*)')
    comment_list = rest.generic_get('/changes/{}/detail'.format(change_id))
    for msg in comment_list['messages']:
        for line in msg['message'].split('\n'):
            m = r.match(line)
            if m:
                print(line)
                m1 = m.group(1).strip('"').strip()
                m2 = m.group(2).strip('"').strip()
                m3 = m.group(3).strip('"').strip()
                if m2 == '-':
                    m2 = None
                if m3 == '-':
                    m3 = None
                if m3 == '~':
                    m2 = '{}/{}'.format(zuul_url, m2)
                    m3 = zuul_ref
                retd[m1] = {}
                if m2:
                    retd[m1]['repo_url'] = m2
                if m3:
                    retd[m1]['repo_ver'] = m3
    print(retd)
    return retd


def save_json_file(output_path, ric_dict, ric_commit_dict, env_dict,
                   comment_dict):
    retd = {}
    retd.update(ric_dict)
    retd.update(ric_commit_dict)
    retd.update(env_dict)
    retd.update(comment_dict)
    content = json.dumps(retd)
    print(content)
    api.file_api.save_file(content, output_path, False)


def _main(zuul_url, zuul_ref, output_path, change_id,
          rest_url, rest_user, rest_pwd, auth_type):
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

    ric_dict = parse_ric_list(description, zuul_url, zuul_ref)
    ric_commit_dict = parse_ric_commit_list(description)
    env_dict = get_env_commit(description, rest)
    comment_dict = parse_comments(change_id, rest, zuul_url, zuul_ref)
    save_json_file(output_path, ric_dict, ric_commit_dict, env_dict,
                   comment_dict)


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
