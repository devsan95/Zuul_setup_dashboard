#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import argparse
import sys
import traceback
from api.jenkins_api import JenkinsRest
from api.xml_tools import XmlParser


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Set the slave you want the job run on')

    parser.add_argument('--slave', type=str, dest='slave',
                        help='slave name')
    parser.add_argument('--job', type=str, dest='job',
                        help='job name')
    parser.add_argument('--user', type=str, dest='user',
                        help='user name of jenkins')
    parser.add_argument('--pwd', type=str, dest='password',
                        help='http password of the jenkins user')
    parser.add_argument('--url', type=str, dest='url',
                        help='jenkins server url')

    ar = parser.parse_args()
    return vars(ar)


def set_slave(job, slave, user, password, url):
    jenkins = JenkinsRest(url, user, password)
    config = jenkins.get_job_config(job)
    # transfer unicode to string
    config = config.encode('utf-8')

    # jenkins.set_node(job, slave)
    print(config)
    xml = XmlParser(config)
    all_elements = xml.get_all_elements()
    print(all_elements)
    if "assignedNode" in all_elements:
        # if the job already assigned a slave,
        # print it and change to the new
        xml.set_tag_text("assignedNode", slave)
        rs = xml.root_to_string()
        completed_str = '''<?xml version='1.1' encoding='UTF-8'?>\n''' + rs
        print completed_str

        jenkins.update_job("test", completed_str)


def _main(**kwargs):
    job = kwargs['job']
    slave = kwargs['slave']
    user = kwargs['user']
    password = kwargs['password']
    url = kwargs['url']
    set_slave(job, slave, user, password, url)


if __name__ == '__main__':
    try:
        args = _parse_args()

        _main(**args)

    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
