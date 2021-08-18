#!/usr/bin/env python
# -*- coding:utf8 -*-
import os
import sys
import re
import argparse
import paramiko
import time
import logging
import jenkins
import requests
from bs4 import BeautifulSoup


jenkins_server = 'http://production-5g.cb.scm.nsn-rdnet.net:80/'
label_path = 'label/{}'
ip_rex = re.compile(r'10\.\d+\.\d+\.\d+')
id_rex = re.compile(r'-(\d+)_\d$')
cmd = '''
set -x
service_file="/etc/systemd/system/jenkins-docker.service";
sed -i 's/cbbuild:[0-9]*.[0-9]*.[0-9]*-*.*$/cbbuild:%s"/' ${service_file};
eval "$(awk -F '=' '/docker pull/{print $2}' ${service_file})"
systemctl stop jenkins-docker.service;
systemctl daemon-reload;
while docker ps -a|grep 'cbbuild' >/dev/null;do sleep 3s;done;
systemctl start jenkins-docker.service;
until docker ps -a|grep 'cbbuild' >/dev/null;do sleep 3s;done;
echo ok;

'''


def update_containner_node(node, ver):
    private = paramiko.RSAKey.from_private_key_file(
        '{}/.ssh/{}'.format(
            os.path.expanduser('~'),
            node['key']
        )
    )
    client.connect(
        hostname=node['ip'],
        port=22,
        username='root',
        pkey=private
    )
    _, output, error = client.exec_command(cmd % (ver))
    log.debug("cmd output: {}".format(str(output.read())))
    log.debug("cmd error: {}".format(str(error.read())))
    online_node(node)
    log.info('Node {} update ok'.format(node['name']))
    return True


def process_node():
    while True:
        if not node_info_list:
            break
        log.info(
            "There are still {} nodes unprocessed".format(
                len(node_info_list)
            )
        )
        for node in node_info_list:
            log.info('process node {}'.format(node['name']))
            if not server.get_node_info(node['name'])['offline']:
                server.disable_node(node['name'])
            if server.get_node_info(node['name'])['idle']:
                if args.type == 'container':
                    if update_containner_node(node, args.version):
                        node_info_list.remove(node)
                elif args.type == "instance":
                    if update_instance_node(node):
                        node_info_list.remove(node)
                else:
                    log.error(
                        'Not support type {}'.format(args.type)
                    )
            else:
                time.sleep(10)


def update_instance_node(node):
    try:
        server.delete_node(node['name'])
        log.info('node {} delete finish'.format(node['name']))
        return True
    except Exception:
        log.error(
            "node {} delete failed, pass".format(
                node['name']
            )
        )
        return True


def online_node(node):
    while True:
        try:
            server.enable_node(node['name'])
            log.info("enable node {} finish".format(node['name']))
            break
        except Exception:
            log.warning(
                "enable node {} failed, try again".format(
                    node['name']
                )
            )
            time.sleep(3)


def setup_logger(debug="False"):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s:\t%(module)s@%(lineno)s:\t%(message)s'
    )
    ch = logging.StreamHandler()
    if debug.lower() == "true":
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.WARNING)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


def arguments():
    parse = argparse.ArgumentParser()
    parse.add_argument(
        '--label',
        '-l',
        required=False,
        help="--jenkins node label"
    )
    parse.add_argument(
        '--node',
        '-n',
        required=False,
        help="--receiver mail list"
    )
    parse.add_argument(
        '--type',
        '-t',
        required=True,
        help="--node type:instance or container"
    )
    parse.add_argument(
        '--version',
        '-v',
        required=False,
        help="--containner version"
    )
    parse.add_argument(
        '--user',
        '-u',
        required=True,
        help="--user"
    )
    parse.add_argument(
        '--passwd',
        '-p',
        required=True,
        help="--password"
    )
    return parse.parse_args()


def get_node_from_html():
    label_node = list()
    response = requests.get(
        os.path.join(
            jenkins_server,
            label_path.format(args.label)
        )
    )
    if response.ok:
        log.info("get node from label {}".format(args.label))
        soup = BeautifulSoup(response.text, 'html.parser')
        for nobr in soup.find_all('nobr'):
            label_node.append(
                nobr.find(
                    "a",
                    class_="model-link inside"
                ).get_text()
            )
    return label_node


def get_node_list():
    if args.label:
        node_list = get_node_from_html()
    elif args.node:
        node_list = args.node.split(',')
    else:
        log.error("Please provide label or node argument.")
        sys.exit(1)
    log.info(node_list)
    return node_list


def get_node_info():
    nodes_info = list()
    for node in nodes:
        node_info = dict()
        node = node.strip()
        node_info['name'] = node
        if not node:
            continue
        if ip_rex.match(node):
            log.warnning("{}, not support ip".format(node))
            continue
        response = requests.get(
            '{}/computer/{}/'.format(
                jenkins_server,
                node
            )
        )
        if not response.ok:
            log.error('can not get node {}'.format(node))
            continue
        node_html = BeautifulSoup(response.text, 'html.parser')
        node_table = node_html.find(
            'table',
            attrs={'class': "pane bigtable"}
        )
        if not node_table:
            log.error("{} may be not a cloud instance".format(node))
            continue
        for tr in node_table.find_all('tr'):
            if tr.th.text == 'Server Id':
                node_info['id'] = tr.td.text.strip()
            if tr.th.text == 'Availability Zone':
                try:
                    tdid = id_rex.findall(tr.td.text.strip())[0]
                except Exception:
                    log.error("The cloud {} not support.".format(
                        tr.td.text.strip()
                    ))
                    break
                node_info['cloud'] = 'cloud_{}'.format(tdid)
                node_info['key'] = 'ca-5gcv-key-{}.pem'.format(tdid)
            if tr.th.text == "Addresses":
                try:
                    node_info['ip'] = ip_rex.findall(
                        tr.td.text.strip()
                    )[0]
                except Exception:
                    log.error("can not find {}'s ip.".format(node))
                    break
        else:
            log.info(node_info)
            nodes_info.append(node_info)
    return nodes_info


if __name__ == "__main__":
    args = arguments()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    server = jenkins.Jenkins(
        jenkins_server,
        username=args.user,
        password=args.passwd
    )
    log = setup_logger(debug="True")
    nodes = get_node_list()
    node_info_list = get_node_info()
    log.debug(node_info_list)
    process_node()
    log.info("all node process finish.")
