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
from random import randint
from slugify import slugify
from api import mysql_api
from mod import utils
from mod import integration_change
from mod import wft_tools
from mod import inherit_map
from mod import config_yaml
from mod import yocto_mapping

import api.file_api
import api.gerrit_api
import api.gerrit_rest
import update_depends
import api.http_api
import submodule_handle
import ruamel.yaml as yaml
import xml.etree.ElementTree as ET


wft = wft_tools.WFT
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
MAIL_REGEX = r'^[^@]+@(nokia|nokia-sbell|internal\.nsn|groups\.nokia)\.com'
PACKAGE_TAG_REGEX = r'[0-9]+.[0-9]+.[0-9]+'
KEY_LIST = ['REVISION', 'rev', 'SRCREV', 'SRC_REV', 'repo_ver']
SBTS_KNIFE_TEMPLATE = {
    "knife_request":
        {
            "baseline": "",
            "purpose": "debug",
            "rebuild_sc": [],
            "flags": [
                "bts"
            ],
            "reference_type": "",
            "changes": {},
            "force_knife_dir": "1",
            "knife_config": "",
            "knife_info": "",
            "module": "",
            "reference_ir": "",
            "server": "http://production.cb.scm.nsn-rdnet.net:80",
            "signed_software": True,
            "upload_location": [],
            "version_number": "99",
            "customer_knife_source": "",
            "knife_changes": {},
            "needed_results_mask": 2048
        },
    "access_key": wft_tools.WFT.key
}


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
    abandoned_changes = []
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
            change_content = rest.get_ticket(change_no, using_cache=True)
            if 'ABANDONED' in change_content['status']:
                print('***{} {} is ABANDONED, no need add to json***'.format(key, change_no))
                abandoned_changes.append(key)
                continue
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
                if project == 'MN/5G/COMMON/integration':
                    ret_dict['integration'] = {'repo_ver': rest.get_commit(change_no)['commit']}
                    continue
                if key == 'deployment':
                    change = rest.get_change(change_no, using_cache=True)
                    project_name = 'gitsm://gerrit.ext.net.nokia.com:29418/{}.git'.format(change['project'])
                    commit = rest.get_commit(change_no)['commit']
                    ret_dict[project_name] = {'REVISION': commit}
                    continue

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
    return ret_dict, external_dict, abandoned_changes


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


def get_available_base(change_id, rest, comp_config, with_sbts=False):
    stream_json = dict()
    inte_change = integration_change.ManageChange(rest, change_id)
    build_stream_list = inte_change.get_build_streams(with_sbts=with_sbts)
    print(build_stream_list)
    for build_stream in build_stream_list:
        for stream in comp_config['streams']:
            if build_stream == stream['value']:
                stream_json[build_stream] = ET.fromstring(
                    wft.get_build_list(stream['name'], baseline_type=0, items=1)
                ).findall('.//baseline')[0].text
                break
    print(stream_json)
    return stream_json


def get_bitbake_setting(build_content):
    bbrecipe = build_content.find('bbrecipe')
    if bbrecipe is not None:
        bbrecipe_location = bbrecipe.get("location", '')
        bbrecipe_commit = bbrecipe.get("commit", '')
        bbrecipe_type = bbrecipe.get("type", '')
    else:
        bbrecipe_location = ''
        bbrecipe_commit = ''
        bbrecipe_type = ''
    return bbrecipe_location, bbrecipe_commit, bbrecipe_type


def parse_inherit_subbuild(proj_component, version, inherit_map_obj):
    if not inherit_map_obj.is_in_inherit_map(proj_component):
        print("{} is not in inherit Map...".format(proj_component))
        return {}
    print("{} is in inherit Map...".format(proj_component))
    return inherit_map_obj.get_inherit_changes(proj_component, version, type_filter='in_build')


def get_env_change_dict(rest, change_id, config_yaml_file='config.yaml'):
    integration_obj = integration_change.IntegrationChange(rest, change_id)
    root_change = integration_obj.get_root_change()
    config_yaml_change = rest.get_file_change(config_yaml_file, root_change)
    if ('new' in config_yaml_change and config_yaml_change['new']) and \
            'old' in config_yaml_change and config_yaml_change['old']:
        print('Initial config_yaml_obj')
        config_yaml_obj = config_yaml.ConfigYaml(config_yaml_content=config_yaml_change['new'])
        print('Get change from config_yaml_obj')
        updated_dict, removed_dict = config_yaml_obj.get_changes(yaml.safe_load(config_yaml_change['old']))
        return updated_dict
    return {}


def add_inherit_into_json(ex_comment_dict, change_id, rest, base_list):
    if not base_list:
        return
    print('Get inherit change from {}'.format(base_list))
    inherit_map_obj = inherit_map.Inherit_Map(base_loads=base_list.values())
    env_change_dict = get_env_change_dict(rest, change_id)
    for stream in ex_comment_dict:
        all_change_dict = {}
        if stream in ex_comment_dict:
            all_change_dict = copy.deepcopy(ex_comment_dict[stream])
        all_change_dict.update(env_change_dict)
        print('Change dict for {} is {}'.format(stream, all_change_dict))
        if not all_change_dict:
            continue
        for section_key, section in all_change_dict.items():
            if 'version' in section:
                inherit_changes = parse_inherit_subbuild(
                    section_key,
                    section['version'],
                    inherit_map_obj
                )
                if inherit_changes:
                    if stream in ex_comment_dict and ex_comment_dict[stream]:
                        inherit_changes.update(ex_comment_dict[stream])
                    ex_comment_dict[stream] = inherit_changes
                    print("Add {} subbuild to ex_comment_dict['{}'] finish".format(section_key, stream))
                    print(inherit_changes)


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


def parse_comments_base(change_id, rest, using_cache=True):
    retd = {}
    r = re.compile(r'update_base:(.*),(.*)')
    de = 'use_default_base'
    comment_list = rest.generic_get('/changes/{}/detail'.format(change_id), using_cache=using_cache)
    for msg in comment_list['messages']:
        for line in msg['message'].split('\n'):
            m = r.match(line)
            if m:
                print(line)
                m1 = m.group(1).strip().strip('"')
                m2 = m.group(2).strip().strip('"')
                if re.match(PACKAGE_TAG_REGEX, m2) or m1.startswith('SBTS'):
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


def combine_knife_json(json_list, abandoned_changes):
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
            result[target]['sync_global_config_changes'] = 'true'

    for obj in json_list:
        for target in obj:
            comp_list = result[target].keys()
            for comp in comp_list:
                if comp in abandoned_changes:
                    result[target].pop(comp, None)
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
    values = {}
    repo_keys = ['repo_ver', 'protocol', 'repo_url']
    for k in data:
        if k in gnbList and 'repo_ver' in data.get(k):
            print('Include gnb component:***{}***,need update knife json'.format(k))
            # get gnb component's repo_ver/protocol/repo_url
            for repo_key in repo_keys:
                if repo_key in data.get(k):
                    values[repo_key] = data.get(k).get(repo_key)
            break
    if values:
        for i in gnbList:
            # add other gnb components
            if i in data:
                data[i].update(values)
            else:
                data[i] = values
        return True
    return False


def get_description(rest, change_id):
    retried = 0
    while True:
        if retried >= 6:
            raise Exception('Can not get {} data, please check if Gerrit issue or make sure triggerred knife from Skytrack !'.format(change_id))
        data = ''
        try:
            data = rest.get_ticket(change_id, using_cache=True)
        except Exception as e:
            print(str(e))
            time.sleep(10)

        if data and 'change_id' in data:
            rest_id = data['change_id']
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


def get_isar_version(comp, comp_dict):
    oam_dir = ''
    if comp == 'coam-parameters':
        oam_dir = 'COAM_ARTIFACTORY_DIRECTORY'
    elif comp == 'cuoam-parameters':
        oam_dir = 'CUOAM_ARTIFACTORY_DIRECTORY'
    else:
        raise Exception("[Error] The function does not support the input param!")
    ecl_link = ''
    if oam_dir in comp_dict and 'BIN_VER' in comp_dict:
        ecl_link = 'http://artifactory-espoo1.int.net.nokia.com/artifactory/mnp5g-oam-bin-rel-local/' \
                   + comp_dict[oam_dir] + '/' + comp_dict['BIN_VER'] + '/ecl.txt'
    else:
        print("[Error] Missing mandatory fields in OAM comments!")
        return None, None
    if ecl_link:
        ecl_file = os.path.join(os.getcwd(), 'ecl.txt')
        try:
            api.http_api.download(ecl_link, ecl_file)
        except Exception as e:
            print("An exception %s occurred, msg: %s" % (type(e), str(e)))
            traceback.print_exc()
            return None, None
        with open(ecl_file, 'r') as f:
            f_content = f.read()
    if f_content:
        isar_reg = re.compile(r'ECL_ISAR_XML=\/isource\/svnroot\/BTS_I_ISAR_XML\/(.*)@([\d]*)')
        content = "\n".join(f_content.splitlines())
        reg_search_result = isar_reg.search(content)
        isar_branch = reg_search_result.groups()[0] if reg_search_result else None
        isar_version = reg_search_result.groups()[1] if reg_search_result else 'HEAD'
        print("[Info] ISAR version get from ecl.txt is {0}@{1}".format(isar_branch, isar_version))
        return isar_branch, isar_version
    else:
        print("[Error] Failed to get isar from ecl.txt {}".format(ecl_link))
        return None, None


def add_isar(comment_dict):
    if not comment_dict or comment_dict == {}:
        print("[Info] Empty comment_dict, no need to parse!")
        return
    for key, value in comment_dict.items():
        for comp, comp_value in value.items():
            if comp == 'coam-parameters' or comp == 'cuoam-parameters':
                isar_branch, isar_version = get_isar_version(comp, comp_value)
                if isar_branch:
                    isar_dict = {"SVNBRANCH": isar_branch, "SVNREV": isar_version}
                    value['isarxml'] = isar_dict
                    break


def initial_sbts_knife_dict(sbts_base):
    sbts_knife_dict = copy.deepcopy(SBTS_KNIFE_TEMPLATE)
    sbts_knife_dict['knife_request']['baseline'] = sbts_base
    sbts_work_dir = os.path.join(os.getcwd(), 'sbts_integration')
    branch_config_file = os.path.join(sbts_work_dir, 'branch-config.json')
    if os.path.exists(sbts_work_dir):
        shutil.rmtree(sbts_work_dir)
    os.makedirs(sbts_work_dir)
    base_repo_info = wft_tools.get_repository_info(sbts_base)
    git_sbts = git.Git(sbts_work_dir)
    git_sbts.init()
    git_sbts.fetch(utils.INTEGRATION_URL, base_repo_info['branch'])
    git_sbts.checkout(base_repo_info['revision'], 'branch-config.json')
    with open(branch_config_file, 'r') as fr:
        branch_config_dict = json.load(fr)
        sbts_knife_dict['knife_request']['module'] = branch_config_dict['modules'][0]['LTE_MODULE']
        return sbts_knife_dict
    raise Exception('Cannot get module info for {}'.format(sbts_base))


def update_sbts_comp_change(sbts_knife_dict, comp_knife_dict):
    random_key = randint(0, 999999999999999)
    while random_key in sbts_knife_dict['knife_request']['knife_changes']:
        random_key = randint(0, 999999999999999)
    sbts_knife_dict['knife_request']['knife_changes'][random_key] = comp_knife_dict


def gen_sbts_knife_dict(knife_dict, stream_json):
    sbts_base = None
    base_stream_map = stream_json
    if 'SBTS' not in ','.join(stream_json.keys()):
        print('No SBTS branch for this topic')
        return {}
    for stream, stream_base in base_stream_map.items():
        if stream.startswith('SBTS'):
            sbts_base = stream_base
    if not sbts_base:
        print('No SBTS branch for this topic')
        return {}
    sbts_knife_dict = initial_sbts_knife_dict(sbts_base)
    print('sbts_knife_dict:')
    print(sbts_knife_dict)
    # get bb_mapping for SBTS load
    sbts_bb_mapping = yocto_mapping.Yocto_Mapping(sbts_base)
    for target_dict in knife_dict.values():
        for component_name, replace_dict in target_dict.items():
            recipe_dict = sbts_bb_mapping.get_component_dict(component_name)[0]
            comp_knife_dict = {}
            if recipe_dict and 'src_uri' in recipe_dict and replace_dict['src_uri']:
                comp_knife_dict[recipe_dict['src_uri']] = replace_dict
                comp_knife_dict['source_repo'] = recipe_dict['src_uri']
                comp_knife_dict['source_type'] = recipe_dict['src_uri_type']
                if 'repo_url' in replace_dict and replace_dict['repo_url']:
                    comp_knife_dict['replace_source'] = replace_dict['repo_url']
                else:
                    comp_knife_dict['replace_source'] = replace_dict['repo_url']
                replace_commit = get_revision_from_dict(replace_dict)
                if replace_commit:
                    comp_knife_dict['replace_commit'] = replace_commit
                if 'package_path' in replace_dict and replace_dict['package_path']:
                    comp_knife_dict['package_path'] = replace_dict['package_path']
            if comp_knife_dict:
                update_sbts_comp_change(sbts_knife_dict, comp_knife_dict)
    return sbts_knife_dict


def get_revision_from_dict(replace_dict):
    for key in KEY_LIST:
        if key in replace_dict:
            return replace_dict[key]
    print('Cannot found revision from {}'.format(replace_dict))
    return None


def run(zuul_url, zuul_ref, output_path, change_id,
        gerrit_info_path, zuul_changes, gnb_list_path, db_info_path, comp_config):
    rest = api.gerrit_rest.init_from_yaml(gerrit_info_path)
    rest.init_cache(1000)
    comp_config = yaml.load(open(comp_config), Loader=yaml.Loader, version='1.1')
    project_branch = parse_zuul_changes(zuul_changes)

    # path
    knife_path = os.path.join(output_path, 'knife.json')
    sbts_knife_path = os.path.join(output_path, 'sbts_knife.json')
    base_path = os.path.join(output_path, 'base.json')
    reviews_path = os.path.join(output_path, 'reviewers.json')

    # config
    knife_config = parse_config(rest, change_id)

    description, rest_id = get_description(rest, change_id)

    # knife json
    ric_dict, ex_dict, abandoned_changes = parse_ric_list(
        rest, description, zuul_url, zuul_ref, project_branch,
        knife_config)
    ric_commit_dict = parse_ric_commit_list(description)
    env_dict = get_env_commit(description, rest)
    ex_comment_dict, comp_f_prop = parse_ex_comments(ex_dict, rest,
                                                     comp_f_prop=[], zuul_url=zuul_url, zuul_ref=zuul_ref)
    comment_dict = parse_comments(change_id, rest, comp_f_prop=comp_f_prop,
                                  zuul_url=zuul_url, zuul_ref=zuul_ref)

    # interfaces
    find_interfaces, interfaces_infos = update_depends.search_interfaces(rest, change_id)
    interfaces_dict = {}
    for interfaces_info in interfaces_infos:
        interfaces_dict[interfaces_info['component']] = {'bb_ver': interfaces_info['comp_version']}
    for ex_dict_value in ex_comment_dict.values():
        ex_dict_value.update(interfaces_dict)
    for comment_value in comment_dict.values():
        comment_value.update(interfaces_dict)

    # add isar_xml in knife json
    inte_change = integration_change.IntegrationChange(rest, change_id)
    feature_id = inte_change.get_feature_id()
    if feature_id and 'NIDD' in feature_id:
        add_isar(ex_comment_dict)
        add_isar(comment_dict)

    stream_json = parse_comments_base(change_id, rest)
    inherit_base_dict = get_available_base(change_id, rest, comp_config)
    add_inherit_into_json(ex_comment_dict, change_id, rest, inherit_base_dict)

    combined_knife_dict = combine_knife_json([
        {'all': ric_dict},
        {'all': ric_commit_dict},
        {'all': env_dict},
        {'all': interfaces_dict},
        ex_comment_dict,
        comment_dict], abandoned_changes)
    save_json_file(knife_path,
                   [combined_knife_dict],
                   override=True)

    # stream base json
    save_json_file(base_path, stream_json)

    # sbts knife json
    save_json_file(sbts_knife_path,
                   [gen_sbts_knife_dict(combined_knife_dict, stream_json)],
                   override=True)
    # email list
    reviews_json = rest.get_reviewer(change_id)
    reviews_mail_list = [x['email'] for x in reviews_json if 'email' in x]
    mail_list = parse_comments_mail(change_id, rest)
    mail_list.extend(reviews_mail_list)
    save_json_file(reviews_path, list(set(mail_list)))

    # add all gnb components
    if gnb_list_path:
        rewrite_knife_json(knife_path, gnb_list_path)

    if db_info_path:
        print('........')
# zuul has changed the zuul database server. and confirmed with Alex this store is not needed anymore
    # store zuul_ref in zuul database
    # if zuul_ref:
    #    save_data_in_zuul_db(knife_path, db_info_path)


if __name__ == '__main__':
    try:
        fire.Fire(run)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
