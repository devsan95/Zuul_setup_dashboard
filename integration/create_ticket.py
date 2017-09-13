#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import traceback
import sys
import argparse
import ruamel.yaml as yaml
import networkx as nx
from datetime import datetime
import json
from api import gerrit_rest
from api import gerrit_api
from slugify import slugify


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Create ticket according to structure file')
    parser.add_argument('path', type=str,
                        help='path to structure file')

    parser.add_argument('--topic-suffix', type=str, dest='topic_suffix',
                        help='topic suffix')

    parser.add_argument('--init-ticket', type=str, dest='init_ticket',
                        help='initial ticket')

    parser.add_argument('--zuul-user', type=str, dest='zuul_user',
                        help='')

    parser.add_argument('--zuul-key', type=str, dest='zuul_key',
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
    create_ticket_by_node(root_node, topic, graph_obj, nodes, gerrit_client)


def create_ticket_by_node(node_obj, topic, graph_obj, nodes, gerrit_client):
    if 'change_id' not in node_obj or not node_obj['change_id']:
        for edge in graph_obj.in_edges(node_obj['name']):
            depend = edge[0]
            if 'change_id' not in nodes[depend] or \
                    not nodes[depend]['change_id']:
                return
        message = make_description_by_node(node_obj, nodes, graph_obj)
        change_id, ticket_id, rest_id = gerrit_client.create_ticket(
            node_obj['repo'], topic, node_obj['branch'], message
        )
        node_obj['change_id'] = change_id
        node_obj['ticket_id'] = ticket_id
        node_obj['rest_id'] = rest_id

    if 'file' in node_obj and node_obj['file']:
        if 'file_path' not in node_obj or not node_obj['file_path']:
            file_path = node_obj['file'] + slugify(topic)
            gerrit_client.add_file_to_change(node_obj['rest_id'],
                                             file_path,
                                             datetime.utcnow().
                                             strftime('%Y%m%d%H%M%S'))
            gerrit_client.publish_edit(node_obj['rest_id'])
            node_obj['file_path'] = file_path

    for child in graph_obj.successors(node_obj['name']):
        create_ticket_by_node(nodes[child], topic, graph_obj, nodes,
                              gerrit_client)


def make_description_by_node(node_obj, nodes, graph_obj):
    lines = ['This is the ticket for integration of '
             'project {}'.format(node_obj['name'])]
    if 'type' in node_obj:
        if node_obj['type'] == 'root':
            lines.append('ROOT CHANGE of one integration process')
        elif node_obj['type'] == 'integration':
            lines.append('MANAGER CHANGE of one integration process\n'
                         'Please do not modify this change.')
    if 'path' in node_obj and node_obj['path']:
        lines.append('Please only modify files '
                     'under the path [<project root>/{}]'.format(
                          node_obj['path']))
    if 'remark' in node_obj and node_obj['remark']:
        lines.append('Remarks: {}'.format(node_obj['remark']))
    for depend in graph_obj.predecessors(node_obj['name']):
        if depend in nodes and 'change_id' in nodes[depend] and \
                nodes[depend]['change_id']:
            lines.append('Depends-on: {}'.format(
                nodes[depend]['change_id']))

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
                      zuul_server, zuul_port, zuul_key):
    gerrit_api.review_patch_set(zuul_user, zuul_server,
                                root_node['ticket_id'],
                                ['Integrated=-1'], 'init label',
                                zuul_key, zuul_port)
    for node in nodes.values():
        if node is not root_node and node is not integration_node:
            gerrit_client.review_ticket(node['rest_id'],
                                        'Initial label', {'Code-Review': 2})
            gerrit_api.review_patch_set(zuul_user, zuul_server,
                                        node['ticket_id'],
                                        ['Integrated=-1'], 'init label',
                                        zuul_key, zuul_port)


def _main(path, topic_suffix, init_ticket, zuul_user, zuul_key):
    topic = None
    utc_dt = datetime.utcnow()
    timestr = utc_dt.replace(microsecond=0).isoformat()
    if not topic_suffix:
        topic = 'integration_{}'.format(timestr)
    else:
        topic = 'integration_{}'.format(topic_suffix)

    structure_obj = load_structure(path)
    gerrit_server = structure_obj['gerrit']['url']
    gerrit_user = structure_obj['gerrit']['user']
    gerrit_pwd = structure_obj['gerrit']['pwd']
    gerrit_ssh_server = structure_obj['gerrit']['ssh_server']
    gerrit_ssh_port = structure_obj['gerrit']['ssh_port']
    gerrit_client = gerrit_rest.GerritRestClient(
        gerrit_server, gerrit_user, gerrit_pwd)
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

    create_ticket_by_graph(root_node, integration_node, graph_obj, nodes,
                           topic, gerrit_client)
    add_structure_string(root_node, integration_node, graph_obj, nodes,
                         gerrit_client)
    label_all_tickets(root_node, integration_node, graph_obj, nodes,
                      gerrit_client, zuul_user,
                      gerrit_ssh_server, gerrit_ssh_port, zuul_key)


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
