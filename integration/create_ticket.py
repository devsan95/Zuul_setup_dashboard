#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import argparse
import json
import os
import shlex
import sys
import textwrap
import traceback
from datetime import datetime

import git
import networkx as nx
import requests
import ruamel.yaml as yaml
import urllib3
from slugify import slugify

import create_jira_ticket
import gerrit_int_op
import send_result_email
from api import file_api
from api import gerrit_api
from api import gerrit_rest
from api import job_tool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Create ticket according to structure file')
    parser.add_argument('path', type=str,
                        help='path to structure file')

    parser.add_argument('gerrit_path', type=str,
                        help='path to gerrit info file')

    parser.add_argument('--topic-prefix', type=str, dest='topic_prefix',
                        help='topic suffix')

    parser.add_argument('--init-ticket', type=str, dest='init_ticket',
                        default=None, help='initial ticket')

    parser.add_argument('--zuul-user', type=str, dest='zuul_user',
                        help='')

    parser.add_argument('--zuul-key', type=str, dest='zuul_key',
                        help='')

    parser.add_argument('--input-branch', type=str, dest='input_branch',
                        default=None, help='')

    parser.add_argument('--ric-file', type=str, dest='ric_path',
                        default=None, help='')

    parser.add_argument('--heat-template', type=str, dest='heat_template',
                        default=None, help='')

    parser.add_argument('--version-name', type=str, dest='version_name',
                        default=None, help='')

    parser.add_argument('--env-change', type=str, dest='env_change',
                        help='')

    parser.add_argument('--streams', type=str, dest='streams',
                        default=None, help='')

    parser.add_argument('--restore-from-topic', type=int, dest='if_restore',
                        default=0, help='')

    args = parser.parse_args()
    return vars(args)


def load_structure(path):
    structure_obj = yaml.load(open(path),
                              Loader=yaml.Loader, version='1.1')
    return structure_obj


def strip_begin(text, prefix):
    if not text.startswith(prefix):
        return text
    return text[len(prefix):]


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


def create_ticket_by_graph(root_node, integration_node, graph_obj, nodes,
                           topic, gerrit_client, info_index):
    create_ticket_by_node(root_node, topic, graph_obj, nodes, root_node,
                          gerrit_client, info_index)


def create_ticket_by_node(node_obj, topic, graph_obj, nodes, root_node,
                          gerrit_client, info_index):
    if 'change_id' not in node_obj or not node_obj['change_id']:
        for edge in graph_obj.in_edges(node_obj['name']):
            depend = edge[0]
            if 'change_id' not in nodes[depend] or \
                    not nodes[depend]['change_id']:
                return
        message = make_description_by_node(node_obj, nodes, graph_obj, topic,
                                           info_index)
        change_id, ticket_id, rest_id = gerrit_client.create_ticket(
            node_obj['repo'], None, node_obj['branch'], message
        )
        node_obj['change_id'] = change_id
        node_obj['ticket_id'] = ticket_id
        node_obj['rest_id'] = rest_id
        node_obj['commit_message'] = message

    # restore
    copy_from_id = None
    gop = gerrit_int_op.IntegrationGerritOperation(gerrit_client)

    if 'type' not in node_obj or \
            (node_obj['type'] != 'root' and node_obj['type'] != 'integration'):
        if info_index['meta']['backup_topic']:
            copy_from_id = gop.get_ticket_from_topic(
                info_index['meta']['backup_topic'],
                node_obj['repo'],
                node_obj['branch'],
                node_obj['name'])

    need_publish = False

    if 'file_path' not in node_obj or not node_obj['file_path']:
        node_obj['file_path'] = []

    file_paths = node_obj['file_path']

    if copy_from_id:
        gop.copy_change(copy_from_id, node_obj['ticket_id'], True)
    else:
        # add files to trigger jobs
        if 'files' in node_obj and node_obj['files']:
            for _file in node_obj['files']:
                file_path = _file + slugify(topic) + '.inte_tmp'
                file_paths.append(file_path)
                gerrit_client.add_file_to_change(node_obj['rest_id'],
                                                 file_path,
                                                 datetime.utcnow().
                                                 strftime('%Y%m%d%H%M%S'))
                need_publish = True

    if 'type' in node_obj and node_obj['type'] == 'integration':
        if 'platform' in info_index['meta'] and info_index['meta']['platform']:
            for stream in info_index['meta']['streams']:
                file_path = info_index['meta']['platform'] + '/' + \
                    stream + '/' + slugify(topic) + '.inte_tmp'
                file_paths.append(file_path)
                gerrit_client.add_file_to_change(node_obj['rest_id'],
                                                 file_path,
                                                 datetime.utcnow().
                                                 strftime('%Y%m%d%H%M%S'))
            need_publish = True

    # add files for env
    changes = {}
    if 'add_files' in node_obj and node_obj['add_files']:
        changes = node_obj['add_files']

    for filename, content in changes.items():
        gerrit_client.add_file_to_change(node_obj['rest_id'],
                                         filename, content)
        need_publish = True

    # add files for submodule
    if 'submodules' in node_obj and node_obj['submodules']:
        for path, repo in node_obj['submodules'].items():
            # if repo in nodes and 'temp_commit' in nodes[repo] and \
            #         nodes[repo]['temp_commit']:
            #     gerrit_client.add_file_to_change(
            #         node_obj['rest_id'], path, '{}'.format(
            #             nodes[repo]['temp_commit']))
            #     need_publish = True
            p_node = nodes.get(repo)
            if p_node:
                if p_node.get('submodule_list') is None:
                    p_node['submodule_list'] = []
                s_list = p_node.get('submodule_list')
                s_list.append([path, node_obj['ticket_id']])

    if 'type' in node_obj and node_obj['type'] == 'ric':
        gerrit_client.add_file_to_change(node_obj['rest_id'],
                                         'ric_{}'.format(topic),
                                         '{}'.format(root_node['ric_content']))
        need_publish = True

    if need_publish:
        gerrit_client.publish_edit(node_obj['rest_id'])

    for child in graph_obj.successors(node_obj['name']):
        create_ticket_by_node(nodes[child], topic, graph_obj, nodes, root_node,
                              gerrit_client, info_index)


def make_description_by_node(node_obj, nodes, graph_obj, topic, info_index):
    title_line = '<{change}> on <{version}> of <{title}> topic <{topic}>'.format(
        change=node_obj['name'],
        topic=topic,
        version=info_index['meta']['version_name'],
        title=info_index['meta']['title']
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
    if 'platform' in info_index['meta'] and info_index['meta']['platform']:
        lines.append('Platform ID: <{}>'.format(
            info_index['meta']['platform']))

    lines.append('  ')
    lines.append('  ')

    section_showed = False
    if 'jira_key' in info_index['meta'] and info_index['meta']['jira_key']:
        lines.append('%JR={}'.format(info_index['meta']['jira_key']))
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
                                                     meta=info_index['meta'])
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

        if info_index['etc']['heat_template']:
            if not ric_title:
                lines.append('This integration contains '
                             'following ric conponent(s):')

            lines.append('  - RICCOMMIT <{}> <{}>'.format(
                'open-stack-heat-templates',
                info_index['etc']['heat_template']))

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

    section_showed = False
    if 'attached' in node_obj and not node_obj['attached']:
        lines.append('This change is an isolated change in this integration.')
        section_showed = True

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


def add_structure_string(root_node, integration_node, graph_obj,
                         nodes, gerrit_client):
    structure_dict = {'root': root_node['ticket_id'],
                      'manager': integration_node['ticket_id'],
                      'tickets': []}
    for node in nodes.values():
        if node is not root_node and node is not integration_node and \
                node.get('type') != 'auto_submodule':
            structure_dict['tickets'].append(node['ticket_id'])

    json_result = json.dumps(structure_dict)
    result = 'Tickets-List: {}'.format(json_result)
    gerrit_client.review_ticket(root_node['rest_id'], result)
    # submodule string
    list_s = root_node.get('submodule_list')
    if list_s:
        json_sub_result = json.dumps(list_s)
        sub_result = 'Submodules-List: {}'.format(json_sub_result)
        gerrit_client.review_ticket(root_node['rest_id'], sub_result)


def label_all_tickets(root_node, integration_node, graph_obj,
                      nodes, gerrit_client, zuul_user,
                      zuul_server, zuul_port, zuul_key):
    gerrit_api.review_patch_set(zuul_user, zuul_server,
                                root_node['ticket_id'],
                                ['Integrated=-1'], 'init_label',
                                zuul_key, zuul_port)
    gerrit_client.review_ticket(root_node['rest_id'], 'reintegrate')
    gerrit_client.review_ticket(integration_node['rest_id'], 'reexperiment')
    for node in nodes.values():
        if node is not root_node and node is not integration_node:
            if 'auto_code_reveiw' in node and not node['auto_code_reveiw']:
                pass
            else:
                gerrit_client.review_ticket(node['rest_id'],
                                            'Initial label', {'Code-Review': 2})
                # gerrit_api.review_patch_set(zuul_user, zuul_server,
                #                             node['ticket_id'],
                #                             ['Integrated=0'], 'init_label',
                #                             zuul_key, zuul_port)

        if 'reviewers' in node and node['reviewers']:
            for reviewer in node['reviewers']:
                try:
                    gerrit_client.add_reviewer(node['rest_id'], reviewer)
                except Exception as ex:
                    print('Adding reviwer failed, {}'.format(str(ex)))
        comment_list = node.get('comments')
        if comment_list:
            for comment_str in comment_list:
                gerrit_client.review_ticket(node['rest_id'], comment_str)


def read_ric(ric_path):
    content = None
    with open(ric_path) as f:
        content = f.read()
    return content


def print_result(root_node, integration_node, graph_obj,
                 nodes, gerrit_server):
    root_change = root_node['ticket_id']
    print('Root change: {}'.format('{}/#/c/{}/'.format(
        gerrit_server, root_change)))
    integration_change = integration_node['ticket_id']
    print('Integration change: {}'.format('{}/#/c/{}/'.format(
        gerrit_server, integration_change)))
    component_changes = ''
    print('Component changes:')
    for node in nodes.values():
        if node is not root_node and node is not integration_node:
            node_change = node['ticket_id']
            component_changes += ' {}'.format(node_change)
            print('{}/#/c/{}/'.format(gerrit_server, node_change))
    result_dict = {
        'RootID': root_change,
        'integration': integration_change,
        'component': component_changes
    }
    path = os.path.join(job_tool.get_workspace(), 'result')
    job_tool.write_dict_to_properties(result_dict, path, False)


def create_file_change_by_env_change(env_change, file_content, filename):
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


def _main(path, gerrit_path, topic_prefix, init_ticket, zuul_user, zuul_key,
          input_branch, ric_path, heat_template, version_name, env_change,
          streams, if_restore):
    topic = None
    utc_dt = datetime.utcnow()
    timestr = utc_dt.replace(microsecond=0).isoformat()
    if not topic_prefix:
        topic = 't_{}'.format(timestr)
    else:
        topic = '{}_{}'.format(topic_prefix, timestr)

    topic = slugify(topic)

    structure_obj = load_structure(path)
    gerrit_obj = load_structure(gerrit_path)

    if not version_name and env_change:
        versions = set()
        env_change_split = shlex.split(env_change)
        for line in env_change_split:
            line = line.strip()
            env_list = line.split('=', 2)
            if len(env_list) >= 2:
                versions.add(env_list[1])

        if versions:
            if 'meta' in structure_obj and \
                    'version_keyword' in structure_obj['meta'] and \
                    structure_obj['meta']['version_keyword']:
                vk = structure_obj['meta']['version_keyword']
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

    gerrit_server = gerrit_obj['gerrit']['url']
    gerrit_user = gerrit_obj['gerrit']['user']
    gerrit_pwd = gerrit_obj['gerrit']['pwd']
    gerrit_ssh_server = gerrit_obj['gerrit']['ssh_server']
    gerrit_ssh_port = gerrit_obj['gerrit']['ssh_port']
    gerrit_client = gerrit_rest.GerritRestClient(
        gerrit_server, gerrit_user, gerrit_pwd)

    if gerrit_obj['gerrit']['auth'] == 'basic':
        gerrit_client.change_to_basic_auth()
    elif gerrit_obj['gerrit']['auth'] == 'digest':
        gerrit_client.change_to_digest_auth()

    # handle meta:
    structure_obj['meta']['topic'] = topic
    if not version_name:
        version_name = timestr
    structure_obj['meta']['version_name'] = version_name
    meta = structure_obj['meta']

    # create graph
    root_node, integration_node, nodes, graph_obj = create_graph(structure_obj)
    check_graph_availability(graph_obj, root_node, integration_node)

    info_index = {
        'meta': meta,
        'root': root_node,
        'mn': integration_node,
        'nodes': nodes,
        'graph': graph_obj,
        'etc': {
            'heat_template': heat_template
        }
    }

    # restore
    meta['backup_topic'] = None
    if if_restore:
        if 'platform' in meta and meta['platform']:
            backup_topic = 'integration_{}_backup'.format(meta['platform'])
            meta['backup_topic'] = backup_topic

    stream_list = []
    if streams:
        stream_list = streams.split(',')
    else:
        stream_list = ['default']

    meta['streams'] = stream_list

    # create jira
    if 'jira' in meta:
        try:
            jira_key = create_jira_ticket.run(info_index)
            meta["jira_key"] = jira_key
        except Exception as ex:
            print('Exception occured while create jira ticket, {}'.format(
                str(ex)))

    # If root exists
    if env_change:
        root_node['env_change'] = env_change
        root_node['add_files'] = create_file_change_by_env_change(
            env_change,
            read_file_from_branch(
                root_node, root_node['branch'],
                gerrit_server, gerrit_user, gerrit_pwd, 'env-config.d/ENV'),
            'env-config.d/ENV')
    elif init_ticket:
        try:
            file_list = gerrit_client.get_file_list(init_ticket)
            add_files = {}
            for _file in file_list:
                _file = _file.split('\n', 2)[0]
                if _file != '/COMMIT_MSG':
                    file_content = gerrit_client.get_file_change(
                        _file, init_ticket)
                    if 'new' in file_content \
                            and 'old' in file_content \
                            and file_content['new'] != file_content['old']:
                        add_files[_file] = strip_begin(
                            file_content['new'], 'Subproject commit ')
            root_node['add_files'] = add_files
        except Exception as e:
            print("An exception %s occurred when query init ticket,"
                  " msg: %s" % (type(e), str(e)))

    else:
        env_files, env_commit = read_from_branch(root_node, input_branch,
                                                 gerrit_server,
                                                 gerrit_user, gerrit_pwd)
        root_node['add_files'] = env_files

    # root_node['temp_commit'] = create_temp_branch(
    #     gerrit_client,
    #     root_node['repo'],
    #     root_node['branch'],
    #     'inte_test/{}'.format(topic),
    #     root_node['add_files'])

    if ric_path:
        root_node['ric_content'] = read_ric(ric_path)

    create_ticket_by_graph(root_node, integration_node, graph_obj, nodes,
                           topic, gerrit_client, info_index)
    add_structure_string(root_node, integration_node, graph_obj, nodes,
                         gerrit_client)
    label_all_tickets(root_node, integration_node, graph_obj, nodes,
                      gerrit_client, zuul_user,
                      gerrit_ssh_server, gerrit_ssh_port, zuul_key)
    print_result(root_node, integration_node, graph_obj, nodes, gerrit_server)
    send_result_email.run(info_index)


def read_from_branch(root_node, input_branch, gerrit_server,
                     gerrit_user, gerrit_pwd):
    ret_dict = {}
    commit_id = ''
    repo_url = gerrit_server + '/' + root_node['repo']
    url_slices = repo_url.split('://', 1)
    url_slices[1] = '{}:{}@{}'.format(requests.utils.quote(gerrit_user), requests.utils.quote(gerrit_pwd), url_slices[1])
    repo_url = '://'.join(url_slices)
    folder = file_api.TempFolder('env_tmp_')
    repo = git.Repo.clone_from(repo_url, folder.get_directory())
    origin = repo.remotes.origin
    branch = repo.create_head(input_branch,
                              repo.remotes.origin.refs[input_branch])
    branch.set_tracking_branch(origin.refs.master).checkout()
    commit_id = repo.head.commit.hexsha

    list_dirs = os.walk(folder.get_directory())
    for root, dirs, files in list_dirs:
        if '.git' not in root:
            for f in files:
                if not f.startswith('.git'):
                    file_path = os.path.join(root, f)
                    if os.path.islink(file_path):
                        ret_dict[os.path.relpath(
                            file_path, folder.get_directory())] = \
                            os.readlink(file_path)
                    else:
                        ret_dict[os.path.relpath(
                            file_path, folder.get_directory())] =\
                            open(file_path).read()

    return ret_dict, commit_id


def read_file_from_branch(
        root_node, input_branch, gerrit_server,
        gerrit_user, gerrit_pwd, file_path):
    repo_url = gerrit_server + '/' + root_node['repo']
    url_slices = repo_url.split('://', 1)
    url_slices[1] = '{}:{}@{}'.format(requests.utils.quote(gerrit_user), requests.utils.quote(gerrit_pwd), url_slices[1])
    repo_url = '://'.join(url_slices)
    folder = file_api.TempFolder('env_tmp_')
    repo = git.Repo.clone_from(repo_url, folder.get_directory())
    origin = repo.remotes.origin
    branch = repo.create_head(input_branch,
                              repo.remotes.origin.refs[input_branch])
    branch.set_tracking_branch(origin.refs.master).checkout()

    file_ab_path = os.path.join(
        folder.get_directory(), file_path)
    if os.path.exists(file_ab_path):
        return open(file_ab_path).read()

    raise Exception('Cannot read file {}'.format(file_ab_path))


def create_temp_branch(rest, project_name,
                       base_branch, target_branch, file_changes):
    # delete if exist
    list_branch = rest.list_branches(project_name)
    for branch in list_branch:
        branch['ref'] = strip_begin(branch['ref'], 'refs/heads/')

    for branch in list_branch:
        if branch['ref'] == target_branch:
            rest.delete_branch(project_name, target_branch)
            break
    # create new branch using base branch
    base = None
    for branch in list_branch:
        if branch['ref'] == base_branch:
            base = branch['revision']
            break

    if not base:
        raise Exception(
            'Cannot get revision of base_branch [{}]'.format(base_branch))

    rest.create_branch(project_name, target_branch, base)
    # add files change to branch and merge
    change_id, ticket_id, rest_id = rest.create_ticket(
        project_name, None, target_branch, 'for temp submodule')

    for file, content in file_changes.items():
        rest.add_file_to_change(rest_id, file, content)
    rest.publish_edit(rest_id)

    rest.review_ticket(rest_id,
                       'for temp submodule',
                       {'Code-Review': 2, 'Verified': 1, 'Gatekeeper': 1})
    rest.submit_change(rest_id)

    # get commit of the change
    info = rest.get_commit(rest_id)
    return info['commit']


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
