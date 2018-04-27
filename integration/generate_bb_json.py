#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import json
import os
import re
import sys
import time
import traceback

import fire
from slugify import slugify

import api.file_api
import api.gerrit_api
import api.gerrit_rest
import submodule_handle


def strip_begin(text, prefix):
    if not text.startswith(prefix):
        return text
    return text[len(prefix):]


def is_adpated(rest, change_no):
    fl = rest.get_file_list(change_no)
    for fn in fl:
        fn = fn.split('\n', 2)[0]
        if fn == '/COMMIT_MSG':
            continue
        elif fn.endswith('.inte_tmp'):
            continue
        return True
    return False


def parse_ric_list(rest, subject, zuul_url, zuul_ref):
    ret_dict = {}
    lines = subject.split('\n')
    r = re.compile(r'  - RIC <([^<>]*)> <([^<>]*)>( <(\d*)>)?')
    for line in lines:
        m = r.match(line)
        if m:
            key = m.group(1).strip('"').strip()
            value = m.group(2).strip('"').strip()
            change_no = m.group(4)
            need_change = True
            if change_no:
                need_change = is_adpated(rest, change_no)
                print('Change {} is Adapted: {}'.format(change_no, need_change))
            if need_change:
                ret_dict[key] = {'repo_url': '{}/{}'.format(zuul_url, value),
                                 'repo_ver': zuul_ref}
                if ret_dict[key]['repo_url'].startswith('http:'):
                    ret_dict[key]['repo_url'] = \
                        ret_dict[key]['repo_url'].replace('http:', 'gitsm:')
                    ret_dict[key]['protocol'] = 'http'
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
                m1 = m.group(1).strip().strip('"')
                m2 = m.group(2).strip().strip('"')
                m3 = m.group(3).strip().strip('"')
                if m2 == '-':
                    m2 = None
                if m3 == '-':
                    m3 = None
                if m3 == '~':
                    m2 = '{}/{}'.format(zuul_url, m2)
                    m3 = zuul_ref
                retd[m1] = {}
                if m2 == 'bb':
                    retd[m1]['bb_ver'] = m3
                else:
                    if m2:
                        retd[m1]['repo_url'] = m2
                        if retd[m1]['repo_url'].startswith('http:'):
                            retd[m1]['repo_url'] = \
                                retd[m1]['repo_url'].replace('http:', 'gitsm:')
                            retd[m1]['protocol'] = 'http'
                    if m3:
                        retd[m1]['repo_ver'] = m3

    print(retd)
    return retd


def parse_comments_base(change_id, rest):
    retd = {}
    r = re.compile(r'update_base:(.*),(.*)')
    comment_list = rest.generic_get('/changes/{}/detail'.format(change_id))
    for msg in comment_list['messages']:
        for line in msg['message'].split('\n'):
            m = r.match(line)
            if m:
                print(line)
                m1 = m.group(1).strip().strip('"')
                m2 = m.group(2).strip().strip('"')
                retd[m1] = m2
    print(retd)
    return retd


def save_json_file(output_path, dict_list, override=False):
    retd = {}
    if override:
        for dict_ in dict_list:
            if dict_:
                retd.update(dict_)
    else:
        retd = dict_list
    content = json.dumps(retd)
    print(content)
    api.file_api.save_file(content, output_path, False)


def run(zuul_url, zuul_ref, output_path, change_id, gerrit_info_path):
    rest = api.gerrit_rest.init_from_yaml(gerrit_info_path)

    rest_id = ''
    description = ''

    while True:
        try:
            data = rest.get_ticket(change_id)
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
    # path
    knife_path = os.path.join(output_path, 'knife.json')
    base_path = os.path.join(output_path, 'base.json')
    reviews_path = os.path.join(output_path, 'reviewers.json')

    # knife json
    ric_dict = parse_ric_list(rest, description, zuul_url, zuul_ref)
    ric_commit_dict = parse_ric_commit_list(description)
    env_dict = get_env_commit(description, rest)
    comment_dict = parse_comments(change_id, rest, zuul_url, zuul_ref)
    save_json_file(knife_path,
                   [ric_dict, ric_commit_dict, env_dict, comment_dict],
                   override=True)

    # stream base json
    stream_json = parse_comments_base(change_id, rest)
    save_json_file(base_path, stream_json)

    # email list
    reviews_json = rest.get_reviewer(change_id)
    save_json_file(reviews_path, reviews_json)


if __name__ == '__main__':
    try:
        fire.Fire(run)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
