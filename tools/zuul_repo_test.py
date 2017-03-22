#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""Test Zuul by adding tickets."""

import traceback
import os
import sys
import git
import yaml
import argparse
import random
import shutil
import copy
from sh import scp, ssh
import arrow
import json


def _parge_gerrit_args(gerrit):
    subparsers = gerrit.add_subparsers(
        title='Gerrit Operation',
        description='Gerrit operation to perform',
        dest='gerrit')

    subparsers.add_parser('abandon',
                          help='to abandon all open tickets')
    subparsers.add_parser('submit',
                          help='to submit all submittable tickets')
    label = subparsers.add_parser('label',
                                  help='to set label to all open tickets')

    label.add_argument('label-name', type=str,
                       help='name of the label you want to set')
    label.add_argument('label-value', type=int,
                       help='value of the label you want to set')


def _parse_args():
    parser = argparse.ArgumentParser(description='make tickets for gerrit '
                                                 'repositories.')

    subparsers = parser.add_subparsers(title='Operation',
                                       description='Operations to perform',
                                       dest='operation')
    subparsers.add_parser('init-config',
                          help='to generate default config to edit')
    subparsers.add_parser('one-module',
                          help='to create tickets within one module')
    subparsers.add_parser('one-repository',
                          help='to create tickets '
                               'within one repository')
    subparsers.add_parser('multiple-repositories',
                          help='to create tickets '
                               'in multiple repositories')

    gerrit = subparsers.add_parser(
        'gerrit', help='to operate in the gerrit tickets')

    _parge_gerrit_args(gerrit)

    parser.add_argument('--count', '-n', default=3, type=int, nargs='?',
                        dest='count',
                        help='set count of tickets to create')
    parser.add_argument('--work-path', '-p', default=os.path.curdir,
                        nargs='?', type=str, dest='work_path',
                        help='set directory to clone the repository')
    parser.add_argument('--config-file', '-c', nargs='?',
                        default=os.path.join(os.path.curdir,
                                             'repo-config.yml'),
                        type=str, dest='config_path',
                        help='set path of config file')
    parser.add_argument('--with-dependency', '-d', action='store_true',
                        dest='with_dependency',
                        help='commit with dependency'
                             '(does not work in one module mode)')

    parser.add_argument('--with-return-code', '-r', nargs='?',
                        dest='return_code_type', type=str, default='none',
                        choices=['pass', 'faulty', 'random', 'none'],
                        help='commit with return code '
                             'which is randomly chosen from 0 and 1')

    parser.add_argument('--reset', '-e', action='store_true',
                        dest='reset',
                        help='perform a reset after each commit')

    parser.add_argument('--multiple-files', '-m', action='store_true',
                        dest='multi_files',
                        help='use multiple files instead of multiple lines')

    args = parser.parse_args()
    return vars(args)


def _append_file(file_path, push_no, commit_no, **kwargs):
    if kwargs['multi_files']:
        path_array = os.path.splitext(file_path)
        file_path = path_array[0] + str(push_no) + path_array[1]
    if not os.path.exists(os.path.dirname(file_path)):
        os.makedirs(os.path.dirname(file_path))
    with open(file_path, 'a') as content:
        content.write('%d.%d %s \n' % (push_no, commit_no, str(arrow.now())))
        if kwargs['return_code_type'] == 'random':
            a = random.randint(0, 2)
            ret_code = 0 if a > 0 else 1
            content.write('%d\n' % ret_code)
        elif kwargs['return_code_type'] == 'pass':
            content.write('0\n')
        elif kwargs['return_code_type'] == 'faulty':
            if kwargs['current_no'] == kwargs['error_no']:
                content.write('1\n')
                print('No %d ticket returns 1' % kwargs['current_no'])
            else:
                content.write('0\n')


def _generate_example_yaml(path):
    data = {
        'gerrit': {
            'server': '0.0.0.0',
            'port': 29418,
            'baseurl': 'http://url.to.gerrit',
            'user': 'user',
            'sshkey': '/path/to/sshkey'
        },

        'repositories': [
            {
                'name': 'TestProjectA',
                'branch': 'master',
                'modules': [
                    'A1/content.txt',
                    'A2/content.txt'
                ]
            }
        ]
    }

    with open(path, 'w') as outfile:
        yaml.dump(data, outfile, default_flow_style=False)
    print('Init config file successfully. File path is %s' % path)
    return


def _create_tickets_for_one_module(**kwargs):
    # randomly choose a module
    repo = random.choice(kwargs['config']['repositories'])
    module = random.choice(repo['modules'])
    gerrit_config = kwargs['config']['gerrit']
    repo_url = 'ssh://%s@%s:%d/%s' % \
               (gerrit_config['user'], gerrit_config['server'],
                gerrit_config['port'], repo['name'])
    branch = repo['branch']
    clone_as = repo['name']

    git_repo = _init_repo(repo_url, branch, clone_as, **kwargs)
    file_path = os.path.join(git_repo.working_dir, module)
    # index = git_repo.index
    revision = git_repo.head.object.hexsha

    push_no = 1
    commit_no = 1

    for i in range(0, kwargs['count']):
        if kwargs['reset']:
            git_repo.head.reset(revision, index=True, working_tree=True)

        _append_file(file_path, push_no, commit_no, **kwargs)
        kwargs['current_no'] += 1

        git_repo.git.add('.')
        git_repo.git.commit(m='%d.%d. create ticket for module %s' %
                              (push_no, commit_no, module))
        commit_no += 1

        # below won't trigger hook
        # index.add(repo.untracked_files)
        # index.commit()
        if kwargs['reset']:
            origin = git_repo.remotes.origin
            info_list = origin.push('HEAD:refs/for/%s' % branch)
            for info in info_list:
                print(info.summary)
            push_no += 1
            commit_no = 1

    if not kwargs['reset']:
        origin = git_repo.remotes.origin
        info_list = origin.push('HEAD:refs/for/%s' % branch)
        for info in info_list:
            print(info.summary)


def _create_tickets_for_one_repo_without_dependency(**kwargs):
    # randomly choose a module
    repo = random.choice(kwargs['config']['repositories'])
    module = random.choice(repo['modules'])
    gerrit_config = kwargs['config']['gerrit']
    repo_url = 'ssh://%s@%s:%d/%s' % \
               (gerrit_config['user'], gerrit_config['server'],
                gerrit_config['port'], repo['name'])
    branch = repo['branch']
    clone_as = repo['name']

    git_repo = _init_repo(repo_url, branch, clone_as, **kwargs)
    file_path = os.path.join(git_repo.working_dir, module)
    revision = git_repo.head.object.hexsha

    push_no = 1
    commit_no = 1

    for i in range(0, kwargs['count']):
        if kwargs['reset']:
            git_repo.head.reset(revision, index=True, working_tree=True)

        module = random.choice(repo['modules'])
        file_path = os.path.join(git_repo.working_dir, module)

        _append_file(file_path, push_no, commit_no, **kwargs)
        kwargs['current_no'] += 1

        git_repo.git.add('.')
        git_repo.git.commit(m='%d.%d. create ticket for repo %s module %s' %
                              (push_no, commit_no, repo['name'], module))
        commit_no += 1

        if kwargs['reset']:
            origin = git_repo.remotes.origin
            info_list = origin.push('HEAD:refs/for/%s' % branch)
            for info in info_list:
                print(info.summary)
            push_no += 1
            commit_no = 1

    if not kwargs['reset']:
        origin = git_repo.remotes.origin
        info_list = origin.push('HEAD:refs/for/%s' % branch)
        for info in info_list:
            print(info.summary)


def _create_tickets_for_repos_without_dependency(**kwargs):
    # randomly choose a module
    repos = []
    gerrit_config = kwargs['config']['gerrit']

    push_no = 1
    commit_no = 1

    for repo_origin in kwargs['config']['repositories']:
        repo = copy.deepcopy(repo_origin)
        repos.append(repo)

        repo['url'] = 'ssh://%s@%s:%d/%s' %\
                      (gerrit_config['user'], gerrit_config['server'],
                       gerrit_config['port'], repo['name'])
        repo['clone_as'] = repo['name']

        repo['git'] = _init_repo(repo['url'], repo['branch'],
                                 repo['clone_as'], **kwargs)

        repo['index'] = repo['git'].index

        repo['revision'] = repo['git'].head.object.hexsha

    for i in range(0, kwargs['count']):
        repo = random.choice(repos)
        module = random.choice(repo['modules'])

        if kwargs['reset']:
            repo['git'].head.reset(repo['revision'],
                                   index=True, working_tree=True)

        file_path = os.path.join(repo['git'].working_dir, module)

        _append_file(file_path, push_no, commit_no, **kwargs)
        kwargs['current_no'] += 1

        repo['git'].git.add('.')
        repo['git'].git.commit(m='%d.%d. create ticket for repo %s module %s' %
                                 (push_no, commit_no, repo['name'], module))
        commit_no += 1

        if kwargs['reset']:
            origin = repo['git'].remotes.origin
            info_list = origin.push('HEAD:refs/for/%s' % repo['branch'])
            for info in info_list:
                print(info.summary)
            push_no += 1
            commit_no = 1

    if not kwargs['reset']:
        for repo in repos:
            origin = repo['git'].remotes.origin
            info_list = origin.push('HEAD:refs/for/%s' % repo['branch'])
            for info in info_list:
                print(info.summary)


def make_repos(type, **kwargs):
    repos = []
    gerrit_config = kwargs['config']['gerrit']

    if type == 'one':
        repo_origin = random.choice(kwargs['config']['repositories'])
        i = 0
        for module in repo_origin['modules']:
            i += 1
            repo = copy.deepcopy(repo_origin)
            repos.append(repo)

            repo['url'] = 'ssh://%s@%s:%d/%s' % \
                          (gerrit_config['user'], gerrit_config['server'],
                           gerrit_config['port'], repo['name'])
            repo['clone_as'] = repo['name'] + str(i)

            repo['git'] = _init_repo(repo['url'], repo['branch'],
                                     repo['clone_as'], **kwargs)
            repo['modules'] = [module]

            repo['index'] = repo['git'].index

            repo['revision'] = repo['git'].head.object.hexsha
    elif type == 'multiple':
        for repo_origin in kwargs['config']['repositories']:
            repo = copy.deepcopy(repo_origin)
            repos.append(repo)

            repo['url'] = 'ssh://%s@%s:%d/%s' % \
                          (gerrit_config['user'], gerrit_config['server'],
                           gerrit_config['port'], repo['name'])
            repo['clone_as'] = repo['name']

            repo['git'] = _init_repo(repo['url'], repo['branch'],
                                     repo['clone_as'], **kwargs)

            repo['index'] = repo['git'].index

            repo['revision'] = repo['git'].head.object.hexsha
    else:
        raise Exception('Not supported type: %s' % type)

    return repos


def get_last_change_id(repo):
    result = ''
    master = repo.head.reference
    msg = master.commit.message
    lines = msg.splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith('Change-Id:'):
            result = line.replace('Change-Id:', '').strip()
    return result


def _create_tickets_for_repos_with_dependency(repos, **kwargs):
    # randomly choose a module
    push_no = 1
    commit_no = 1

    count = kwargs['count']
    if count < 2:
        raise Exception('You must set count greater than 1 to use dependency.')
    while count > 0:
        times = min(random.randint(2, len(repos)), count)
        print('Generate %d tickets with dependency' % times)
        count -= times
        last_change_id = ''
        repo = None
        shuffled_repos = copy.deepcopy(repos)
        random.shuffle(shuffled_repos)

        for i in range(0, times):
            repo = shuffled_repos[i]
            module = random.choice(repo['modules'])

            if kwargs['reset']:
                repo['git'].head.reset(repo['revision'],
                                       index=True, working_tree=True)

            file_path = os.path.join(repo['git'].working_dir, module)

            _append_file(file_path, push_no, commit_no, **kwargs)
            kwargs['current_no'] += 1

            if last_change_id:
                msg = '%d.%d. create ticket for repo %s module %s\n' \
                      'Depends-On: %s' % \
                      (push_no, commit_no, repo['name'],
                       module, last_change_id)
            else:
                msg = '%d.%d. create ticket for repo %s module %s' %\
                      (push_no, commit_no, repo['name'], module)

            print('Commit msg is ', msg)

            repo['git'].git.add('.')
            repo['git'].git.commit(m=msg)
            commit_no += 1
            last_change_id = get_last_change_id(repo['git'])
            print('Commit change id is ', last_change_id)

        if kwargs['reset']:
            for repo in repos:
                origin = repo['git'].remotes.origin
                info_list = origin.push('HEAD:refs/for/%s' % repo['branch'])
                for info in info_list:
                    print(info.summary)
            push_no += 1
            commit_no = 1

    if not kwargs['reset']:
        for repo in repos:
            origin = repo['git'].remotes.origin
            info_list = origin.push('HEAD:refs/for/%s' % repo['branch'])
            for info in info_list:
                print(info.summary)


def _init_repo(repo_url, branch, clone_as, **kwargs):
    _init_ssh(**kwargs)
    package_path = os.path.join(kwargs['work_path'], 'repo')
    if not os.path.exists(package_path):
        os.makedirs(package_path)

    repo_path = os.path.join(package_path, clone_as)
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)
    os.makedirs(repo_path)

    repo = git.Repo.clone_from(repo_url, repo_path, b=branch)
    _init_msg_hook(repo_path, **kwargs)

    return repo


def _init_msg_hook(repo_path, **kwargs):
    scp('-p', '-P', kwargs['config']['gerrit']['port'],
        kwargs['config']['gerrit']['user'] + '@'
        + kwargs['config']['gerrit']['server'] + ':hooks/commit-msg',
        repo_path + '/.git/hooks/')


def _init_ssh(**kwargs):
    ssh_key_path = kwargs['config']['gerrit']['sshkey']
    ssh_key_name = ssh_key_path.replace('/', '-')

    ssh_key_target = os.path.abspath(
        os.path.join(os.path.expanduser("~"), '.ssh', ssh_key_name))

    if not os.path.exists(ssh_key_target):
        shutil.copy2(ssh_key_path, ssh_key_target)
        os.chmod(ssh_key_target, 0600)

    ssh_config = os.path.join(os.path.expanduser("~"), '.ssh', 'config')
    if not os.path.exists(ssh_config):
        f = open(ssh_config, 'w')
        f.close()
        os.chmod(ssh_config, 0600)

    with open(ssh_config, 'r+') as f:
        lines = f.read()
        if ssh_key_target not in lines:
            lines += 'Host %s\n' % kwargs['config']['gerrit']['server']
            lines += '    HostName %s\n' % kwargs['config']['gerrit']['server']
            lines += '    PreferredAuthentications publickey\n'
            lines += '    IdentityFile %s\n' % ssh_key_target
            f.seek(0)
            f.write(lines)
            f.truncate()
    pass


def query_gerrit_tickets(type, **kwargs):
    result = ssh('-p', kwargs['config']['gerrit']['port'],
                 kwargs['config']['gerrit']['user'] + '@'
                 + kwargs['config']['gerrit']['server'],
                 'gerrit query '
                 '--format=JSON '
                 'status:%s ' % type)
    print (result)
    return_array = []
    for line in result:
        json_dict = json.loads(line)
        if 'rowCount' not in json_dict:
            return_array.append(json_dict)

    return return_array


def abandon_tickets(**kwargs):
    tickets = query_gerrit_tickets('open', **kwargs)
    for ticket in tickets:
        result = ssh('-p', kwargs['config']['gerrit']['port'],
                     kwargs['config']['gerrit']['user'] + '@'
                     + kwargs['config']['gerrit']['server'],
                     'gerrit review --abandon %s,1' % ticket['number'])
        print result


def submit_tickets(**kwargs):
    tickets = query_gerrit_tickets('open', **kwargs)
    for ticket in tickets:
        result = ssh('-p', kwargs['config']['gerrit']['port'],
                     kwargs['config']['gerrit']['user'] + '@'
                     + kwargs['config']['gerrit']['server'],
                     'gerrit review --submit %s,1' % ticket['number'])
        print result


def set_label_to_tickets(label, value, **kwargs):
    tickets = query_gerrit_tickets('open', **kwargs)
    for ticket in tickets:
        print ticket
        result = ssh('-p', kwargs['config']['gerrit']['port'],
                     kwargs['config']['gerrit']['user'] + '@'
                     + kwargs['config']['gerrit']['server'],
                     'gerrit review --label %s=%d %s,1'
                     % (label, value, ticket['number']))
        print result


def _main(**kwargs):
    if kwargs['operation'] == 'init-config':
        _generate_example_yaml(kwargs['config_path'])
        return

    with open(kwargs['config_path'], 'r') as config_file:
        kwargs['config'] = yaml.load(config_file)

    if kwargs['operation'] == 'one-module':
        _create_tickets_for_one_module(**kwargs)
    elif kwargs['operation'] == 'one-repository':
        if kwargs['with_dependency']:
            _create_tickets_for_repos_with_dependency(
                make_repos('one', **kwargs), **kwargs)
        else:
            _create_tickets_for_one_repo_without_dependency(**kwargs)

    elif kwargs['operation'] == 'multiple-repositories':
        if kwargs['with_dependency']:
            _create_tickets_for_repos_with_dependency(
                make_repos('multiple', **kwargs), **kwargs)
        else:
            _create_tickets_for_repos_without_dependency(**kwargs)

    elif kwargs['operation'] == 'gerrit':
        gerrit_op = kwargs['gerrit']
        if gerrit_op == 'abandon':
            abandon_tickets(**kwargs)
        elif gerrit_op == 'submit':
            submit_tickets(**kwargs)
        elif gerrit_op == 'label':
            label = kwargs['label-name']
            value = kwargs['label-value']
            set_label_to_tickets(label, value, **kwargs)
    # print('The parameters are: ')
    # print(json.dumps(kwargs, indent=2))


if __name__ == '__main__':
    try:
        os.environ['GIT_PYTHON_TRACE'] = 'full'
        params = _parse_args()
        if params['return_code_type'] == 'faulty':
            params['error_no'] = random.randint(1, params['count']-1)
            print('No %d ticket will return 1' % params['error_no'])
        params['current_no'] = 1
        _main(**params)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
