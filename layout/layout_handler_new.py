#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

"""
For verify the layout file.
"""

import ConfigParser
import argparse
import collections
import copy
import os
import re
import sys
import time
import traceback

import git
import voluptuous
import zuul.layoutvalidator as validator
from ruamel import yaml

__author__ = "HZ 5G SCM Team"
__copyright__ = "Copyright 2008, Nokia"
__credits__ = []
__license__ = "Apache"
__version__ = "1.1.1"
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
        return self.path

    def get_folder(self):
        if self.path is None:
            return None
        return os.path.dirname(os.path.abspath(self.path)) + os.sep


def get_project_node(project, projects):
    for item in projects:
        if 'name' in item and item['name'] == project:
            return item

    return None


def merge_commented_seq(a, b):
    c = yaml.comments.CommentedSeq()
    c.ca.comment = [None, None]
    for item in a:
        c.append(item)
    for item in b:
        c.append(item)
    idx_m = len(a)
    if hasattr(a, 'ca'):
        for k, item in a.ca.items.items():
            c.ca.items[k] = copy.copy(item)
        if a.ca.comment:
            if len(a.ca.comment) > 1 and a.ca.comment[1]:
                c.ca.comment[1] = a.ca.comment[1]
            if a.ca.end:
                if idx_m in c.ca.items:
                    c.ca.items[idx_m][1] = copy.copy(c.ca.items[idx_m][1])
                    c.ca.items[idx_m][1].extend(a.ca.end)
                else:
                    c.ca.items[idx_m] = [None, a.ca.end, None, None]
    if hasattr(b, 'ca'):
        for k, item in b.ca.items.items():
            c.ca.items[k + idx_m] = copy.copy(item)
        if b.ca.comment:
            if len(b.ca.comment) > 1 and b.ca.comment[1]:
                if idx_m not in c.ca.items:
                    c.ca.items[idx_m] = [None, [], None, None]
                if not isinstance(c.ca.items[idx_m][1], collections.Iterable):
                    c.ca.items[idx_m][1] = [c.ca.items[idx_m][1]]
                c.ca.items[idx_m][1] = copy.copy(c.ca.items[idx_m][1])
                c.ca.items[idx_m][1].extend(b.ca.comment[1])

            if b.ca.end:
                c.ca._end = b.ca.end
    return c


def merge_layout(base_dict, merge_dict):
    ret_dict = copy.copy(base_dict)
    ret_project = []
    merge_project = []
    if 'projects' in ret_dict:
        ret_project = [x['name'] for x in ret_dict['projects'] if 'name' in x]
    if 'projects' in merge_dict:
        merge_project = [x['name'] for x in merge_dict['projects'] if 'name' in x]
    overlapped_list = set(ret_project) & set(merge_project)

    for k, v in merge_dict.iteritems():  # k: projects v: name:gnb
        if k in ret_dict:
            if k == 'projects' and overlapped_list:
                to_merge = copy.copy(merge_dict[k])
                to_ret = copy.copy(ret_dict[k])
                to_append = []
                for ol_project in overlapped_list:
                    to_merge_node = get_project_node(ol_project, to_merge)
                    to_ret_node = get_project_node(ol_project, to_ret)
                    ret_one_repo_node = copy.copy(to_ret_node)
                    for key in ret_one_repo_node:  # key: check gate
                        if key != 'name':
                            if key in to_merge_node:
                                ret_one_repo_node[key] = merge_commented_seq(ret_one_repo_node[key], to_merge_node[key])
                    for key in to_merge_node:
                        if key not in ret_one_repo_node:
                            ret_one_repo_node[key] = copy.copy(to_merge_node[key])
                    to_ret.remove(to_ret_node)
                    to_merge.remove(to_merge_node)
                    to_append.append(ret_one_repo_node)

                ret_dict[k] = merge_commented_seq(to_ret, to_merge) + to_append
            else:
                ret_dict[k] = merge_commented_seq(ret_dict[k], merge_dict[k])
        else:
            ret_dict[k] = v
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


def list_job_in_projects(projects_section, pipelines):
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
                if isinstance(v, yaml.comments.CommentedSeq) and k in pipelines:
                    _scan_jobs_recursive(v, ret_list)

    return list(set(ret_list))


def list_job_in_one_repo_by_pipeline(projects_section, pipelines):
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
                if isinstance(v, yaml.comments.CommentedSeq) and k in pipelines:
                    _scan_jobs_recursive(k, v, ret_list)

    for k in ret_list:
        ret_list[k] = list(set(ret_list[k]))

    return ret_list


def check_layout_d_consistency(snippet_list, pipelines):
    new_list = []
    for snippet in snippet_list:
        if not snippet.obj:
            continue

        if 'jobs' not in snippet.obj or not snippet.obj['jobs']:
            list_job = []
        else:
            list_job = [x['name'] for x in snippet.obj['jobs']]

        list_project = []
        if 'projects' in snippet.obj and snippet.obj['projects']:
            list_project = list_job_in_projects(snippet.obj['projects'], pipelines)
        new_list.append({'path': snippet.path,
                         'obj': snippet.obj,
                         'job_list': list_job,
                         'project_list': list_project})

    for snippet in new_list:
        print('Checking [{}]'.format(snippet['path']))
        list_no_matching = set()
        reg_matching = set()
        reg_no_matching = set()
        reg_wildly_matching = []

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
                            reg_wildly_matching.append(
                                [rege, item, snippet_e.get('path')])
                            # is_matched = True
                            # break
                # if is_matched:
                #    break

        if reg_no_matching:
            ex_str = 'Some strings in jobs does not present in projects: \n'
            for item in reg_no_matching:
                ex_str += '{} '.format(item)
            raise Exception(ex_str)

        if reg_wildly_matching:
            ex_str = 'Some strings in "jobs" section in [{}] ' \
                     'may affect other projects: \n'.format(snippet.get('path'))
            for item in reg_wildly_matching:
                ex_str += '[{}] matches [{}] in [{}] \n'.format(
                    item[0], item[1], item[2])
            raise Exception(ex_str)


def check_one_repo_availability(snippet_list, pipelines):
    print('Checking One repo job unique:')
    check_one_repo_job_unique(snippet_list, pipelines)

    print('Checking One repo job filtered:')
    for snippet in snippet_list:
        check_one_repo_job_filtered(snippet, pipelines)
    regex_ok = True

    print('Checking regex availability:')
    for snippet in snippet_list:
        regex_ok = regex_ok and check_regex_availability(snippet)
    if not regex_ok:
        raise Exception('Regex Error Occurred!')


def check_one_repo_job_filtered(snippet, pipelines):
    if 'projects' not in snippet.obj:
        return
    if not snippet.obj['projects']:
        return
    ret_dict = list_job_in_one_repo_by_pipeline(snippet.obj['projects'], pipelines)
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


def check_regex_availability(tree, path=None):
    ret = True
    if isinstance(tree, LayoutSnippet):
        path = tree.path
        tree = tree.obj

    if isinstance(tree, basestring):
        if tree.startswith('^'):
            try:
                re.compile(tree)
            except re.error as e:
                print('Regex [{}] in [{}] is invalid, because {}'.format(tree, path, e))
                ret = False
    elif isinstance(tree, collections.Mapping):
        for k, v in tree.items():
            ret = ret and check_regex_availability(v, path)
    elif isinstance(tree, collections.Iterable):
        for item in tree:
            ret = ret and check_regex_availability(item, path)
    return ret


def check_one_repo_job_unique(snippet_list, pipelines):
    job_list = {}
    for snippet in snippet_list:
        if 'projects' not in snippet.obj:
            continue
        if not snippet.obj['projects']:
            continue
        job_list[snippet.path] = list_job_in_one_repo_by_pipeline(
            snippet.obj['projects'], pipelines)

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
        self.pipelines = []
        self._clear_yaml()
        self._load_all_file()

    def _clear_yaml(self):
        self._yaml['layout'] = None
        self._yaml['layout.d'] = []
        self.pipelines = []

    def _load_all_file(self):
        self._clear_yaml()
        self._yaml['layout'] = LayoutSnippet(self._main_file_path,
                                             yaml.round_trip_load(open(
                                                 self._main_file_path),
                                                 version='1.1'))
        self.pipelines = [x.get('name') for x in self._yaml['layout'].obj.get('pipelines')]
        print('Pipelines:', self.pipelines)
        if os.path.exists(self._layout_d_path):
            # file_list = os.listdir(self._layout_d_path)
            # for file_name in file_list:
            #     path = os.path.join(self._layout_d_path, file_name)
            #     self._yaml['layout.d'].append(
            #         LayoutSnippet(path, yaml.round_trip_load(open(path),
            #                       version='1.1')))
            list_dirs = os.walk(self._layout_d_path)
            for root, dirs, files in list_dirs:
                for f in files:
                    if f.endswith('.yaml') or f.endswith('.yml'):
                        file_path = os.path.join(root, f)
                        if os.path.islink(file_path):
                            fp = os.readlink(file_path)
                        else:
                            fp = open(file_path)
                        self._yaml['layout.d'].append(
                            LayoutSnippet(file_path, yaml.round_trip_load(fp,
                                                                          version='1.1')))
                        fp.close()

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
        ret_dct = copy.copy(self._yaml['layout'].obj)
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

    def combine_with_validation(self, output_path=None, connections=None, pipelines=None):
        #  verify_layout_with_zuul(self._yaml['layout'])
        check_list = self._yaml['layout.d'][:]
        m_layout = self._yaml['layout'].obj
        if ('jobs' in m_layout and m_layout['jobs']) or \
           ('projects' in m_layout and m_layout['projects']):
            check_list.append(self._yaml['layout'])

        jobs = []
        job_filters = {}
        job_filter_duplicate = {}
        error_list = []
        warning_list = []
        for snippet in check_list:
            path = snippet.get_identity()
            folder = snippet.get_folder()
            yaml_ = snippet.obj
            job_list = []

            project_list = yaml_.get('projects')
            if project_list:
                for project_ in project_list:
                    if not project_.get('name'):
                        error_list.append(
                            'Project {} in file {} has no name'.format(
                                project_list.index(project_),
                                path
                            ))
                        continue

            if 'projects' in yaml_ and yaml_['projects']:
                job_list = list_job_in_projects(yaml_['projects'], pipelines)

            jobs.append({'path': path,
                         'folder': folder,
                         'jobs': job_list})
            job_filter_list = yaml_.get('jobs')
            if job_filter_list:
                for filter_ in job_filter_list:
                    if not filter_.get('name'):
                        error_list.append(
                            'Job Filter {} in file {} has no name'.format(
                                job_filter_list.index(filter_),
                                path
                            ))
                        continue

                    if filter_['name'].startswith('^'):
                        try:
                            re.compile(filter_['name'])
                        except re.error as e:
                            error_list.append('Regex [{}] in [{}] is invalid, because {}'.format(filter_['name'], path, e))
                            continue

                    if filter_['name'] in job_filters:
                        # duplicate!
                        if filter_['name'] not in job_filter_duplicate:
                            job_filter_duplicate[filter_['name']] = [job_filters[filter_['name']]['path'], path]
                        else:
                            job_filter_duplicate[filter_['name']].append(path)
                    else:
                        job_filters[filter_['name']] = {'path': path, 'folder': folder, 'name': filter_['name']}

        # job filter can't be duplicated
        if job_filter_duplicate:
            print('Job Filter Duplicated!')
            for k, v in job_filter_duplicate.iteritems():
                print('Filter [{}] appears in:'.format(k))
                for i in v:
                    print(i)
            raise Exception('Job Filter Duplicated')

        # check if all jobs filter are used
        # check if all jobs are only filtered by one string filter and one regular filter
        # check if all jobs filter don't filter job in other folder
        for info in jobs:
            for job in info['jobs']:
                string_filter = None
                regular_filter_list = []
                for fname, filter_ in job_filters.iteritems():
                    if fname == job:
                        string_filter = filter_
                        filter_['used'] = True
                    elif fname.startswith('^'):
                        reg = re.compile(fname)
                        if reg.match(job):
                            filter_['used'] = True
                            regular_filter_list.append(filter_)

                if len(regular_filter_list) > 1:
                    warning_msg = 'Job [{}] in [{}] is filtered by more than one filter, \n'.format(job, info['path'])
                    for regular_filter in regular_filter_list:
                        warning_msg += '\t->[{}] in [{}],\n'.format(
                            regular_filter['name'], regular_filter['path'])
                    warning_list.append(warning_msg)

                if string_filter and string_filter['folder'] != info['folder'] and string_filter['folder'] not in info['folder']:
                    error_list.append('Filter [{}] in [{}] should not affect job [{}] in [{}], because they are not in the same folder'.format(
                        string_filter['name'], string_filter['path'],
                        job, info['path']
                    ))
                if regular_filter_list:
                    for regular_filter in regular_filter_list:
                        if regular_filter and regular_filter['folder'] != info['folder'] and regular_filter['folder'] not in info['folder']:
                            error_list.append('Filter [{}] in [{}] should not affect job [{}] in [{}], because they are not in the same folder'.format(
                                regular_filter['name'], regular_filter['path'],
                                job, info['path']
                            ))

        reg_using = 0
        using = 0
        not_using = 0
        for fname, filter_ in job_filters.iteritems():

            if not filter_.get('used'):
                warning_list.append('Filter [{}] in [{}] is not used!'.format(fname, filter_['path']))
                not_using += 1
            else:
                if fname.startswith('^'):
                    reg_using += 1
                else:
                    using += 1
        print('Not used : Regex used : Used = {}:{}:{}'.format(not_using, reg_using, using))

        if warning_list:
            print('!!!!!!Warning!!!!!!')
            print('!!!!!!Warning!!!!!!')
            print('!!!!!!Warning!!!!!!')
            for warning in warning_list:
                print(warning)
                print('------')

        print("")

        if error_list:
            print('!!!!!!Error occurred!!!!!!')
            print('!!!!!!Error occurred!!!!!!')
            print('!!!!!!Error occurred!!!!!!')
            for error in error_list:
                print(error)
                print('------')
            raise Exception('Verify with error')

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

    args = parser.parse_args()
    return vars(args)


class FakeConnection(object):
    def __init__(self, driver_name):
        self.driver_name = driver_name


def configure_connections(config):
    connections = {}

    for section_name in config.sections():
        con_match = re.match(r'^connection ([\'\"]?)(.*)(\1)$',
                             section_name, re.I)
        if not con_match:
            continue
        con_name = con_match.group(2)
        con_config = dict(config.items(section_name))

        if 'driver' not in con_config:
            raise Exception("No driver specified for connection %s."
                            % con_name)

        con_driver = con_config['driver']

        if con_driver == 'gerrit':
            connections[con_name] = FakeConnection("gerrit")
        elif con_driver == 'smtp':
            connections[con_name] = FakeConnection('smtp')
        elif con_driver == 'sql':
            connections[con_name] = FakeConnection('sql')
        else:
            raise Exception("Unknown driver, %s, for connection %s"
                            % (con_config['driver'], con_name))

    # If the [gerrit] or [smtp] sections still exist, load them in as a
    # connection named 'gerrit' or 'smtp' respectfully

    if 'gerrit' in config.sections():
        if 'gerrit' not in connections:
            connections['gerrit'] = FakeConnection("gerrit")

    if 'smtp' in config.sections():
        if 'smtp' not in connections:
            connections['smtp'] = FakeConnection('smtp')

    return connections


def _main():
    args = _parse_args()
    inpath = args['input_file']
    group = LayoutGroup(inpath)
    outpath = None
    zuulconf = None
    if 'output_file' in args:
        outpath = args['output_file']
    if 'zuul_config' in args:
        zuulconf = args['zuul_config']

    connections = None
    if zuulconf:
        config = ConfigParser.ConfigParser()
        config.read(os.path.expanduser(zuulconf))
        connections = configure_connections(config)

    op = args['operation']

    if op == 'verify':
        check_snip = LayoutSnippet(
            path=inpath,
            obj=yaml.round_trip_load(open(inpath), version='1.1')
        )
        verify_layout_with_zuul(check_snip, connections)
    elif op == 'merge':
        group.combine_with_validation(outpath, connections, pipelines=group.pipelines)
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
