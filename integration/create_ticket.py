#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import traceback
import sys
import argparse
import ruamel.yaml as yaml
import networkx as nx
from datetime import datetime
import json
import git
import os
from api import gerrit_rest
from api import gerrit_api
from api import file_api
from api import job_tool
from slugify import slugify


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
                        help='initial ticket')

    parser.add_argument('--zuul-user', type=str, dest='zuul_user',
                        help='')

    parser.add_argument('--zuul-key', type=str, dest='zuul_key',
                        help='')

    parser.add_argument('--input-branch', type=str, dest='input_branch',
                        help='')

    parser.add_argument('--ric-file', type=str, dest='ric_path',
                        help='')

    args = parser.parse_args()
    return vars(args)


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


def create_ticket_by_graph(root_node, integration_node, graph_obj, nodes,
                           topic, gerrit_client):
    create_ticket_by_node(root_node, topic, graph_obj, nodes, root_node,
                          gerrit_client)


def create_ticket_by_node(node_obj, topic, graph_obj, nodes, root_node,
                          gerrit_client):
    if 'change_id' not in node_obj or not node_obj['change_id']:
        for edge in graph_obj.in_edges(node_obj['name']):
            depend = edge[0]
            if 'change_id' not in nodes[depend] or \
                    not nodes[depend]['change_id']:
                return
        message = make_description_by_node(node_obj, nodes, graph_obj, topic)
        change_id, ticket_id, rest_id = gerrit_client.create_ticket(
            node_obj['repo'], None, node_obj['branch'], message
        )
        node_obj['change_id'] = change_id
        node_obj['ticket_id'] = ticket_id
        node_obj['rest_id'] = rest_id

    need_publish = False

    # add files to trigger jobs
    if 'files' in node_obj and node_obj['files']:
        if 'file_path' not in node_obj or not node_obj['file_path']:
            file_paths = []
            for _file in node_obj['files']:
                file_path = _file + slugify(topic)
                file_paths.append(file_path)
                gerrit_client.add_file_to_change(node_obj['rest_id'],
                                                 file_path,
                                                 datetime.utcnow().
                                                 strftime('%Y%m%d%H%M%S'))
                need_publish = True
            node_obj['file_path'] = file_paths

    # add files for env
    if 'add_files' in node_obj and node_obj['add_files']:
        for filename, content in node_obj['add_files'].items():
            gerrit_client.add_file_to_change(node_obj['rest_id'],
                                             filename, content)
            need_publish = True

    # add files for submodule
    if 'submodules' in node_obj and node_obj['submodules']:
        for path, repo in node_obj['submodules'].items():
            if repo in nodes and 'temp_commit' in nodes[repo] and \
                    nodes[repo]['temp_commit']:
                gerrit_client.add_file_to_change(
                    node_obj['rest_id'], path, '{}'.format(
                        nodes[repo]['temp_commit']))
                need_publish = True

    if 'type' in node_obj and node_obj['type'] == 'ric':
        gerrit_client.add_file_to_change(node_obj['rest_id'], 'ric',
                                         '{}'.format(root_node['ric_content']))
        need_publish = True

    if need_publish:
        gerrit_client.publish_edit(node_obj['rest_id'])

    for child in graph_obj.successors(node_obj['name']):
        create_ticket_by_node(nodes[child], topic, graph_obj, nodes, root_node,
                              gerrit_client)


def make_description_by_node(node_obj, nodes, graph_obj, topic):
    lines = ['Project <{}> Integration For <{}>'.format(
        node_obj['name'], topic)]

    if 'type' in node_obj:
        if node_obj['type'] == 'root':
            lines.append('ROOT CHANGE')
            lines.append('Please do not modify this change.')
        elif node_obj['type'] == 'integration':
            lines.append('MANAGER CHANGE')
            lines.append('Please do not modify this change.')
    if 'submodules' in node_obj and node_obj['submodules']:
        lines.append('SUBMODULES PLACEHOLDER CHANGE')
        lines.append('Please do not modify this change.')

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
        lines.append('Remarks: {}'.format(node_obj['remark']))
        section_showed = True

    if section_showed:
        lines.append('  ')
        lines.append('  ')

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
                            lines.append('  - RIC <{}> <{}>'.format(
                                ric, node['repo']))

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
    if len(list(graph_obj.predecessors(node_obj['name']))) > 0:
        lines.append('This change depends on following change(s):')
        section_showed = True
        for depend in graph_obj.predecessors(node_obj['name']):
            if depend in nodes and 'ticket_id' in nodes[depend] and \
                    nodes[depend]['ticket_id']:
                lines.append('  - Project:<{}> Change:<{}>'.format(
                    depend, nodes[depend]['ticket_id']))

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
        if node is not root_node and node is not integration_node:
            structure_dict['tickets'].append(node['ticket_id'])

    json_result = json.dumps(structure_dict)
    result = 'Tickets-List: {}'.format(json_result)
    gerrit_client.review_ticket(root_node['rest_id'], result)


def label_all_tickets(root_node, integration_node, graph_obj,
                      nodes, gerrit_client, zuul_user,
                      zuul_server, zuul_port, zuul_key, reviewers):
    gerrit_api.review_patch_set(zuul_user, zuul_server,
                                root_node['ticket_id'],
                                ['Integrated=-1'], 'init label',
                                zuul_key, zuul_port)
    for node in nodes.values():
        if node is not root_node and node is not integration_node:
            gerrit_client.review_ticket(node['rest_id'],
                                        'Initial label', {'Code-Review': 2})
            # gerrit_api.review_patch_set(zuul_user, zuul_server,
            #                             node['ticket_id'],
            #                             ['Integrated=0'], 'init label',
            #                             zuul_key, zuul_port)
    if len(reviewers) > 0:
        for node in nodes.values():
            if node is not root_node and node is not integration_node:
                for reviewer in reviewers:
                    try:
                        gerrit_client.add_reviewer(node['rest_id'], reviewer)
                    except Exception as ex:
                        print(str(ex))


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
        'root': root_change,
        'integration': integration_change,
        'component': component_changes
    }
    path = os.path.join(job_tool.get_workspace(), 'result')
    job_tool.write_dict_to_properties(result_dict, path)


def _main(path, gerrit_path, topic_prefix, init_ticket, zuul_user, zuul_key,
          input_branch, ric_path):
    topic = None
    utc_dt = datetime.utcnow()
    timestr = utc_dt.replace(microsecond=0).isoformat()
    if not topic_prefix:
        topic = 'integration_{}'.format(timestr)
    else:
        topic = '{}_{}'.format(topic_prefix, timestr)

    structure_obj = load_structure(path)
    gerrit_obj = load_structure(gerrit_path)
    gerrit_server = gerrit_obj['gerrit']['url']
    gerrit_user = gerrit_obj['gerrit']['user']
    gerrit_pwd = gerrit_obj['gerrit']['pwd']
    gerrit_ssh_server = gerrit_obj['gerrit']['ssh_server']
    gerrit_ssh_port = gerrit_obj['gerrit']['ssh_port']
    gerrit_client = gerrit_rest.GerritRestClient(
        gerrit_server, gerrit_user, gerrit_pwd)

    reviewers = []
    if 'reviewers' in gerrit_obj and gerrit_obj['reviewers']:
        reviewers = gerrit_obj['reviewers']

    if gerrit_obj['gerrit']['auth'] == 'basic':
        gerrit_client.change_to_basic_auth()
    elif gerrit_obj['gerrit']['auth'] == 'digest':
        gerrit_client.change_to_digest_auth()

    root_node, integration_node, nodes, graph_obj = create_graph(structure_obj)
    check_graph_availability(graph_obj, root_node, integration_node)

    if init_ticket:
        try:
            info = gerrit_client.query_ticket(init_ticket)
            root_node['change_id'] = info['change_id']
            root_node['ticket_id'] = info['_number']
            root_node['rest_id'] = info['id']
        except Exception as e:
            print("An exception %s occurred when query init ticket,"
                  " msg: %s" % (type(e), str(e)))

    env_files, env_commit = read_from_branch(root_node, input_branch,
                                             gerrit_server,
                                             gerrit_user, gerrit_pwd)
    root_node['add_files'] = env_files
    root_node['temp_commit'] = env_commit
    root_node['ric_content'] = read_ric(ric_path)

    create_ticket_by_graph(root_node, integration_node, graph_obj, nodes,
                           topic, gerrit_client)
    add_structure_string(root_node, integration_node, graph_obj, nodes,
                         gerrit_client)
    label_all_tickets(root_node, integration_node, graph_obj, nodes,
                      gerrit_client, zuul_user,
                      gerrit_ssh_server, gerrit_ssh_port, zuul_key, reviewers)
    print_result(root_node, integration_node, graph_obj, nodes, gerrit_server)


def read_from_branch(root_node, input_branch, gerrit_server,
                     gerrit_user, gerrit_pwd):
    ret_dict = {}
    commit_id = ''
    repo_url = gerrit_server + '/' + root_node['repo']
    url_slices = repo_url.split('://', 1)
    url_slices[1] = '{}:{}@{}'.format(gerrit_user, gerrit_pwd, url_slices[1])
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


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
