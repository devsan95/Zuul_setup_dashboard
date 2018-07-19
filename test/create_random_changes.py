#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

from __future__ import print_function

import collections
import os
import random
import string
import time
import uuid

import fire
import yaml

from api import gerrit_rest


def is_iterable(obj):
    return isinstance(obj, collections.Iterable)


def process_conf(conf, repos, branches):
    if repos:
        set_a = set(conf['repos'].keys())
        set_b = set(repos)
        set_c = set_a & set_b
        conf['valid_repos'] = list(set_c)
    else:
        conf['valid_repos'] = conf['repos'].keys()
    if branches:
        for repo, node in conf['repos'].items():
            branch_node = node['branches']
            set_a = set(branch_node.keys())
            set_b = set(branches)
            set_c = set_a & set_b
            node['valid_branches'] = list(set_c)
    else:
        for repo, node in conf['repos'].items():
            branch_node = node['branches']
            node['valid_branches'] = branch_node.keys()


def random_path(folders):
    folder = random.choice(folders)
    file_name = str(uuid.uuid4())
    path = os.path.join(folder, file_name)
    return path


def create_change(rest, conf, current_no, total_no, topic,
                  file_numbers, module_numbers, depends_on):
    repo = random.choice(conf['valid_repos'])
    repo_node = conf['repos'][repo]
    branch = random.choice(repo_node['valid_branches'])
    branch_node = repo_node['branches'][branch]
    folders = branch_node['folders']
    message = '{} ({}/{})'.format(topic, current_no, total_no)
    dependency = conf.get('created_change_id')
    if depends_on and dependency:
        message = '{}\nDependency\n{}'.format(
            message,
            '\n'.join(['Depends-on: {}'.format(x) for x in dependency]))
    change_id, change_no, rest_id = rest.create_ticket(repo, '', branch,
                                                       message)

    if 'created_change_id' not in conf:
        conf['created_change_id'] = []
    conf['created_change_id'].append(change_id)

    need_publish = False
    modules = [random.choice(folders) for _ in range(module_numbers)]
    print('Selected modules are {}'.format(modules))
    for i in range(0, file_numbers):
        path = random_path(modules)
        rest.add_file_to_change(change_no, path, path)
        need_publish = True

    if need_publish:
        rest.publish_edit(change_no)

    return change_no, change_id


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def run(gerrit_conf, change_conf, change_numbers,
        change_interval=0, file_numbers=0, module_numbers=1, depends_on=False,
        repos=None, branches=None, code_review=False):
    rest = gerrit_rest.init_from_yaml(gerrit_conf)
    with open(change_conf) as f:
        conf = yaml.load(f)

    if repos:
        if isinstance(repos, basestring):
            repos = [repos]
    if branches:
        if isinstance(branches, basestring):
            branches = [branches]

    process_conf(conf, repos, branches)
    topic = id_generator()
    print('Current topic is {}'.format(topic))

    for i in range(0, change_numbers):
        try:
            change_no, change_id = create_change(
                rest, conf, i + 1,
                change_numbers, topic, file_numbers,
                module_numbers, depends_on)

            print('Change created, {}'.format(rest.get_change_address(change_no)))
            if code_review:
                rest.review_ticket(change_no, 'auto code review',
                                   {'Code-Review': 2})
                print('Code-Reivew+2')
        except Exception as e:
            print('Exception \n{}'.format(e))
        if change_interval > 0:
            print('Sleep for {}'.format(change_interval))
            time.sleep(change_interval)


if __name__ == '__main__':
    fire.Fire(run)
