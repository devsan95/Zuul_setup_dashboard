#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import copy
import json
import os
import shlex
import sys
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
from api import collection_api
from api import gerrit_api
from api import gerrit_rest
from api import job_tool
from api import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

auto_branch_repos = ['MN/SCMTA/zuul/inte_mn', 'MN/SCMTA/zuul/inte_ric', 'MN/SCMTA/zuul/inte_root', 'MN/5G/COMMON/env']
env_repo = 'MN/5G/COMMON/env'

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

    def create_ticket_by_node(self, node_obj):
        nodes = self.info_index['nodes']
        graph = self.info_index['graph']
        topic = self.meta['topic']
        if 'change_id' not in node_obj or not node_obj['change_id']:
            for edge in graph.in_edges(node_obj['name']):
                depend = edge[0]
                if 'change_id' not in nodes[depend] or \
                        not nodes[depend]['change_id']:
                    return
            message = self.make_description_by_node(node_obj)
            if node_obj['repo'] in auto_branch_repos:
                self.handle_auto_branch(node_obj['repo'], node_obj['branch'])
            base_commit = self.get_base_commit(node_obj['repo'], node_obj['branch'])
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
            if 'type' in node_obj and node_obj['type'] == 'root' and node_obj['repo'] == env_repo:
                if env_change:
                    node_obj['env_change'] = env_change
                    env_content = self.gerrit_rest.get_file_content('env-config.d/ENV', rest_id)
                    node_obj['add_files'] = self.create_file_change_by_env_change(env_content, 'env-config.d/ENV')

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
                self.create_ticket_by_node(nodes[child])
            except Exception:
                print("[Error] create changes failed!Trying to abandon gerrit changes and close jira!")
                nodes = self.info_index['nodes']
                if 'jira_key' in self.meta:
                    create_jira_ticket.close(self.meta['jira_key'])
                for node in nodes.values():
                    if 'ticket_id' in node:
                        self.gerrit_rest.abandon_change(node['ticket_id'])
                        print ('ticket {} is abandoned'.format(node['ticket_id']))
                raise Exception

    def make_description_by_node(self, node_obj):
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
                    node_obj['type'] == 'integration_all':
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
                                             'following ric conponent(s):')
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
        self.gerrit_rest.review_ticket(root_node['rest_id'], 'reintegrate')
        self.gerrit_rest.review_ticket(integration_node['rest_id'], 'reexperiment')
        for node in nodes.values():
            if node is not root_node and node is not integration_node:
                if 'auto_code_reveiw' in node and not node['auto_code_reveiw']:
                    pass
                else:
                    self.gerrit_rest.review_ticket(
                        node['rest_id'],
                        'Initial label', {'Code-Review': 2})
                    # gerrit_api.review_patch_set(zuul_user, zuul_server,
                    #                             node['ticket_id'],
                    #                             ['Integrated=0'], 'init_label',
                    #                             zuul_key, zuul_port)

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

    def get_base_commit(self, project, branch):
        key = '{},{}'.format(project, branch)
        commit = self.base_commits_info.get(key)
        print('Get commit [{}] from key [{}]'.format(commit, key))
        if not commit:
            commit_info = self.gerrit_rest.get_latest_commit_from_branch(project, branch)
            commit_hash = commit_info['revision']
            change_info = self.gerrit_rest.query_ticket('commit:{}'.format(commit_hash), count=1)
            if change_info:
                change_info = change_info[0]
                commit = change_info['_number']
                self.base_commits_info[key] = commit
                print('Set commit [{}] to key [{}]'.format(commit, key))
        return commit

    def update_oam_description(self):
        for node in self.info_index['nodes']:
            try:
                node_dict = CONF.get_dict(node)
            except Exception:
                continue
            title = '{}_%FIFI={}'.format(self.info_index['nodes'][node]['ticket_id'], self.meta['feature_id'])
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

    def run(self, version_name=None, topic_prefix=None, streams=None,
            jira_key=None, feature_id=None, feature_owner=None,
            if_restore=False, base_commits=None, env_change=None,
            force_feature_id=False, open_jira=False, skip_jira=False):

        if base_commits:
            self.parse_base_commits(base_commits)

        # handle integration topic
        utc_dt = datetime.utcnow()
        timestr = utc_dt.replace(microsecond=0).isoformat()
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

        # create graph
        root_node, integration_node, nodes, graph_obj = create_graph(self.info_index)
        check_graph_availability(graph_obj, root_node, integration_node)

        self.info_index['root'] = root_node
        self.info_index['mn'] = integration_node
        self.info_index['nodes'] = nodes
        self.info_index['graph'] = graph_obj

        # restore
        self.meta['backup_topic'] = None
        if if_restore:
            platform = self.meta.get('platform')
            if platform:
                backup_topic = 'integration_{}_backup'.format(platform)
                self.meta['backup_topic'] = backup_topic

        if streams:
            stream_list = [x for x in streams.split(',') if x]
            if not stream_list:
                stream_list = ['default']
        else:
            stream_list = ['default']

        self.meta['streams'] = stream_list

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
                                if len(version_name) + 1 + len(value) <= 60:
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
        elif 'jira_key' in self.meta and force_feature_id:
            self.meta['feature_id'] = self.meta['jira_key']

        print('[JOBTAG] Version name is {}. '
              'Jira key is {}. '
              'Feature id is {}'.format(
                  self.meta.get('version_name'),
                  self.meta.get('jira_key'),
                  self.meta.get('feature_id')))

        self.create_ticket_by_node(root_node)
        self.add_structure_string()
        self.label_all_tickets()
        self.update_oam_description()
        self.print_result()
        send_result_email.run(self.info_index)


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
@click.option('--base-commits', default=None, type=unicode)
@click.option('--env-change', default=None, type=unicode)
@click.option('--force-feature-id', default=False, type=bool)
@click.option('--open-jira', default=False, type=bool)
@click.option('--skip-jira', default=False, type=bool)
@click.pass_context
def create_changes(ctx, version_name=None,
                   topic_prefix=None, streams=None,
                   jira_key=None, feature_id=None, feature_owner=None, if_restore=False,
                   base_commits=None, env_change=None, force_feature_id=False,
                   open_jira=False, skip_jira=False):
    icc = ctx.obj['obj']
    icc.run(version_name, topic_prefix, streams, jira_key,
            feature_id, feature_owner, if_restore, base_commits,
            env_change, force_feature_id, open_jira, skip_jira)


if __name__ == '__main__':
    try:
        cli(obj={})
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
