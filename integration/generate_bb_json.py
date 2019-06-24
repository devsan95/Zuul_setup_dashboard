#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import copy
import json
import os
import re
import sys
import time
import shutil
import traceback
import datetime

import git
import fire
import urllib3
from slugify import slugify
from api import mysql_api

import api.file_api
import api.gerrit_api
import api.gerrit_rest
import submodule_handle

import ruamel.yaml as yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
MAIL_REGEX = r'^[^@]+@(nokia|nokia-sbell|internal\.nsn|groups\.nokia)\.com'


def strip_begin(text, prefix):
    if not text.startswith(prefix):
        return text
    return text[len(prefix):]


def is_adapted(rest, change_no):
    fl = rest.get_file_list(change_no, using_cache=True)
    for fn in fl:
        fn = fn.split('\n', 2)[0]
        if fn == '/COMMIT_MSG':
            continue
        elif fn.endswith('.inte_tmp'):
            continue
        return True
    return False


def parse_config(rest, change_no):
    retd = {'linked-projects': set()}
    comment_list = rest.generic_get(
        '/changes/{}/detail'.format(change_no), using_cache=True)
    for msg in comment_list['messages']:
        msg_str = msg['message']
        if 'update_knife_json_config:' in msg_str:
            update_yaml = msg_str[msg_str.find('update_knife_json_config:'):]
            try:
                parse_config_yaml(update_yaml, retd)
            except Exception as e:
                print(e)
                traceback.print_exc()
                continue
    print('[Info] Config parse result:')
    print(retd)
    return retd


def parse_ric_list(rest, subject, zuul_url,
                   zuul_ref, project_branch, config):
    print("---------------------------parsing integration"
          " change to get the ric list-------------------------------")
    ret_dict = {}
    external_dict = {}
    link_result = {}
    lines = subject.split('\n')
    ric = []
    r = re.compile(r'  - RIC <([^<>]*)> <([^<>]*)>( <(\d*)>)?( <t:([^<>]*)>)?')
    for line in lines:
        m = r.match(line)
        if m:
            key = m.group(1).strip('"').strip()
            value = m.group(2).strip('"').strip()
            change_no = m.group(4)
            need_change = True
            type_ = m.group(6)
            change = rest.get_change(change_no, using_cache=True)
            project = change['project']
            ric.append([key, value, change_no,
                        need_change, type_, change, project])
            # project is linked
            if project in config['linked-projects']:
                if project not in link_result:
                    link_result[project] = is_adapted(rest, change_no)
                else:
                    link_result[project] = (link_result[project] or is_adapted(rest, change_no))
    for item in ric:
        key, value, change_no, need_change, type_, change, project = item
        if type_ != 'integration':
            print('[Info] for ric key {}, change number is {},'
                  ' type is {}'.format(key, change_no, type_))
            if change_no:
                if change_no in external_dict:
                    external_dict[change_no].append(key)
                else:
                    external_dict[change_no] = [key]
        if type_ != 'external':
            if change_no:
                need_change = is_adapted(rest, change_no)
                if need_change:
                    print('[Info] For ric key {},'
                          ' change {} has adaptation'.format(key, change_no))
                if link_result.get(project):
                    print(
                        '[Info] one component in project {} has adaptation, \
                        so the other related components '
                        'will be added in knife json'.format(project))
                    need_change = True
            if need_change:
                ret_dict[key] = {'repo_url': '{}/{}'.format(zuul_url, value),
                                 'repo_ver': zuul_ref}
                if change_no:
                    if project in project_branch:
                        branch = project_branch[project]
                        ret_dict[key]['repo_ver'] = \
                            form_zuul_ref(zuul_ref, branch)
                    else:
                        print('[Warning] project {} not in zuul_changes'.format(project))
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
        branches = rest.list_branches('MN/5G/COMMON/env', using_cache=True)
        for branch in branches:
            branch['ref'] = strip_begin(branch['ref'], 'refs/heads/')

        for branch in branches:
            if branch['ref'] == branch_name:
                print(branch['revision'])
                retd['env'] = {'repo_ver': branch['revision']}

    return retd


def parse_commitmsg_and_comments(comment_list, retd, rest, change_id, comp_list=None,
                                 comp_f_prop=None, zuul_url='', zuul_ref=''):
    for msg in comment_list['messages']:
        msg_str = msg['message']
        if 'update_knife_json:' in msg_str:
            update_yaml = msg_str[msg_str.find('update_knife_json:'):]
            try:
                comp_f_prop = parse_comp_from_prop(update_yaml, retd, rest,
                                                   change_id,
                                                   comp_f_prop=comp_f_prop,
                                                   zuul_url=zuul_url,
                                                   zuul_ref=zuul_ref)
            except Exception as e:
                print(e)
                traceback.print_exc()
                continue

    print('comp_f_property: {}'.format(comp_f_prop))
    for msg in comment_list['messages']:
        if 'update_knife_json:' in msg_str:
            update_yaml = msg_str[msg_str.find('update_knife_json:'):]
            try:
                parse_update_yaml(update_yaml, retd, component_list=comp_list)
            except Exception as e:
                print(e)
                traceback.print_exc()
                continue
        for line in msg['message'].split('\n'):
            parse_update_bb(
                line, retd, comp_f_prop=comp_f_prop, component_list=comp_list)
            parse_update_comp(
                line, retd, comp_f_prop=comp_f_prop, component_list=comp_list)
    return comp_f_prop


def parse_comments(change_id, rest, comp_f_prop=None, zuul_url='', zuul_ref=''):
    print('parsing comments!')
    retd = {}
    comment_list = rest.generic_get('/changes/{}/detail'.format(change_id), using_cache=True)
    parse_commitmsg_and_comments(comment_list, retd, rest, change_id, comp_f_prop=comp_f_prop,
                                 zuul_url=zuul_url, zuul_ref=zuul_ref)

    print('Comments of integration parse result:')
    print(retd)
    return retd


def parse_ex_comments(ex_dict, rest, comp_f_prop=None, zuul_url='', zuul_ref=''):
    print('parsing ex comments!')
    print('ex dict is:')
    print(ex_dict)
    retd = {}
    for change_id, comp_list in ex_dict.items():
        comment_list = rest.generic_get('/changes/{}/detail'.format(change_id), using_cache=True)
        comp_f_prop = parse_commitmsg_and_comments(comment_list, retd, rest, change_id,
                                                   comp_f_prop=comp_f_prop, zuul_url=zuul_url,
                                                   zuul_ref=zuul_ref, comp_list=comp_list)

    print('Other change parse result:')
    print(retd)
    return retd, comp_f_prop


def parse_config_yaml(yaml_str, result):
    yaml_obj = yaml.load(yaml_str, Loader=yaml.Loader)
    action_list = yaml_obj['update_knife_json_config']
    for action in action_list:
        atype = action['type']
        if atype == 'add-linked-projects':
            projects = action['projects']
            if 'linked-projects' not in result:
                result['linked-projects'] = set()
            for project in projects:
                result['linked-projects'].add(project)
        elif atype == 'remove-linked-projects':
            projects = action['projects']
            if 'linked-projects' not in result:
                result['linked-projects'] = set()
            for project in projects:
                if project in result['linked-projects']:
                    result['linked-projects'].remove(project)
        else:
            raise Exception('Unsupported type {}'.format(atype))


def parse_comp_from_prop(yaml_str, result,
                         rest=None, change_no=None, comp_f_prop=None,
                         zuul_url='', zuul_ref=''):
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
        if atype == 'component-from-property':
            if not rest or not change_no:
                raise Exception('No gerrit rest or change no')
            prop_change = rest.get_change(change_no, using_cache=True)
            prop_project = prop_change['project']
            file_content = get_ref_file_content(
                action['file_name'], zuul_url, prop_project, zuul_ref)
            key_value = {}
            for line in file_content.split('\n'):
                m = re.match(r'\s*#', line)
                if m:
                    continue
                line_snip = line.split('=', 2)
                if len(line_snip) > 1:
                    key_value[line_snip[0].strip()] = line_snip[1].strip()
            for key, param in action['keys'].items():
                if key in key_value:
                    value = key_value[key]
                    component = param['target_name']
                    if not comp_f_prop:
                        comp_f_prop = []
                    comp_f_prop.append(component)
                    # if component not in component_list:
                    #     print('[{}] not in comp list'.format(component))
                    #     continue
                    cparam = {}
                    for k, v in param['target_params'].items():
                        cparam[k] = v.format(key=key, value=value)
                    for stream in streams:
                        result[stream][component] = cparam
    return comp_f_prop


def parse_update_yaml(yaml_str, result, component_list=None):
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
                    if component_list:
                        if component not in component_list:
                            print('[{}] not in comp list'.format(component))
                            continue
                    result[stream][component] = param
        elif atype == 'remove-component':
            for stream in streams:
                for component in action['components']:
                    if component_list:
                        if component not in component_list:
                            print('[{}] not in comp list'.format(component))
                            continue
                    rp = result[stream]
                    rp.pop(component, None)
                    print('delete [{}] from [{}]'.format(
                        component, stream))
        elif atype == 'component-from-property':
            print('Coninue because this should be dealed before')
            continue
        else:
            raise Exception('Unsupported type {}'.format(atype))


def get_ref_file_content(file_name, zuul_url, project, zuul_ref):
    proj_wk = os.path.join(os.getcwd(), 'zuul_repos', project)
    repo_url = os.path.join(zuul_url, project)
    if os.path.exists(proj_wk):
        shutil.rmtree(proj_wk)
    os.makedirs(proj_wk)
    g = git.Git(proj_wk)
    g.init()
    print('Get zuul repo {}:{}'.format(repo_url, zuul_ref))
    g.fetch(repo_url, zuul_ref)
    g.checkout('FETCH_HEAD')
    with open(os.path.join(proj_wk, file_name), 'r') as fr:
        return fr.read()


def parse_update_comp(line, result, comp_f_prop=None, component_list=None):
    line_ = line.split('update_component:')
    if len(line_) > 1:
        values = line_[1]
        value_list = values.split(',')
        value_list = [x.strip().strip('"') for x in value_list]
        print(line)
        value_len = len(value_list)
        if value_len < 3:
            print('parameters of update_component is not enough.')
            return
        m = value_list
        component = m[0]
        key = m[1]
        value = m[2]
        if comp_f_prop and component in comp_f_prop:
            print('{} verison should get from env, do not need to update here'.format(component))
            return
        if value_len >= 4:
            targets = [x.strip().strip('"') for x in m[3].split(';')]
        else:
            targets = ['all']
        if component_list:
            if component not in component_list:
                print('[{}] not in comp list'.format(line))
                return
        for target in targets:
            if target not in result:
                result[target] = {}
                result[target][component] = {}
            else:
                if component not in result[target]:
                    result[target][component] = {}
            rp = result[target][component]
            if key == '~':
                result[target].pop(component, None)
                print('[{}] delete [{}] from [{}]'.format(
                    line, component, target))
                return
            elif value == '~':
                rp.pop(key, None)
                print('[{}] delete [{}] from [{}] in [{}]'.format(
                    line, key, component, target))
                return
            if key and value:
                rp[key] = value
            else:
                print('key: [{}], value: [{}] not in comp list'.format(
                    key, value))


def parse_update_bb(line, result, comp_f_prop=None, component_list=None):
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
        if comp_f_prop and component in comp_f_prop:
            print('{} verison should get from env, do not need to update here'.format(component))
            return
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


def parse_comments_mail(change_id, rest, using_cache=True):
    mail_key = 'knife recipients:'
    comment_list = rest.generic_get('/changes/{}/detail'.format(change_id), using_cache=using_cache)
    mail_list = []
    for msg in comment_list['messages']:
        is_mail_list = False
        for line in msg['message'].split('\n'):
            if mail_key in line:
                is_mail_list = True
                continue
            if is_mail_list:
                m = re.match(MAIL_REGEX, line.strip())
                if m:
                    print(line)
                    mail_list.append(line.strip())
    print('Comments of mail parse result:')
    print(mail_list)
    return mail_list


def parse_comments_base(change_id, rest):
    retd = {}
    r = re.compile(r'update_base:(.*),(.*)')
    de = 'use_default_base'
    comment_list = rest.generic_get('/changes/{}/detail'.format(change_id), using_cache=True)
    for msg in comment_list['messages']:
        for line in msg['message'].split('\n'):
            m = r.match(line)
            if m:
                print(line)
                m1 = m.group(1).strip().strip('"')
                m2 = m.group(2).strip().strip('"')
                retd[m1] = m2
            if de in line:
                print(line)
                retd = {}
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
            print('[warning] zuul_changes {} cant be parsed, since it is empty'.format(p))
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


def rewrite_knife_json(knife_json_path, gnblist_path):
    # input knife.json and gnb_list files
    with open(gnblist_path, 'r') as f:
        gnbList = f.read().splitlines()

    with open(knife_json_path, 'a+') as f:
        data = json.load(f)
        flag = False
        # if knife.json include any gnb component,flag = True
        for key, stream_data in data.items():
            if add_comps_to_knife_json(stream_data, gnbList):
                flag = True
        if flag:
            content = json.dumps(data, indent=2)
            api.file_api.save_file(content, knife_json_path, False)
            print('Updated gnb components!!')
        else:
            print('No need update knife json!')


def add_comps_to_knife_json(data, gnbList):
    flag = False
    for k in data:
        if k in gnbList:
            flag = True
            print('Include gnb component:***{}***,need update knife json'.format(k))
            # get gnb component's repo_ver/protocol/repo_url
            values = data.get(k)
            break
    if flag:
        for i in gnbList:
            # add other gnb components
            data[i] = values
        return True
    return False


def get_description(rest, change_id):
    retried = 0
    while True:
        if retried >= 6:
            raise Exception('Can not get {} data'.format(change_id))
        data = ''
        try:
            data = rest.get_ticket(change_id, using_cache=True)
        except Exception as e:
            print(str(e))
            time.sleep(10)

        if data and 'id' in data:
            rest_id = data['id']
            retried = 0
            break
        retried += 1

    while True:
        if retried >= 6:
            raise Exception('Can not get {} commit data'.format(rest_id))
        commit_data = ''
        try:
            commit_data = rest.get_commit(rest_id, using_cache=True)
        except Exception as e:
            print(str(e))
            time.sleep(10)

        if commit_data and 'message' in commit_data:
            description = commit_data['message']
            break
        retried += 1
    return description, rest_id


def save_data(knife_path, zuul_db):
    values = {}
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    r = re.compile(r'gitsm://(.*/p)/(.*)')

    with open(knife_path, 'r') as f:
        json_obj = json.load(f)
        for key in json_obj.keys():
            for comp in json_obj[key].keys():
                if "repo_ver" in json_obj[key][comp].keys()\
                        and "refs/zuul" in json_obj[key][comp]["repo_ver"]:
                    values["zuul_ref"] = json_obj[key][comp]["repo_ver"]
                    values["date"] = date
                    m = r.match(json_obj[key][comp]["repo_url"])
                    if m:
                        values["zuul_url"] = m.group(1).strip()
                        values["project"] = m.group(2).strip()
                    if not zuul_db.executor(
                        sql='SELECT * FROM t_integration_refs WHERE zuul_ref = "{}" '
                            'AND zuul_url = "{}" AND project = "{}"'
                            .format(values["zuul_ref"], values["zuul_url"], values["project"]),
                            output=True
                    ):
                        zuul_db.insert_info('t_integration_refs', values)


def save_data_in_zuul_db(knife_path, db_info_path):
    server_name = "zuul"
    database_name = "stored_refs"
    zuul_db = mysql_api.init_from_yaml(db_info_path, server_name=server_name)
    zuul_db.init_database(database_name)
    save_data(knife_path, zuul_db)


def run(zuul_url, zuul_ref, output_path, change_id,
        gerrit_info_path, zuul_changes, gnb_list_path, db_info_path):
    rest = api.gerrit_rest.init_from_yaml(gerrit_info_path)
    rest.init_cache(1000)
    project_branch = parse_zuul_changes(zuul_changes)

    # path
    knife_path = os.path.join(output_path, 'knife.json')
    base_path = os.path.join(output_path, 'base.json')
    reviews_path = os.path.join(output_path, 'reviewers.json')

    # config
    knife_config = parse_config(rest, change_id)

    description, rest_id = get_description(rest, change_id)

    # knife json
    ric_dict, ex_dict = parse_ric_list(
        rest, description, zuul_url, zuul_ref, project_branch,
        knife_config)
    ric_commit_dict = parse_ric_commit_list(description)
    env_dict = get_env_commit(description, rest)
    ex_comment_dict, comp_f_prop = parse_ex_comments(ex_dict, rest,
                                                     comp_f_prop=[], zuul_url=zuul_url, zuul_ref=zuul_ref)
    comment_dict = parse_comments(change_id, rest, comp_f_prop=comp_f_prop,
                                  zuul_url=zuul_url, zuul_ref=zuul_ref)
    save_json_file(knife_path,
                   [combine_knife_json([
                       {'all': ric_dict},
                       {'all': ric_commit_dict},
                       {'all': env_dict},
                       ex_comment_dict,
                       comment_dict
                   ])],
                   override=True)

    # stream base json
    stream_json = parse_comments_base(change_id, rest)
    save_json_file(base_path, stream_json)

    # email list
    reviews_json = rest.get_reviewer(change_id)
    reviews_mail_list = [x['email'] for x in reviews_json if 'email' in x]
    mail_list = parse_comments_mail(change_id, rest)
    mail_list.extend(reviews_mail_list)
    save_json_file(reviews_path, list(set(mail_list)))

    # add all gnb components
    rewrite_knife_json(knife_path, gnb_list_path)

    # store zuul_ref in zuul database
    if zuul_ref:
        save_data_in_zuul_db(knife_path, db_info_path)


if __name__ == '__main__':
    try:
        fire.Fire(run)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
