#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

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


def parse_ric_list(rest, subject, zuul_url,
                   zuul_ref, project_branch):
    ret_dict = {}
    external_dict = {}
    lines = subject.split('\n')
    r = re.compile(r'  - RIC <([^<>]*)> <([^<>]*)>( <(\d*)>)?( <t:([^<>]*)>)?')
    for line in lines:
        m = r.match(line)
        if m:
            key = m.group(1).strip('"').strip()
            value = m.group(2).strip('"').strip()
            change_no = m.group(4)
            need_change = True
            type_ = m.group(6)
            if type_ == 'external':
                print('{} is external'.format(change_no))
                if change_no:
                    if change_no in external_dict:
                        external_dict[change_no].append(key)
                    else:
                        external_dict[change_no] = [key]
            else:
                if change_no:
                    need_change = is_adpated(rest, change_no)
                    print('Change {} is Adapted: {}'.format(change_no, need_change))
                if need_change:
                    ret_dict[key] = {'repo_url': '{}/{}'.format(zuul_url, value),
                                     'repo_ver': zuul_ref}
                    if change_no:
                        change = rest.get_change(change_no)
                        project = change['project']
                        if project in project_branch:
                            branch = project_branch[project]
                            ret_dict[key]['repo_ver'] = \
                                form_zuul_ref(zuul_ref, branch)
                        else:
                            print('project {} not in zuul_changes'.format(project))
                    if ret_dict[key]['repo_url'].startswith('http:'):
                        ret_dict[key]['repo_url'] = \
                            ret_dict[key]['repo_url'].replace('http:', 'gitsm:')
                        ret_dict[key]['protocol'] = 'http'
    return ret_dict, external_dict


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


def parse_comments(change_id, rest):
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
                    retd.pop(m1, None)
                    print('[{}] delete [{}]'.format(line, m1))
                    continue
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


def parse_ex_comments(ex_dict, rest):
    print('ex dict is:')
    print(ex_dict)
    retd = {}
    for change_id, comp_list in ex_dict.items():
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
                    if m1 not in comp_list:
                        print('[{}] not in comp list'.format(line))
                        continue
                    if m2 == '-':
                        m2 = None
                    if m3 == '-':
                        m3 = None
                    if m3 == '~':
                        retd.pop(m1, None)
                        print('[{}] delete [{}]'.format(line, m1))
                        continue
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


def parse_zuul_changes(zuul_changes):
    retd = {}
    plist = zuul_changes.split('^')
    for p in plist:
        blist = p.split(':')
        if len(blist) > 1:
            retd[blist[0]] = blist[1]
        else:
            print('{} cant be parsed'.format(p))
    return retd


def form_zuul_ref(zuul_ref, branch):
    rets = ''
    ref_list = zuul_ref.split('/')
    if len(ref_list) > 3:
        ref_hash = ref_list[-1]
        rets = 'refs/zuul/{}/{}'.format(branch, ref_hash)
    else:
        print('{} cant be parsed'.format(zuul_ref))
        return zuul_ref
    return rets


def run(zuul_url, zuul_ref, output_path, change_id,
        gerrit_info_path, zuul_changes):
    rest = api.gerrit_rest.init_from_yaml(gerrit_info_path)
    project_branch = parse_zuul_changes(zuul_changes)

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
    ric_dict, ex_dict = parse_ric_list(
        rest, description, zuul_url, zuul_ref, project_branch)
    ric_commit_dict = parse_ric_commit_list(description)
    env_dict = get_env_commit(description, rest)
    comment_dict = parse_comments(change_id, rest)
    ex_comment_dict = parse_ex_comments(ex_dict, rest)
    save_json_file(knife_path,
                   [ric_dict, ric_commit_dict,
                    env_dict, comment_dict, ex_comment_dict],
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
