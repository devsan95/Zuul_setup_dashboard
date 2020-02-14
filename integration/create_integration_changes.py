#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import copy
import json
import os
import re
import shlex
import sys
import time
import textwrap
import traceback
from datetime import datetime

import click
import networkx as nx
import ruamel.yaml as yaml
import urllib3
from slugify import slugify

import create_jira_ticket
import gerrit_int_op
import send_result_email
import skytrack_database_handler
from rebase_interface import update_interfaces_refs
from api import collection_api
from api import gerrit_api
from api import gerrit_rest
from api import job_tool
from api import config
from api import env_repo as get_env_repo
from mod import get_component_info
from mod import wft_tools
from mod import integration_change as inte_change

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

auto_branch_repos = ['MN/SCMTA/zuul/inte_mn', 'MN/SCMTA/zuul/inte_ric',
                     'MN/SCMTA/zuul/inte_root', 'MN/5G/COMMON/env',
                     'MN/5G/COMMON/integration']
env_repo = ['MN/5G/COMMON/env', 'MN/5G/COMMON/integration']

CONF = config.ConfigTool()
CONF.load('repo')


def load_structure(path):
    structure_obj = yaml.load(open(path),
                              Loader=yaml.Loader, version='1.1')
    return structure_obj


def create_graph(structure_obj):
    root_node = None
    nodes = {}
    integration_node = None
    integration_all_node = None

    # get all nodes from structure
    for node in structure_obj['structure']:
        if node['name'] in nodes:
            raise Exception(
                'There is already a node called "{}"'.format(node['name']))
        nodes[node['name']] = node
        if 'type' not in node:
            pass
        elif node['type'] == 'root':
            root_node = node
        elif node['type'] == 'integration':
            integration_node = node
        elif node['type'] == 'integration_all':
            integration_all_node = node

    # create a directed graph
    node_list = nodes.values()
    node_name_list = [x['name'] for x in node_list]
    graph_obj = nx.DiGraph()

    # add all nodes to the graph
    graph_obj.add_nodes_from(node_name_list)

    # add all dependency to the graph
    for node in node_list:
        if 'depends' in node:
            for depend_name in node['depends']:
                if depend_name not in node_name_list:
                    raise Exception(
                        'depend {} of {} does not exist'.format(
                            depend_name, node['name']))
                graph_obj.add_edge(depend_name, node['name'])

    # make integration_all_node depends on all other nodes
    if integration_all_node:
        for node in node_list:
            if node is not integration_node and node is not integration_all_node:
                graph_obj.add_edge(node['name'], integration_all_node['name'])

    # make manager node depends on all other nodes
    for node in node_list:
        if node is not integration_node:
            if 'attached' in node and not node['attached']:
                continue
            graph_obj.add_edge(node['name'], integration_node['name'])
    return root_node, integration_node, nodes, graph_obj


def check_graph_availability(graph_obj, root_node, integration_node):
    return check_necessary_nodes(root_node, integration_node, graph_obj) and\
        check_graph_root(root_node, graph_obj) and \
        check_graph_connectivity(root_node, graph_obj) and \
        check_graph_cycling(graph_obj)


def check_necessary_nodes(root_node, integration_node, graph_obj):
    if not root_node:
        raise Exception('There are not root project in the structure.')
    if not integration_node:
        raise Exception('There are not integration project in the structure.')
    if len(graph_obj.nodes()) < 3:
        raise Exception('There are no enough project in the structure.')
    return True


def check_graph_root(root_node, graph_obj):
    if graph_obj.in_edges(root_node['name']):
        raise Exception('There are dependencies in root project!')
    return True


def check_graph_connectivity(root_node, graph_obj):
    for node in graph_obj.nodes():
        if node != root_node['name']:
            c = nx.algorithms.node_connectivity(graph_obj,
                                                root_node['name'], node)
            if c == 0:
                raise Exception("Project {} can't connect to root project "
                                "by dependency".format(node['name']))
    return True


def check_graph_cycling(graph_obj):
    cycles = nx.algorithms.simple_cycles(graph_obj)
    cycle_num = 0
    for cycle in cycles:
        cycle_num += 1
        print('There is a cycle made by: {}'.format(cycle))
    if cycle_num > 0:
        raise Exception('There are cycles in the structure')
    return True


class IntegrationChangesCreation(object):
    def __init__(self, yaml_path, gerrit_path, zuul_user, zuul_key):
        self.change_info = None
        self.base_load_list = list()
        self.info_index = None
        self.meta = None
        self.structure = None

        self.gerrit_obj = None
        self.gerrit_server = None
        self.gerrit_user = None
        self.gerrit_pwd = None
        self.gerrit_ssh_server = None
        self.gerrit_ssh_port = None
        self.gerrit_ssh_user = None
        self.gerrit_ssh_key = None
        self.gerrit_rest = None
        self.comp_config = None

        self.load_yaml(yaml_path)
        self.load_gerrit(gerrit_path, zuul_user, zuul_key)
        self.auto_branch_status = {}
        self.base_commits_info = {}

    def load_yaml(self, yaml_path):
        self.change_info = load_structure(yaml_path)
        self.info_index = copy.deepcopy(self.change_info)
        self.meta = self.info_index['meta']
        self.structure = self.info_index['structure']

    def load_gerrit(self, gerrit_path, zuul_user, zuul_key):
        self.gerrit_obj = load_structure(gerrit_path)
        self.gerrit_ssh_user = zuul_user
        self.gerrit_ssh_key = zuul_key
        self.gerrit_server = self.gerrit_obj['gerrit']['url']
        self.gerrit_user = self.gerrit_obj['gerrit']['user']
        self.gerrit_pwd = self.gerrit_obj['gerrit']['pwd']
        self.gerrit_ssh_server = self.gerrit_obj['gerrit']['ssh_server']
        self.gerrit_ssh_port = self.gerrit_obj['gerrit']['ssh_port']
        self.gerrit_rest = gerrit_rest.GerritRestClient(
            self.gerrit_server, self.gerrit_user, self.gerrit_pwd)

        if self.gerrit_obj['gerrit']['auth'] == 'basic':
            self.gerrit_rest.change_to_basic_auth()
        elif self.gerrit_obj['gerrit']['auth'] == 'digest':
            self.gerrit_rest.change_to_digest_auth()

    def update_meta(self, update_dict):
        collection_api.dict_merge(self.meta, update_dict)

    def check_coam_integration(self):
        coam_components = list()
        pit_impacted_components = self.comp_config['pit_impacted']
        branch = None
        for node in self.info_index['structure']:
            if 'type' in node and 'root' in node['type']:
                branch = node['branch']
            if node['name'] in pit_impacted_components:
                coam_components.append(node['name'])
        if len(coam_components) > 1:
            self.info_index['structure'].append({
                'branch': branch,
                'name': 'integration_coam',
                'type': 'integration_coam',
                'repo': 'MN/SCMTA/zuul/inte_mn_coam',
                'title': 'Coam Integration Manager',
                'depends': coam_components
            })

    def handle_auto_branch(self, repo, branch_):
        branch = 'refs/heads/' + branch_
        if repo not in self.auto_branch_status:
            self.auto_branch_status[repo] = set()
        if branch in self.auto_branch_status[repo]:
            return
        b_list = self.gerrit_rest.list_branches(repo)
        bn_list = [x['ref'] for x in b_list]
        if branch in bn_list:
            self.auto_branch_status[repo].add(branch)
            return
        self.gerrit_rest.create_branch(repo, branch)
        b_list = self.gerrit_rest.list_branches(repo)
        bn_list = [x['ref'] for x in b_list]
        if branch in bn_list:
            self.auto_branch_status[repo].add(branch)
            return

    def create_file_change_by_env_change(self, file_content, filename):
        env_change = self.meta.get('env_change')
        lines = file_content.split('\n')
        env_change_split = shlex.split(env_change)
        for i, line in enumerate(lines):
            if '=' in line:
                key2, value2 = line.strip().split('=', 1)
                for env_line in env_change_split:
                    if '=' in env_line:
                        key, value = env_line.split('=', 1)
                        if key.strip() == key2.strip():
                            lines[i] = key2 + '=' + value
        for env_line in env_change_split:
            if env_line.startswith('#'):
                lines.append(env_line)
        ret_dict = {filename: '\n'.join(lines)}
        return ret_dict

    def create_ticket_by_node(self, node_obj, integration_mode, ext_commit_msg=None):
        nodes = self.info_index['nodes']
        graph = self.info_index['graph']
        topic = self.meta['topic']
        if 'change_id' not in node_obj or not node_obj['change_id']:
            for edge in graph.in_edges(node_obj['name']):
                depend = edge[0]
                if 'change_id' not in nodes[depend] or \
                        not nodes[depend]['change_id']:
                    return
            message = self.make_description_by_node(node_obj, ext_commit_msg)
            if node_obj['repo'] in auto_branch_repos:
                self.handle_auto_branch(node_obj['repo'], node_obj['branch'])
            base_commit = self.get_base_commit(node_obj, integration_mode)
            change_id, ticket_id, rest_id = self.gerrit_rest.create_ticket(
                node_obj['repo'], None, node_obj['branch'], message, base_change=base_commit
            )
            print ('ticket {} created'.format(ticket_id))
            node_obj['change_id'] = change_id
            node_obj['ticket_id'] = ticket_id
            node_obj['rest_id'] = rest_id
            node_obj['commit_message'] = message

            # env change
            env_change = self.meta.get('env_change')
            if 'type' in node_obj and node_obj['type'] == 'root' and node_obj['repo'] in env_repo:
                if env_change:
                    node_obj['env_change'] = env_change
                    env_path = get_env_repo.get_env_repo_info(self.gerrit_rest, rest_id)[1]
                    env_content = self.gerrit_rest.get_file_content(env_path, rest_id)
                    node_obj['add_files'] = self.create_file_change_by_env_change(env_content,
                                                                                  env_path)

        # restore
        copy_from_id = None
        gop = gerrit_int_op.IntegrationGerritOperation(self.gerrit_rest)

        if 'type' not in node_obj or \
                (node_obj['type'] != 'root' and node_obj['type'] != 'integration'):
            if self.info_index['meta']['backup_topic']:
                copy_from_id = gop.get_ticket_from_topic(
                    self.info_index['meta']['backup_topic'],
                    node_obj['repo'],
                    node_obj['branch'],
                    node_obj['name'])

        need_publish = False

        if 'file_path' not in node_obj or not node_obj['file_path']:
            node_obj['file_path'] = []

        file_paths = node_obj['file_path']

        if copy_from_id:
            gop.copy_change(copy_from_id, node_obj['ticket_id'])
        else:
            # add files to trigger jobs
            if 'files' in node_obj and node_obj['files']:
                for _file in node_obj['files']:
                    file_path = _file + slugify(topic) + '.inte_tmp'
                    file_paths.append(file_path)
                    self.gerrit_rest.add_file_to_change(node_obj['rest_id'],
                                                        file_path,
                                                        datetime.utcnow().
                                                        strftime('%Y%m%d%H%M%S'))
                    need_publish = True

        if 'type' in node_obj and node_obj['type'] == 'integration':
            if 'platform' in self.info_index['meta'] and self.info_index['meta']['platform']:
                for stream in self.info_index['meta']['streams']:
                    file_path = self.info_index['meta']['platform'] + '/' + \
                        stream + '/' + slugify(topic) + '.inte_tmp'
                    file_paths.append(file_path)
                    self.gerrit_rest.add_file_to_change(
                        node_obj['rest_id'],
                        file_path,
                        datetime.utcnow().
                        strftime('%Y%m%d%H%M%S'))
                need_publish = True

        # add files for env
        changes = {}
        if 'add_files' in node_obj and node_obj['add_files']:
            changes = node_obj['add_files']

        for filename, content in changes.items():
            self.gerrit_rest.add_file_to_change(
                node_obj['rest_id'],
                filename, content)
            need_publish = True

        # add files for submodule
        if 'submodules' in node_obj and node_obj['submodules']:
            for path, repo in node_obj['submodules'].items():
                p_node = nodes.get(repo)
                if p_node:
                    if p_node.get('submodule_list') is None:
                        p_node['submodule_list'] = []
                    s_list = p_node.get('submodule_list')
                    s_list.append([path, node_obj['ticket_id']])

        if need_publish:
            self.gerrit_rest.publish_edit(node_obj['rest_id'])

        for child in graph.successors(node_obj['name']):
            try:
                self.create_ticket_by_node(nodes[child], integration_mode, ext_commit_msg)
            except Exception as e:
                print("[Error] create changes failed!Trying to abandon gerrit changes and close jira!")
                nodes = self.info_index['nodes']
                if 'jira_key' in self.meta:
                    create_jira_ticket.close(self.meta['jira_key'])
                for node in nodes.values():
                    if 'ticket_id' in node:
                        self.gerrit_rest.abandon_change(node['ticket_id'])
                        print ('ticket {} is abandoned'.format(node['ticket_id']))
                traceback.print_exc()
                raise Exception(str(e))

    def make_description_by_node(self, node_obj, ext_commit_msg=None):
        print('ext_commit_msg: {}'.format(ext_commit_msg))
        topic = self.meta['topic']
        graph_obj = self.info_index['graph']
        nodes = self.info_index['nodes']
        title_line = '<{change}> on <{version}> of <{title}> topic <{topic}>'.format(
            change=node_obj['name'],
            topic=topic,
            version=self.info_index['meta']['version_name'],
            title=self.info_index['meta']['title']
        )
        lines = textwrap.wrap(title_line, 80)

        if 'type' in node_obj:
            if node_obj['type'] == 'root':
                lines.append('ROOT CHANGE')
                lines.append('Please do not modify this change.')
            elif node_obj['type'] == 'integration' or \
                    node_obj['type'] == 'integration_all' or node_obj['type'] == 'integration_coam':
                lines.append('MANAGER CHANGE')
                lines.append('Please do not modify this change.')
        if 'submodules' in node_obj and node_obj['submodules']:
            lines.append('SUBMODULES PLACEHOLDER CHANGE')
        if 'platform' in self.info_index['meta'] and self.info_index['meta']['platform']:
            lines.append('Platform ID: <{}>'.format(
                self.info_index['meta']['platform']))

        lines.append('  ')
        lines.append('  ')

        section_showed = False
        if 'jira_key' in self.info_index['meta'] and self.info_index['meta']['jira_key']:
            lines.append('%JR={}'.format(self.info_index['meta']['jira_key']))
            section_showed = True

        if 'feature_id' in self.info_index['meta'] and self.info_index['meta']['feature_id']:
            lines.append('%FIFI={}'.format(self.info_index['meta']['feature_id']))
            section_showed = True

        if section_showed:
            lines.append('  ')
            lines.append('  ')

        section_showed = False
        if ext_commit_msg:
            lines.append(ext_commit_msg)
            section_showed = True

        if section_showed:
            lines.append('  ')
            lines.append('  ')

        section_showed = False
        if 'paths' in node_obj and node_obj['paths']:
            lines.append('Please only modify files '
                         'under the following path(s):')
            section_showed = True
            for path in node_obj['paths']:
                lines.append('  - <project root>/{}'.format(path))
        if 'remark' in node_obj and node_obj['remark']:
            lines.append('Remarks: ')
            lines.append('---')
            for line in node_obj['remark']:
                lines.append('{}'.format(textwrap.fill(line, 80)))
            lines.append('---')
            section_showed = True

        if section_showed:
            lines.append('  ')
            lines.append('  ')

        if 'title_replace' in node_obj and node_obj['title_replace']:
            new_title = node_obj['title_replace'].format(node=node_obj,
                                                         meta=self.meta)
            lines.insert(0, '')
            lines.insert(0, new_title)

        section_showed = False
        ric_title = False
        if 'type' in node_obj and \
            (node_obj['type'] == 'integration' or
             node_obj['type'] == 'integration_all'):
            for depend in graph_obj.predecessors(node_obj['name']):
                if depend in nodes:
                    node = nodes[depend]
                    if 'ric' in node and node['ric']:
                        ric_list = node['ric']
                        if len(ric_list) > 0:
                            if not ric_title:
                                lines.append('This integration contains '
                                             'following ric component(s):')
                                ric_title = True
                            section_showed = True
                            for ric in ric_list:
                                f_type = 'component'
                                if 'type' in node:
                                    f_type = node['type']
                                lines.append(
                                    '  - RIC <{}> <{}> <{}> <t:{}>'.format(
                                        ric, node['repo'],
                                        node['ticket_id'],
                                        f_type))

        if section_showed:
            lines.append('  ')
            lines.append('  ')

        section_showed = False
        if 'type' in node_obj and \
            (node_obj['type'] == 'integration' or
             node_obj['type'] == 'integration_all'):
            for name, node in nodes.items():
                if 'type' in node and node['type'] == 'ric':
                    section_showed = True
                    lines.append('RIC file is in following repo:')
                    lines.append('  - RICREPO <{}> <{}>'.format(node['repo'],
                                                                node['ticket_id']))
                    break

        if section_showed:
            lines.append('  ')
            lines.append('  ')

        section_showed = False
        if 'type' in node_obj and \
            (node_obj['type'] == 'integration' or
             node_obj['type'] == 'integration_all'):
            submodule_set = set()
            for name, node in nodes.items():
                if 'submodules' in node and node['submodules']:
                    for key, value in node['submodules'].items():
                        submodule_set.add(value)
            if submodule_set:
                section_showed = True
                lines.append('Temporary branches are in following repo:')
                for sub in submodule_set:
                    lines.append('  - TEMP <{}>'.format(nodes[sub]['repo']))

        if section_showed:
            lines.append('  ')
            lines.append('  ')

        section_showed = False
        if 'submodules' in node_obj and node_obj['submodules']:
            sub_dict = node_obj['submodules']
            if len(sub_dict) > 0:
                lines.append('This change contains following submodule(s):')
                section_showed = True
                for sub_path, sub_project in sub_dict.items():
                    if sub_project in nodes and 'ticket_id' in nodes[sub_project] \
                            and nodes[sub_project]['ticket_id']:
                        lines.append('  - SUBMODULE <{}> <{}> <{}>'.format(
                            sub_path, sub_project,
                            nodes[sub_project]['ticket_id']))

        if section_showed:
            lines.append('  ')
            lines.append('  ')

        section_showed = False
        if 'submodule_roots' in node_obj and node_obj['submodule_roots']:
            sub_list = node_obj['submodule_roots']
            if len(sub_list) > 0:
                lines.append('This change is root of following submodule(s):')
                section_showed = True
                for line in sub_list:
                    proj, branch, path = line.split(',')
                    lines.append('  - SUBMODULEROOT <{}> <{}> <{}>'.format(
                        proj, branch, path))

        if section_showed:
            lines.append('  ')
            lines.append('  ')

        section_showed = False
        if 'ric' in node_obj and node_obj['ric']:
            lines.append('This change contains following component(s):')
            section_showed = True
            for comp in node_obj['ric']:
                lines.append('  - COMP <{}>'.format(comp))

        if section_showed:
            lines.append('  ')
            lines.append('  ')

        section_showed = False
        if len(list(graph_obj.predecessors(node_obj['name']))) > 0:
            lines.append('This change depends on following change(s):')
            section_showed = True
            for depend in graph_obj.predecessors(node_obj['name']):
                if depend in nodes and 'ticket_id' in nodes[depend] and \
                        nodes[depend]['ticket_id']:
                    f_type = 'component'
                    if 'type' in nodes[depend]:
                        f_type = nodes[depend]['type']

                    lines.append('  - Project:<{}> Change:<{}> Type:<{}>'.format(
                        depend, nodes[depend]['ticket_id'], f_type))

        if section_showed:
            lines.append('  ')
            lines.append('  ')

        for depend in graph_obj.predecessors(node_obj['name']):
            if depend in nodes and 'change_id' in nodes[depend] and \
                    nodes[depend]['change_id']:
                lines.append('Depends-on: {}'.format(
                    nodes[depend]['change_id']))

        lines.append('  ')

        description = '\n'.join(lines)
        return description

    def add_structure_string(self):
        root_node = self.info_index['root']
        integration_node = self.info_index['mn']
        nodes = self.info_index['nodes']
        structure_dict = {'root': root_node['ticket_id'],
                          'manager': integration_node['ticket_id'],
                          'tickets': []}
        for node in nodes.values():
            if node is not root_node and node is not integration_node and \
                    node.get('type') != 'auto_submodule':
                structure_dict['tickets'].append(node['ticket_id'])

        json_result = json.dumps(structure_dict)
        result = 'Tickets-List: {}'.format(json_result)
        self.gerrit_rest.review_ticket(root_node['rest_id'], result)
        # submodule string
        list_s = root_node.get('submodule_list')
        if list_s:
            json_sub_result = json.dumps(list_s)
            sub_result = 'Submodules-List: {}'.format(json_sub_result)
            self.gerrit_rest.review_ticket(root_node['rest_id'], sub_result)

    def label_all_tickets(self):
        root_node = self.info_index['root']
        integration_node = self.info_index['mn']
        nodes = self.info_index['nodes']
        gerrit_api.review_patch_set(self.gerrit_ssh_user, self.gerrit_ssh_server,
                                    root_node['ticket_id'],
                                    ['Integrated=-1'], 'init_label',
                                    self.gerrit_ssh_key, self.gerrit_ssh_port)
        for node in nodes.values():
            if node is not root_node and node is not integration_node:
                if 'auto_code_review' in node and node['auto_code_review']:
                    self.gerrit_rest.review_ticket(
                        node['rest_id'],
                        'Initial label', {'Code-Review': int(node['auto_code_review'])})

            if 'reviewers' in node and node['reviewers']:
                for reviewer in node['reviewers']:
                    try:
                        self.gerrit_rest.add_reviewer(node['rest_id'], reviewer)
                    except Exception as ex:
                        print('Adding reviwer failed, {}'.format(str(ex)))

            comment_list = node.get('comments')
            if comment_list:
                for comment_str in comment_list:
                    self.gerrit_rest.review_ticket(node['rest_id'], comment_str)

    def parse_base_commits(self, base_commit_str):
        list1 = base_commit_str.split(';')
        for item1 in list1:
            list2 = item1.split(':')
            self.base_commits_info[list2[0]] = list2[1]

    def get_base_commit(self, node_obj, integration_mode):
        project = node_obj['repo']
        branch = node_obj['branch']
        key = '{},{}'.format(project, branch)
        print('[Info] Integration mode is: {}'.format(integration_mode))
        if 'Head' in integration_mode:
            commit_info = self.gerrit_rest.get_latest_commit_from_branch(project, branch)
            commit_hash = commit_info['revision']
        elif 'Fixed_base' in integration_mode:
            if 'MN/SCMTA/zuul/inte_ric' in project or 'MN/SCMTA/zuul/inte_mn' in project:
                commit_info = self.gerrit_rest.get_latest_commit_from_branch(project, branch)
                commit_hash = commit_info['revision']
            elif 'MN/SCMTA/zuul/inte_root' in project:
                commit_info = self.gerrit_rest.get_latest_commit_from_branch('MN/SCMTA/zuul/inte_root', branch)
                commit_hash = commit_info['revision']
            elif 'airphone' in project:
                commit_info = self.gerrit_rest.get_latest_commit_from_branch('MN/5G/AIRPHONE/airphone', branch)
                commit_hash = commit_info['revision']
            else:
                commit_hash = self.base_commits_info.get(node_obj['name'])
                if not commit_hash and 'ric' in node_obj:
                    commit_hash = self.base_commits_info.get(node_obj['ric'][0])
        print('[Info] Get commit_hash [{}] for component [{}]'.format(commit_hash, node_obj['name']))
        commit = ''
        if commit_hash:
            change_info = self.gerrit_rest.query_ticket('commit:{}'.format(commit_hash), count=1)
            if change_info:
                change_info = change_info[0]
                commit = change_info['_number']
                self.base_commits_info[key] = commit
                print('[Info] Get change number [{}] for key [{}]'.format(commit, key))
        else:
            raise Exception('[Error] Failed to get commit hash for component {}'.format(node_obj['name']))
        return commit

    def update_oam_description(self):
        for node in self.info_index['nodes']:
            try:
                node_dict = CONF.get_dict(node)
            except Exception:
                continue
            title = ''
            if 'feature_id' in self.meta:
                title = '{}_%FIFI={}'.format(
                    self.info_index['nodes'][node]['ticket_id'],
                    self.meta['feature_id'])
            elif 'version_name' in self.meta:
                title = '{}_%FIFI={}'.format(
                    self.info_index['nodes'][node]['ticket_id'],
                    self.meta['version_name'])
            if not title:
                raise Exception('No feature_id or version_name in meta')
            oam_description = [
                'MR will be created in {}/{} soon.'.format(node_dict['repo_server'], node_dict['repo_project']),
                'title: {}'.format(title),
                'branch: int_{}'.format(title)
            ]
            self.info_index['nodes'][node]['description'] += oam_description

    def print_result(self):
        root_node = self.info_index['root']
        integration_node = self.info_index['mn']
        nodes = self.info_index['nodes']
        root_change = root_node['ticket_id']
        print('Root change: {}'.format(self.gerrit_rest.get_change_address(root_change)))
        integration_change = integration_node['ticket_id']
        print('Integration change: {}'.format(self.gerrit_rest.get_change_address(integration_change)))
        component_changes = ''
        print('Component changes:')
        for node in nodes.values():
            if node is not root_node and node is not integration_node:
                node_change = node['ticket_id']
                component_changes += ' {}'.format(node_change)
                print(self.gerrit_rest.get_change_address(node_change))
        result_dict = {
            'RootID': root_change,
            'integration': integration_change,
            'component': component_changes
        }
        path = os.path.join(job_tool.get_workspace(), 'result')
        job_tool.write_dict_to_properties(result_dict, path, False)

    def get_base_commit_from_other(self, base_load, ric_com):
        comp_ver = ''
        for build in self.base_load_list:
            module_ver = build
            if module_ver == base_load:
                continue
            get_comp_info = get_component_info.GET_COMPONENT_INFO(base_load)
            try:
                comp_ver = get_comp_info.get_comp_hash(ric_com)
            except Exception as e:
                print e
                print "[WARNING]Can't get base commit from {0}".format(module_ver)
            if comp_ver:
                return comp_ver
        return comp_ver

    def parse_base_load(self, base_load):
        base_commits = {}
        get_comp_info = get_component_info.GET_COMPONENT_INFO(base_load)
        node_list = self.info_index['nodes'].values()
        print("[Info] Start to parse base load for node_list: {}".format(node_list))
        for node in node_list:
            print("[Info] Parse component: {}".format(node['name']))
            if 'type' in node and 'root' in node['type']:
                if 'MN/5G/COMMON/env' in node['repo']:
                    com_ver = get_comp_info.get_comp_hash('env')
                    base_commits['env'] = com_ver
                    print("[Info] Base commit for env is: {}".format(com_ver))
                    continue
            if 'MN/5G/COMMON/integration' in node['repo']:
                base_commits['integration'] = base_load
                continue
            if 'type' in node and 'integration' in node['type']:
                continue
            if 'airphone' in node['repo']:
                try:
                    com_ver = get_comp_info.get_comp_hash(node['ric'][0])
                    base_commits[node['ric'][0]] = com_ver
                    print("[Info] Base commit for component {} is {}".format(node['ric'][0], com_ver))
                except Exception as e:
                    print e
                    print("[Warning] failed to find commit in base package, will use HEAD instead!")
                continue
            if 'type' in node and 'external' in node['type']:
                if 'ric' in node and node['ric']:
                    for ric_com in node['ric']:
                        com_ver = ''
                        try:
                            com_ver = get_comp_info.get_comp_hash(ric_com)
                            print("[Info] Base commit for component {} is {}".format(ric_com, com_ver))
                        except Exception as e:
                            print e
                        if not com_ver:
                            print("[Warning] failed to find commit in {0}, will try other streams".format(base_load))
                            com_ver = self.get_base_commit_from_other(base_load, ric_com)
                        if com_ver:
                            base_commits[ric_com] = com_ver
                        else:
                            print("[Warning] failed to find commit in base package, will use HEAD instead!")

            else:
                if 'ric' in node and node['ric']:
                    com_ver = ''
                    try:
                        com_ver = get_comp_info.get_comp_hash(node['ric'][0])
                    except Exception as e:
                        print e
                    if not com_ver:
                        print("[Warning] failed to find commit in {0}, will try other streams".format(base_load))
                        com_ver = self.get_base_commit_from_other(base_load, node['ric'][0])
                    base_commits[node['name']] = com_ver
                    print("[Info] Base commit for component {} is {}".format(node['ric'][0], com_ver))
        if base_commits.values():
            print("[Info] value for base_commits is: {}".format(base_commits))
            return base_commits
        print("[Error] Failed to parse base_commits!")
        return None

    def insert_integration_mode(self, integration_mode, base_load, base_commits):
        if not integration_mode:
            raise Exception('[Error] No integration mode specified!')
        if 'Fixed_base' in integration_mode:
            if not base_load:
                raise Exception('[Error] do integration on fixed mode but base_load not specified!')
            int_mode = '<without-zuul-rebase>'
        else:
            int_mode = '<with-zuul-rebase>'
        for node in self.info_index['nodes'].values():
            if 'remark' in node:
                self.info_index['nodes'][node['name']]['remark'].append(int_mode)
            else:
                self.info_index['nodes'][node['name']]['remark'] = [int_mode]
            if int_mode == '<without-zuul-rebase>':
                if 'MN/5G/NB/gnb' in node['repo']:
                    if 'title_replace' not in node:
                        raise Exception('[Error] No title_replace keyword in gnb node')
                    else:
                        self.info_index['nodes'][node['name']]['title_replace'] = '[none] [NOREBASE] {node[name]} {meta[version_name]} {meta[branch]}'
                if 'type' in node and 'integration' in node['type'] and 'all' not in node['type']:
                    for build in self.base_load_list:
                        if 'comments' in node:
                            self.info_index['nodes'][node['name']]['comments'].append('update_base:{},{}'.format(build.rsplit('.', 1)[0], build))
                        else:
                            self.info_index['nodes'][node['name']]['comments'] = ['update_base:{},{}'.format(build.rsplit('.', 1)[0], build)]
                if base_commits and 'MN/SCMTA/zuul/inte_ric' in node['repo']:
                    if node['name'] in base_commits:
                        base_commit_info = base_commits[node['name']]
                    elif 'ric' in node and node['ric'][0] in base_commits:
                        base_commit_info = base_commits[node['ric'][0]]
                    else:
                        base_commit_info = ''
                    if base_commit_info:
                        if 'remark' in node:
                            self.info_index['nodes'][node['name']]['remark'].append('base_commit:{}'
                                                                                    .format(base_commit_info))
                        else:
                            self.info_index['nodes'][node['name']]['remark'] = \
                                ['base_commit:{}'.format(base_commit_info)]
            if int_mode == '<with-zuul-rebase>':
                if 'type' in node and 'integration' in node['type'] and 'all' not in node['type']:
                    if 'comments' in node:
                        self.info_index['nodes'][node['name']]['comments'].append('use_default_base')
                    else:
                        self.info_index['nodes'][node['name']]['comments'] = ['use_default_base']

    def get_base_comp(self):
        base_comp_list = self.comp_config['depends_components']
        base_comp = []
        for node in self.info_index['nodes'].values():
            if 'type' in node and 'root' in node['type']:
                continue
            if node['name'] in base_comp_list:
                base_comp.append(node['name'])
        if len(base_comp) < 1:
            return None
        return base_comp

    def update_base_depends(self, base_comp):
        print('[Info] Going to add depends on base components: {}'.format(base_comp))
        for comp in base_comp:
            change_id = None
            for node in self.info_index['nodes'].values():
                if comp in node['name']:
                    change_id = node['change_id']
            if not change_id:
                raise Exception('Failed to set depends on for base component {}'.format(comp))
            for node in self.info_index['nodes'].values():
                if any(base_name in node['name'] for base_name in base_comp):
                    print('{} is in base component list'.format(node['name']))
                    continue
                if node is not self.info_index['root'] and node is not self.info_index['mn']:
                    comp_change = inte_change.IntegrationChange(self.gerrit_rest, node['ticket_id'])
                    commit_msg_obj = inte_change.IntegrationCommitMessage(comp_change)
                    begin_line = -1
                    for i, v in enumerate(commit_msg_obj.msg_lines):
                        if v.startswith('Depends-on: '):
                            begin_line = i + 1
                    if begin_line > -1:
                        line_value = 'Depends-on: {}'.format(change_id)
                        commit_msg_obj.msg_lines.insert(begin_line, line_value)
                        new_msg = commit_msg_obj.get_msg()
                        try:
                            self.gerrit_rest.delete_edit(node['ticket_id'])
                        except Exception as e:
                            print(e)
                        self.gerrit_rest.change_commit_msg_to_edit(node['ticket_id'], new_msg)
                        self.gerrit_rest.publish_edit(node['ticket_id'])

    def run(self, version_name=None, topic_prefix=None, streams=None,
            jira_key=None, feature_id=None, feature_owner=None,
            if_restore=False, integration_mode=None, base_load=None,
            env_change=None, ext_commit_msg=None, mysql_info=None,
            comp_config=None,
            open_jira=False, skip_jira=False):

        # handle integration topic
        utc_dt = datetime.utcnow()
        timestr = utc_dt.replace(microsecond=0).isoformat().replace(':', '_')
        if comp_config:
            self.comp_config = yaml.load(open(comp_config), Loader=yaml.Loader, version='1.1')
        if not topic_prefix:
            topic = 't_{}'.format(timestr)
        else:
            topic = '{}_{}'.format(topic_prefix, timestr)
        topic = slugify(topic)
        self.meta['topic'] = topic

        if env_change:
            self.meta['env_change'] = env_change

        if feature_owner and feature_owner != 'anonymous' and not self.meta['jira']['assignee']:
            self.meta['jira']['assignee'] = {'name': feature_owner}

        self.check_coam_integration()

        # create graph
        root_node, integration_node, nodes, graph_obj = create_graph(self.info_index)
        check_graph_availability(graph_obj, root_node, integration_node)

        self.info_index['root'] = root_node
        self.info_index['mn'] = integration_node
        self.info_index['nodes'] = nodes
        self.info_index['graph'] = graph_obj

        if streams:
            stream_list = [x for x in streams.split(',') if x]
            if not stream_list:
                stream_list = ['default']
        else:
            stream_list = ['default']

        self.meta['streams'] = stream_list

        # handle base load
        base_commits = None
        if "Fixed_base" in integration_mode:
            if base_load:
                self.base_load_list = [x for x in base_load.split(',') if x.strip()]
                if self.base_load_list:
                    base_load = wft_tools.get_newer_base_load(self.base_load_list)
                else:
                    base_load, self.base_load_list = wft_tools.get_latest_qt_load(self.meta['streams'])
            else:
                base_load, self.base_load_list = wft_tools.get_latest_qt_load(self.meta['streams'])
            if '_' in base_load:
                base_load = base_load.split('_')[-1]
            base_commits = self.parse_base_load(base_load)
            if base_commits:
                self.base_commits_info = base_commits

        # insert integration mode to changes
        self.insert_integration_mode(integration_mode, base_load, base_commits)

        # restore
        self.meta['backup_topic'] = None
        if if_restore:
            platform = self.meta.get('platform')
            if platform:
                backup_topic = 'integration_{}_backup'.format(platform)
                self.meta['backup_topic'] = backup_topic

        # handle version name
        if not version_name and env_change:
            versions = set()
            env_change_split = shlex.split(env_change)
            for line in env_change_split:
                line = line.strip()
                env_list = line.split('=', 2)
                if len(env_list) >= 2:
                    versions.add(env_list[1])

            if versions:
                vk = self.meta.get('version_keyword')
                if vk:
                    for value in versions:
                        if vk in value and len(value) < 35:
                            version_name = value
                            break
                else:
                    for value in versions:
                        if len(value) <= 35:
                            if version_name:
                                if len(version_name) + 1 + len(value) <= 50:
                                    version_name += '/'
                                    version_name += value
                                else:
                                    break
                            else:
                                version_name = value
        if not version_name:
            if feature_id:
                version_name = feature_id
            elif jira_key:
                version_name = jira_key
            else:
                version_name = timestr

        self.meta['version_name'] = version_name

        # handle jira
        if jira_key:
            self.meta['jira_key'] = jira_key
        else:
            if not skip_jira:
                if 'jira' in self.meta:
                    try:
                        jira_key = create_jira_ticket.run(self.info_index)
                        self.meta["jira_key"] = jira_key
                        if open_jira:
                            create_jira_ticket.open(jira_key)
                    except Exception as ex:
                        print('Exception occured while create jira ticket, {}'.format(str(ex)))
                        raise ex

        # handle feature id
        if feature_id:
            self.meta['feature_id'] = feature_id
        else:
            self.meta['feature_id'] = version_name

        print('[JOBTAG] Version name is {}. '
              'Jira key is {}. '
              'Feature id is {}'.format(
                  self.meta.get('version_name'),
                  self.meta.get('jira_key'),
                  self.meta.get('feature_id')))

        self.create_ticket_by_node(root_node, integration_mode, ext_commit_msg)
        self.add_structure_string()
        self.label_all_tickets()
        self.update_oam_description()
        if 'interface info:' in ext_commit_msg:
            comp_change_list = [node['ticket_id'] for node in self.info_index['nodes'].values() if
                                node.get('type') != 'auto_submodule']
            update_interfaces_refs(rest=self.gerrit_rest,
                                   comp_change_list=comp_change_list,
                                   comp_name=re.search(r'comp_name:\W+(.*)', ext_commit_msg).group(1),
                                   commit_id=re.search(r'commit-ID:\W+(.*)', ext_commit_msg).group(1)
                                   )
        # handle node need to be depends on
        base_comp = self.get_base_comp()
        if base_comp:
            self.update_base_depends(base_comp)
        self.print_result()
        send_result_email.run(self.info_index)
        if mysql_info:
            retry = 5
            while True:
                if not skytrack_database_handler.if_issue_exist(
                        database_info_path=mysql_info,
                        issue_key=self.meta["jira_key"]
                ):
                    print "[WARNING] {0} haven't created in skytrack database".format(self.meta["jira_key"])
                    print "Will retry in 20s"
                    time.sleep(20)
                    if retry == 0:
                        print "[WARNING] retry end, can not update integration mode"
                        break
                    retry -= 1
                    print "Retry left {0} times".format(retry)
                    continue
                wft_build_list = [wft_tools.get_wft_release_name(build) for build in self.base_load_list]
                skytrack_database_handler.update_integration_mode(
                    database_info_path=mysql_info,
                    issue_key=self.meta["jira_key"],
                    integration_mode=integration_mode,
                    fixed_build=','.join(wft_build_list),)
                break
            skytrack_database_handler.update_events(
                database_info_path=mysql_info,
                integration_name=self.info_index['meta']['jira_key'],
                description="Integration Topic created"
            )


@click.group()
@click.option('--yaml-path', type=unicode)
@click.option('--gerrit-path', type=unicode)
@click.option('--zuul-user', type=unicode)
@click.option('--zuul-key', type=unicode)
@click.pass_context
def cli(ctx, yaml_path, gerrit_path, zuul_user, zuul_key):
    ctx.obj['obj'] = IntegrationChangesCreation(
        yaml_path, gerrit_path, zuul_user, zuul_key)
    pass


@cli.command()
@click.option('--version-name', default=None, type=unicode)
@click.option('--topic-prefix', default=None, type=unicode)
@click.option('--streams', default=None, type=unicode)
@click.option('--jira-key', default=None, type=unicode)
@click.option('--feature-id', default=None, type=unicode)
@click.option('--feature-owner', default=None, type=unicode)
@click.option('--if-restore', default=False, type=bool)
@click.option('--integration-mode', default=None, type=unicode)
@click.option('--base-load', default=None, type=unicode)
@click.option('--env-change', default=None, type=unicode)
@click.option('--ext_commit_msg', default=None, type=unicode)
@click.option('--mysql_info', default=None, type=unicode)
@click.option('--comp_config', default=None, type=unicode)
@click.option('--open-jira', default=False, type=bool)
@click.option('--skip-jira', default=False, type=bool)
@click.option('--version_name', default=None, type=unicode)
@click.pass_context
def create_changes(ctx, version_name=None,
                   topic_prefix=None, streams=None,
                   jira_key=None, feature_id=None, feature_owner=None, if_restore=False,
                   integration_mode=None, base_load=None, ext_commit_msg=None,
                   mysql_info=None, comp_config=None, env_change=None,
                   open_jira=False, skip_jira=False):
    icc = ctx.obj['obj']
    icc.run(version_name=version_name, topic_prefix=topic_prefix,
            streams=streams, jira_key=jira_key,
            feature_id=feature_id, feature_owner=feature_owner,
            if_restore=if_restore, integration_mode=integration_mode,
            base_load=base_load, env_change=env_change,
            ext_commit_msg=ext_commit_msg, mysql_info=mysql_info,
            comp_config=comp_config,
            open_jira=open_jira, skip_jira=skip_jira)


if __name__ == '__main__':
    try:
        # pylint: disable=E1123
        cli(obj={})
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
