#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
For verify the layout file.
"""

import os
from ruamel import yaml
import sys
import re
import traceback
import voluptuous
import time
import zuul.layoutvalidator as validator
import argparse
import ConfigParser
from copy import deepcopy
import zuul
import zuul.lib.connections
import git


__author__ = "HZ 5G SCM Team"
__copyright__ = "Copyright 2007, Nokia"
__credits__ = []
__license__ = "Apache"
__version__ = "1.0.1"
__maintainer__ = "HZ 5G SCM Team"
__email__ = "5g_hz.scm@nokia.com"
__status__ = "Production"

one_repo_name = 'MN/5G/NB/gnb'


class LayoutNotExistException(Exception):
    pass


class LayoutSnippet(object):
    def __init__(self, path=None, obj=None):
        self.path = path
        self.obj = obj
        if self.obj is None:
            self.load_from_path()

    def load_from_path(self):
        if self.path is None:
            self.obj = None
        else:
            self.obj = yaml.round_trip_load(open(self.path), version='1.1')

    def get_identity(self):
        if self.path is None:
            return str(self.obj)
        else:
            return self.path


def get_project_node(project, projects):
    for item in projects:
        if 'name' in item and item['name'] == project:
            return item

    return None


def merge_layout(base_dict, merge_dict):
    ret_dict = deepcopy(base_dict)
    for k, v in merge_dict.iteritems():
        if k in ret_dict:
            require_one_repo_process = False
            if k == 'projects':
                if get_project_node(one_repo_name, ret_dict[k]) and \
                        get_project_node(one_repo_name, merge_dict[k]):
                    require_one_repo_process = True

            if require_one_repo_process:
                to_merge = deepcopy(merge_dict[k])
                to_ret = deepcopy(ret_dict[k])
                to_merge_node = get_project_node(one_repo_name, to_merge)
                to_ret_node = get_project_node(one_repo_name, to_ret)
                ret_one_repo_node = deepcopy(to_ret_node)
                for key in ret_one_repo_node:
                    if key != 'name':
                        if key in to_merge_node:
                            ret_one_repo_node[key] = \
                                yaml.round_trip_load(
                                    yaml.round_trip_dump(
                                        ret_one_repo_node[key]) +
                                    yaml.round_trip_dump(to_merge_node[key]),
                                    version='1.1')
                for key in to_merge_node:
                    if key not in ret_one_repo_node:
                        ret_one_repo_node[key] = deepcopy(to_merge_node[key])
                to_ret.remove(to_ret_node)
                to_merge.remove(to_merge_node)
                ret_dict[k] = to_ret + to_merge
                ret_dict[k].append(ret_one_repo_node)
            else:
                yaml1 = yaml.round_trip_dump(ret_dict[k])
                yaml2 = yaml.round_trip_dump(merge_dict[k])
                ret_dict[k] = yaml.round_trip_load(
                    yaml1 + '\n' + yaml2, version='1.1')
        else:
            ret_dict[k] = merge_dict[k]
    return ret_dict


def verify_layout_with_zuul(snippet, connections=None):
    try:
        validator.LayoutValidator().validate(snippet.obj, connections)
    except voluptuous.Invalid as ex:
        raise Exception('Unexpected YAML syntax error in [{}]:\n  {}'.format(
            snippet.get_identity(), str(ex)))


def check_layout_d_duplication(snippet_list, section='projects'):
    duplication_list = []
    for i in range(0, len(snippet_list)):
        for j in range(i + 1, len(snippet_list)):
            snippet1 = snippet_list[i]
            snippet2 = snippet_list[j]
            if not snippet1.obj or not snippet2.obj\
                    or section not in snippet1.obj \
                    or section not in snippet2.obj \
                    or not snippet1.obj[section]\
                    or not snippet2.obj[section]:
                continue
            item_list_x = \
                [x['name'] for x in [y for y in snippet1.obj[section]]]

            item_list_y = \
                [x['name'] for x in [y for y in snippet2.obj[section]]]

            duplicate_projects = set(item_list_x) & set(item_list_y)

            for item in duplicate_projects:
                # one repo in projects does not count
                if not (item == one_repo_name and section == 'projects'):
                    duplication_list.append({'project': item,
                                             'file1': snippet1.get_identity(),
                                             'file2': snippet2.get_identity()
                                             })
    if duplication_list:
        ex_str = 'Found duplication in list: \n'
        for item in duplication_list:
            ex_str += 'Section [{}] [{}] duplicates in [{}] and [{}] \n'\
                .format(section, item['project'], item['file1'], item['file2'])
        raise Exception(ex_str)


def list_job_in_projects(projects_section):
    ret_list = []

    def _scan_jobs_recursive(joblist, retlist):
        for item in joblist:
            if isinstance(item, yaml.comments.CommentedMap):
                for k, v in list(item.items()):
                    retlist.append(k)
                    _scan_jobs_recursive(v, retlist)
            else:
                retlist.append(item)

    for item in projects_section:
        if isinstance(item, yaml.comments.CommentedMap):
            for k, v in list(item.items()):
                if isinstance(v, yaml.comments.CommentedSeq):
                    _scan_jobs_recursive(v, ret_list)

    return list(set(ret_list))


def list_job_in_one_repo_by_pipeline(projects_section):
    ret_list = {}

    def _scan_jobs_recursive(pipeline, joblist, ret_list):
        for item in joblist:
            if isinstance(item, yaml.comments.CommentedMap):
                for k, v in list(item.items()):
                    if pipeline not in ret_list:
                        ret_list[pipeline] = []
                    ret_list[pipeline].append(k)
                    _scan_jobs_recursive(pipeline, v, ret_list)
            else:
                if pipeline not in ret_list:
                    ret_list[pipeline] = []
                ret_list[pipeline].append(item)

    for item in projects_section:
        if isinstance(item, yaml.comments.CommentedMap):
            if item['name'] != one_repo_name:
                continue
            for k, v in list(item.items()):
                if isinstance(v, yaml.comments.CommentedSeq):
                    _scan_jobs_recursive(k, v, ret_list)

    for k in ret_list:
        ret_list[k] = list(set(ret_list[k]))

    return ret_list


def check_layout_d_consistency(snippet_list):
    new_list = []
    for snippet in snippet_list:
        if not snippet.obj:
            continue

        if 'jobs' not in snippet.obj or not snippet.obj['jobs']:
            list_job = []
        else:
            list_job = [x['name'] for x in snippet.obj['jobs']]

        if 'projects' not in snippet.obj:
            raise Exception(
                'File [{}] does not contain `projects` section, '
                'which is not permitted.'.format(snippet.get_identity()))

        list_project = list_job_in_projects(snippet.obj['projects'])
        new_list.append({'path': snippet.path,
                         'obj': snippet.obj,
                         'job_list': list_job,
                         'project_list': list_project})

    for snippet in new_list:
        print('Checking [{}]'.format(snippet['path']))
        list_no_matching = set()
        reg_matching = set()
        reg_no_matching = set()
        reg_wildly_matching = set()

        print('Job list is', snippet['job_list'])
        print('Project job list is', snippet['project_list'])

        for item in snippet['job_list']:
            if item not in snippet['project_list']:
                list_no_matching.add(item)

        for rege in list_no_matching:
            try:
                reg = re.compile(rege)
                is_matched = False
                for item in snippet['project_list']:
                    if reg.match(item):
                        reg_matching.add(rege)
                        is_matched = True
                        break
                if not is_matched:
                    reg_no_matching.add(rege)
            except re.error:
                reg_no_matching.add(rege)

        for rege in reg_matching:
            reg = re.compile(rege)
            is_matched = False
            for snippet_e in new_list:
                if snippet is not snippet_e:
                        for item in snippet_e['project_list']:
                            if reg.match(item):
                                reg_wildly_matching.add(rege)
                                is_matched = True
                                break
                if is_matched:
                    break

        if reg_no_matching:
            ex_str = 'Some strings in jobs does not present in projects: \n'
            for item in reg_no_matching:
                ex_str += '{} '.format(item)
            raise Exception(ex_str)

        if reg_wildly_matching:
            ex_str = 'Some strings in jobs may effect other projects: \n'
            for item in reg_wildly_matching:
                ex_str += '{} '.format(item)
            raise Exception(ex_str)


def check_one_repo_availability(snippet_list):
    check_one_repo_job_unique(snippet_list)
    for snippet in snippet_list:
        check_one_repo_job_filtered(snippet)


def check_one_repo_job_filtered(snippet):
    ret_dict = list_job_in_one_repo_by_pipeline(snippet.obj['projects'])
    for pipeline in ret_dict:
        for job in ret_dict[pipeline]:
            job_filtered = False
            for item in snippet.obj['jobs']:
                if item['name'] == job:
                    job_filtered = True
                    break
                reg = re.compile(item['name'])
                if reg.match(job):
                    job_filtered = True
                    break
            if not job_filtered:
                raise Exception('Job [{}] of [{}] of [{}] is not filtered '
                                'in jobs section.'.format(
                                    job, one_repo_name, snippet.path))


def check_one_repo_job_unique(snippet_list):
    job_list = {}
    for snippet in snippet_list:
        job_list[snippet.path] = list_job_in_one_repo_by_pipeline(
            snippet.obj['projects'])

    for i in range(0, len(job_list.keys())):
        for j in range(i + 1, len(job_list.keys())):
            k1 = job_list.keys()[i]
            k2 = job_list.keys()[j]
            for pipeline in job_list[k1]:
                if pipeline in job_list[k2]:
                    for job in job_list[k1][pipeline]:
                        if job in job_list[k2][pipeline]:
                            raise Exception('[{}] and [{}] have the same job '
                                            '[{}] in pipeline [{}] '
                                            'of [{}]'.format(k1, k2, job,
                                                             pipeline,
                                                             one_repo_name))


def archive_layout_file(path):
    if os.path.exists(path):
        if not os.path.isfile(path):
            raise Exception('Layout path is not a file.')
        dir_path = os.path.dirname(path)
        file_name = os.path.basename(path)
        archive_path = os.path.join(dir_path, 'layout_archives/')
        if not os.path.exists(archive_path):
            print('Make directory for archiving: [{}]'.format(archive_path))
            os.makedirs(archive_path)
        os.rename(path, os.path.join(archive_path, '{}.{}'.format(
            file_name, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))))


def get_repo_revision(path):
    try:
        repo = git.Repo(path=path)
        sha = repo.head.object.hexsha
        return sha
    except Exception as ex:
        print(ex)
        return None


class LayoutGroup(object):
    def __init__(self, main_file_path):
        if not os.path.exists(main_file_path):
            raise LayoutNotExistException(
                'File [{}] does not exist.'.format(main_file_path))
        self._main_file_path = main_file_path
        self._layout_d_path = os.path.join(
            os.path.dirname(main_file_path), 'layout.d')
        self._yaml = {}
        self._clear_yaml()
        self._load_all_file()

    def _clear_yaml(self):
        self._yaml['layout'] = None
        self._yaml['layout.d'] = []

    def _load_all_file(self):
        self._clear_yaml()
        self._yaml['layout'] = LayoutSnippet(self._main_file_path,
                                             yaml.round_trip_load(open(
                                                 self._main_file_path),
                                                 version='1.1'))
        if os.path.exists(self._layout_d_path):
            file_list = os.listdir(self._layout_d_path)
            for file_name in file_list:
                path = os.path.join(self._layout_d_path, file_name)
                self._yaml['layout.d'].append(
                    LayoutSnippet(path, yaml.round_trip_load(open(path),
                                  version='1.1')))

    def _set_head_comments(self, snippet):
        obj = snippet.obj
        comment = 'Automatic generated file. Please do not modify.'
        directory_path = os.path.dirname(self._yaml['layout'].path)
        sha = get_repo_revision(directory_path)
        if sha:
            comment += '\n'
            comment += 'Revision: [{}]'.format(sha)
        for item in self._yaml['layout.d']:
            comment += '\n'
            comment += 'Merged: [{}]'.format(item.path)
        obj.yaml_set_start_comment(comment)

    def combine_one(self, snippet):
        return LayoutSnippet(path=snippet.path,
                             obj=merge_layout(
                                 self._yaml['layout'].obj, snippet.obj))

    def combine(self, output_path=None):
        ret_dct = deepcopy(self._yaml['layout'].obj)
        for item in self._yaml['layout.d']:
            if not item.obj:
                continue
            ret_dct = merge_layout(ret_dct, item.obj)
        ret_snippet = LayoutSnippet(path=None, obj=ret_dct)
        self._set_head_comments(ret_snippet)
        if output_path is not None:
            output_directory = os.path.dirname(os.path.abspath(output_path))
            if not os.path.exists(output_directory):
                print('Make dir for output: [{}]'.format(output_directory))
                os.makedirs(output_directory)
            if os.path.exists(output_path):
                archive_layout_file(output_path)
            f = open(output_path, 'w')
            f.write(yaml.dump(ret_dct, Dumper=yaml.RoundTripDumper))
            f.close()
        return ret_snippet

    def combine_with_validation(self, output_path=None, connections=None):
        #  verify_layout_with_zuul(self._yaml['layout'])
        check_list = deepcopy(self._yaml['layout.d'])
        m_layout = self._yaml['layout'].obj
        if ('jobs' in m_layout and m_layout['jobs']) or \
           ('projects' in m_layout and m_layout['projects']):
            check_list.append(self._yaml['layout'])
        check_layout_d_duplication(check_list, 'projects')
        check_layout_d_duplication(check_list, 'jobs')
        check_layout_d_consistency(check_list)
        check_one_repo_availability(check_list)
        for snippet in self._yaml['layout.d']:
            if not snippet.obj:
                continue
            verify_layout_with_zuul(self.combine_one(snippet), connections)

        output_obj = self.combine(output_path)
        verify_layout_with_zuul(output_obj, connections)
        return output_obj.path


def _parse_args():
    parser = argparse.ArgumentParser(description='Handle layout file.')

    subparsers = parser.add_subparsers(title='Operation',
                                       description='Operations to perform',
                                       dest='operation')
    subparsers.add_parser(
        'verify', help='verify a complete layout file')
    parser_merge = subparsers.add_parser(
        'merge', help='merge and verify a layout with layout.d')
    parser_check = subparsers.add_parser(
        'check', help='check a yaml snippet in layout.d')

    parser.add_argument('--zuul-config', '-z', nargs='?',
                        type=str, dest='zuul_config', required=False,
                        help='zuul.conf to verify connections.')

    parser.add_argument('--input-file', '-i', nargs='?',
                        type=str, dest='input_file', required=True,
                        help='path to main layout file')

    parser_merge.add_argument('--output-file', '-o', nargs='?',
                              type=str, dest='output_file', required=False,
                              help='path to place merged layout. '
                                   'If path exists, '
                                   'the old file will be archived.')

    parser_check.add_argument('--input-snippet', '-s', nargs='?',
                              type=str, dest='snippet', required=True,
                              help='path to file to check.')

    args = parser.parse_args()
    return vars(args)


def _main():
    args = _parse_args()
    inpath = args['input_file']
    group = LayoutGroup(inpath)
    outpath = None
    zuulconf = None
    insnip = None
    if 'output_file' in args:
        outpath = args['output_file']
    if 'zuul_config' in args:
        zuulconf = args['zuul_config']
    if 'snippet' in args:
        insnip = args['snippet']

    connections = None
    if zuulconf:
        config = ConfigParser.ConfigParser()
        config.read(os.path.expanduser(zuulconf))
        connections = zuul.lib.connections.configure_connections(config)

    op = args['operation']

    if op == 'verify':
        verify_layout_with_zuul(LayoutSnippet(
            path=inpath,
            obj=yaml.round_trip_load(open(inpath), version='1.1')
        ), connections)
    elif op == 'merge':
        group.combine_with_validation(outpath, connections)
    elif op == 'check':
        check_snip = LayoutSnippet(path=insnip, obj=yaml.round_trip_load(
            open(insnip), version='1.1'))
        check_layout_d_consistency([check_snip])
        check_one_repo_availability([check_snip])
        verify_layout_with_zuul(group.combine_one(check_snip), connections)
    else:
        raise Exception('Unsupport operation: [{}]'.format(op))

    print('All done. No Excepitons.')


if __name__ == '__main__':
    try:
        _main()
        sys.exit(0)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
