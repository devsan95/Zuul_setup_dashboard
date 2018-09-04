#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import copy
import json
import os
import sys
import textwrap
import traceback
from datetime import datetime

import fire
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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_structure(path):
    structure_obj = yaml.load(open(path),
                              Loader=yaml.Loader, version='1.1')
    return structure_obj


def create_graph(structure_obj):
    root_node = None
    nodes = {}
    integration_node = None

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

    # make manager node depends on all other nodes
    for node in node_list:
        if node is not integration_node:
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
            change_id, ticket_id, rest_id = self.gerrit_rest.create_ticket(
                node_obj['repo'], None, node_obj['branch'], message
            )
            node_obj['change_id'] = change_id
            node_obj['ticket_id'] = ticket_id
            node_obj['rest_id'] = rest_id
            node_obj['commit_message'] = message

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

        if need_publish:
            self.gerrit_rest.publish_edit(node_obj['rest_id'])

        for child in graph.successors(node_obj['name']):
            self.create_ticket_by_node(nodes[child])

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
            elif node_obj['type'] == 'integration':
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
        if 'type' in node_obj and node_obj['type'] == 'integration':
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
        if 'type' in node_obj and node_obj['type'] == 'integration':
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
        if 'type' in node_obj and node_obj['type'] == 'integration':
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

    def run(self, version_name=None, topic_prefix=None, streams=None, jira_key=None,
            if_restore=False):

        # handle integration topic
        utc_dt = datetime.utcnow()
        timestr = utc_dt.replace(microsecond=0).isoformat()
        if not topic_prefix:
            topic = 't_{}'.format(timestr)
        else:
            topic = '{}_{}'.format(topic_prefix, timestr)
        topic = slugify(topic)
        self.meta['topic'] = topic

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
            stream_list = streams.split(',')
        else:
            stream_list = ['default']

        self.meta['streams'] = stream_list

        # handle version name
        if not version_name:
            if jira_key:
                self.meta['version_name'] = jira_key
            else:
                version_name = timestr
                self.meta['version_name'] = version_name

        # handle jira
        if jira_key:
            self.meta['jira_key'] = jira_key
        else:
            if 'jira' in self.meta:
                try:
                    jira_key = create_jira_ticket.run(self.info_index)
                    self.meta["jira_key"] = jira_key
                except Exception as ex:
                    print('Exception occured while create jira ticket, {}'.format(str(ex)))

        print('[JOBTAG] Version name is {}. Jira key is {}'.format(self.meta['version_name'], self.meta.get('jira_key')))

        self.create_ticket_by_node(root_node)
        self.add_structure_string()
        self.label_all_tickets()
        self.print_result()
        send_result_email.run(self.info_index)


if __name__ == '__main__':
    try:
        fire.Fire(IntegrationChangesCreation)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)