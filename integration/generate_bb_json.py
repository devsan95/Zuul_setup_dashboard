#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import copy
import json
import os
import re
import sys
import time
import traceback

import fire
import urllib3
from slugify import slugify

import api.file_api
import api.gerrit_api
import api.gerrit_rest
import submodule_handle

import ruamel.yaml as yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
            if type_ != 'integration':
                print('{} is {}'.format(change_no, type_))
                if change_no:
                    if change_no in external_dict:
                        external_dict[change_no].append(key)
                    else:
                        external_dict[change_no] = [key]
            if type_ != 'external':
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
    comment_list = rest.generic_get('/changes/{}/detail'.format(change_id))
    for msg in comment_list['messages']:
        msg_str = msg['message']
        if 'update_knife_json:' in msg_str:
            update_yaml = msg_str[msg_str.find('update_knife_json:'):]
            try:
                parse_update_yaml(update_yaml, retd, rest, change_id)
            except Exception as e:
                print(e)
                traceback.print_exc()
                continue
        else:
            for line in msg['message'].split('\n'):
                parse_update_bb(line, retd)
    print('Comments of integration parse result:')
    print(retd)
    return retd


def parse_ex_comments(ex_dict, rest):
    print('ex dict is:')
    print(ex_dict)
    retd = {}
    for change_id, comp_list in ex_dict.items():
        comment_list = rest.generic_get('/changes/{}/detail'.format(change_id))
        for msg in comment_list['messages']:
            msg_str = msg['message']
            if 'update_knife_json:' in msg_str:
                update_yaml = msg_str[msg_str.find('update_knife_json:'):]
                try:
                    parse_update_yaml(update_yaml, retd, rest, change_id, comp_list)
                except Exception as e:
                    print(e)
                    traceback.print_exc()
                    continue
            else:
                for line in msg['message'].split('\n'):
                    parse_update_bb(line, retd, comp_list)

    print('Other change parse result:')
    print(retd)
    return retd


def parse_update_yaml(yaml_str, result, rest=None, change_no=None, component_list=None):
    yaml_obj = yaml.load(yaml_str, Loader=yaml.Loader)
    action_list = yaml_obj['update_knife_json']
    for action in action_list:
        atype = action['type']
        streams = action.get('streams')
        if not streams:
            streams = ['all']
        for stream in streams:
            if stream not in result:
                result[stream] = {}
        if atype == 'update-component':
            for stream in streams:
                components = action['components']
                for component, param in components.items():
                    result[stream][component] = param
        elif atype == 'remove-component':
            for stream in streams:
                for component in action['components']:
                    rp = result[stream][component]
                    rp.pop(component, None)
                    print('delete [{}] from [{}]'.format(
                        component, stream))
        elif atype == 'component-from-property':
            if not rest or not change_no:
                raise Exception('No gerrit rest or change no')
            diff = rest.get_file_change(action['file_name'], change_no).get('new_diff')
            key_value = {}
            for line in diff.split('\n'):
                line_snip = line.split('=', 2)
                if len(line_snip) > 1:
                    key_value[line_snip[0].strip()] = line_snip[1].strip()
            for key, param in action['keys'].items():
                if key in key_value:
                    value = key_value[key]
                    component = param['target_name']
                    cparam = {}
                    for k, v in param['target_params'].items():
                        cparam[k] = v.format(key=key, value=value)
                    for stream in streams:
                        result[stream][component] = cparam
        else:
            raise Exception('Unsupported type {}'.format(atype))


def parse_update_bb(line, result, component_list=None):
    line_ = line.split('update_bb:')
    if len(line_) > 1:
        values = line_[1]
        value_list = values.split(',')
        value_list = [x.strip().strip('"') for x in value_list]
        print(line)
        value_len = len(value_list)
        if value_len < 3:
            print('parameters of update_bb is not enough.')
            return
        m = value_list
        component = m[0]
        url = m[1]
        commit = m[2]
        if value_len >= 4:
            targets = [x.strip().strip('"') for x in m[3].split(';')]
        else:
            targets = ['all']
        if component_list:
            if component not in component_list:
                print('[{}] not in comp list'.format(line))
                return
        if url == '-':
            url = None
        if commit == '-':
            commit = None
        for target in targets:
            if target not in result:
                result[target] = {}
            result[target][component] = {}
            rp = result[target][component]
            if commit == '~':
                rp.pop(component, None)
                print('[{}] delete [{}] from [{}]'.format(
                    line, component, target))
                return
            if url == 'bb':
                rp['bb_ver'] = commit
            else:
                if url:
                    rp['repo_url'] = url
                    if rp['repo_url'].startswith('http:'):
                        rp['repo_url'] = \
                            rp['repo_url'].replace('http:', 'gitsm:')
                        rp['protocol'] = 'http'
                if commit:
                    rp['repo_ver'] = commit


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
    print('Comments of base parse result:')
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
    content = json.dumps(retd, indent=2)
    print('Saved json is:')
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


def combine_knife_json(json_list):
    result = {'all': {}}
    for obj in json_list:
        if 'all' in obj:
            result['all'].update(obj['all'])
    for obj in json_list:
        for target in obj:
            if target != 'all':
                if target not in result:
                    result[target] = copy.deepcopy(result['all'])
                result[target].update(obj[target])
    return result


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
                   [combine_knife_json([
                       {'all': ric_dict},
                       {'all': ric_commit_dict},
                       {'all': env_dict},
                       comment_dict,
                       ex_comment_dict
                   ])],
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
