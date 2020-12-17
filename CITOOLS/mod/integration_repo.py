#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""A Class to do operations on Integration WorkSpace"""

import os
import re
import sys
import git
import shutil
import logging
import tarfile
import subprocess

from mod import utils

ERR_MSG_LIST = [
    "ERROR: Nothing PROVIDES \'(.*?)\'",
    "ERROR: Nothing RPROVIDES \'(.*?)\'",
    "ERROR: Multiple versions of (.*?) are",
    "ERROR: (.*?) ",
    "error: (.*?) ",
]
BBFILE_EXT = "-99.bb"
RESERVED_KEYS = ['repo_ver',
                 'repo_url',
                 'platform',
                 'bb_ver',
                 'string_replace',
                 'patch',
                 'parent']

logging.basicConfig(level=logging.INFO)
VERSION_REGEX = [r'-[a-z0-9]{24,}', r'-[0-9\.\-_]+', r'-[a-zA-Z0-9\.\-_]+', '']
GIT_USER = 'CA 5GCV'
GIT_EMAIL = '5g_cb.scm@nokia.com'


class INTEGRATION_REPO(object):

    def __init__(self, repo_url, repo_ver, version_pattern='',
                 work_dir=os.path.join(os.getcwd(), 'Integration'),
                 add_if_no=False):
        self.repo_url = repo_url
        self.repo_ver = repo_ver
        self.work_dir = work_dir
        self.prepare_workspace()
        self.version_pattern = self.get_ver_pattern(version_pattern)
        if self.version_pattern:
            self.config_file = ''
            self.config_file = self.get_config_file()
            self.pipeline = self.get_pipeline()
            self.targets = self.get_targets()
            self.int_targets = self.get_int_targets()
        self.add_if_no = add_if_no
        self.dep_file_list = []
        self.git_user = GIT_USER
        self.git_email = GIT_EMAIL

    def get_env_submodule_ver(self):
        g = git.Git(self.work_dir)
        output = g.submodule('status')
        env_version = ''
        for line in output:
            if line.split()[0].strip() == 'env':
                env_version = output.split()[0].strip()
        if env_version:
            return env_version
        raise Exception('[Error] Cannot find env submodule')

    def get_integration_branch(self):
        g_repo = git.Git(self.work_dir)
        branch_data = g_repo.branch('--contains', 'HEAD', '-a')
        for line in branch_data.splitlines():
            line_str = line.strip()
            if line_str == 'master' or 'rel/' in line_str:
                return re.sub('.*/rel', 'rel', line_str)
        return ''

    def run_bitbake_cmd(self, prefix_path, oe_scripts, *bitbake_args):
        bitbake_arg_str = ' '.join(list(bitbake_args))
        bash_cmd = ''
        bash_cmd += '{ mkdir -p build && '
        bash_cmd += 'source ./.config-{} && '.format(self.pipeline)
        if 'meta-toolset/prepare_env.sh' in oe_scripts:
            bash_cmd += 'source {} {} && '.format(
                oe_scripts, prefix_path)
        else:
            bash_cmd += 'source {} build/{} && '.format(
                oe_scripts, prefix_path)
        if oe_scripts == './oe-init-build-env':
            bash_cmd += '../../env/prefix-root-gen-script.d/{} ./prefix_root && '.format(
                prefix_path.replace('integration-', ''))
            bash_cmd += 'source ./prefix_root/environment-setup.sh && '
        bash_cmd += 'PIPELINE={} bitbake {};'.format(
            self.pipeline,
            bitbake_arg_str)
        bash_cmd += '}'
        logging.info(bash_cmd)
        old_wkdir = os.getcwd()
        os.chdir(self.work_dir)
        bash_output = subprocess.check_output(["bash", "-c", bash_cmd])
        os.chdir(old_wkdir)
        return bash_output

    def get_yocto_oe_dir(self):
        try:
            if self.get_config_value('TOOLSET_POKY'):
                return 'meta-toolset/prepare_env.sh'
            else:
                return 'poky/oe-init-build-env'
        except Exception:
            return 'poky/oe-init-build-env'

    def get_comp_info_by_bitbake(self, int_bb_target, comp_name, bb_file):
        comp_name_with_ver = os.path.basename(bb_file)
        regex_pv = r'^(PV)="([^"]+)"'
        regex_repo = r'^(GIT_URI|GIT_REPO|SRC_URI)="([^"]+)"'
        regex_ver = r'^(REVISION|SVNTAG|SVNREV|SRCREV|BIN_VER|SRC_REV)="([^"]+)"'
        comp_dict = {}
        pv = ''
        if comp_name in comp_name_with_ver:
            pv = comp_name_with_ver.split(comp_name)[1].lstrip('_')
        oe_scripts = './oe-init-build-env'
        module = int_bb_target.split('integration-')[1]
        target_var = 'TARGET_{}'.format(module.replace('-', '_'))
        director = self.get_config_value(target_var)
        if module.startswith('Yocto'):
            oe_scripts = self.get_yocto_oe_dir()
        else:
            director = 'integration-{}'.format(director)
        env_file_path = os.path.join(
            self.work_dir,
            'build',
            director,
            '{}.env'.format(comp_name_with_ver))
        try:
            self.run_bitbake_cmd(director, oe_scripts,
                                 '-e', '-b', bb_file, '>', env_file_path)
        except Exception:
            return comp_dict
        with open(env_file_path, 'r') as fr:
            for line in fr.read().splitlines():
                m_repo = re.match(regex_repo, line)
                if m_repo:
                    comp_dict['repo_url'] = m_repo.group(2).split(';')[0]
                m_ver = re.match(regex_ver, line)
                if m_ver:
                    comp_dict['repo_ver'] = m_ver.group(2)
                m_pv = re.match(regex_pv, line)
                if m_pv:
                    pv = m_pv.group(2)
                comp_dict['pv'] = pv
        if 'repo_ver' not in comp_dict and 'repo_url' in comp_dict:
            comp_dict['repo_ver'] = 'HEAD'
        return comp_dict

    def prepare_prefix_and_run_bitbake_cmd(self, target, is_yocto=False, *bitbake_args):
        oe_scripts = './oe-init-build-env'
        target_path = 'integration-{}'.format(target)
        if is_yocto:
            oe_scripts = self.get_yocto_oe_dir()
            target_path = target
        return self.run_bitbake_cmd(target_path, oe_scripts, *bitbake_args)

    def run_dep_cmd(self, director, int_bb_target=''):
        if not int_bb_target:
            int_bb_target = director
        oe_scripts = './oe-init-build-env'
        module = int_bb_target.split('integration-')[1].strip()
        bb_cmd_dir = director
        if module.startswith('Yocto'):
            oe_scripts = self.get_yocto_oe_dir()
        else:
            bb_cmd_dir = 'integration-{}'.format(bb_cmd_dir)
        self.run_bitbake_cmd(bb_cmd_dir, oe_scripts, '-g', int_bb_target)
        dep_file_path = os.path.join(
            self.work_dir,
            'build',
            bb_cmd_dir,
            '%s.dep' % director)
        shutil.copyfile(
            os.path.join(
                self.work_dir,
                'build',
                bb_cmd_dir,
                'recipe-depends.dot'),
            dep_file_path)
        self.dep_file_list.append(dep_file_path)

    def get_int_targets(self):
        int_targets = []
        for target in self.targets:
            if len(target.split('.')) > 1:
                int_targets.append(target.split('.')[1])
        return int_targets

    def get_dep_files(self):
        logging.info('get dep files for integration')
        modules = self.get_config_value('MODULES').split()
        self.dep_file_list = []
        logging.info(modules)
        plat_targets = {}
        for module in modules:
            int_bb_target = 'integration-{}'.format(module)
            try:
                plat_value = self.get_config_value(
                    'TARGET_{}'.format(module.replace('-', '_')))
            except Exception:
                plat_value = 'NATIVE'
            if plat_value not in plat_targets:
                plat_targets[plat_value] = [int_bb_target]
            else:
                plat_targets[plat_value].append(int_bb_target)
                logging.info('plat targets: %s', plat_targets)
        for plat, targets in plat_targets.items():
            int_bb_targets = ' '.join(targets)
            self.run_dep_cmd(plat, int_bb_targets)
        logging.info('dep file list:%s', self.dep_file_list)

    def get_git_changes(self, git_obj):
        """
        List changes in git (integration, meta-5g, etc.) repository
        """
        out = git_obj.status('-s').strip()
        # default empty set
        changes = {}
        if not out:
            return changes
        lines = out.split("\n")
        status_split = re.compile(r"^([^\s]+)\s+(.*)$")

        for change, path in [status_split.match(x.strip()).groups() for x in lines]:
            changes.setdefault(change, []).append(path)
        return changes

    def commit_submodule(self, sub_name, tag_name):
        g_sub = git.Git(os.path.join(self.work_dir, sub_name))
        changes = self.get_git_changes(g_sub)
        logging.info('get chagnes : %s', changes)
        if changes:
            self.git_reset_author(g_sub)
            g_sub.add('.')
            g_sub.commit('-m', 'create knife tag: %s' % tag_name)
        else:
            logging.info("No changes in %s Use last revision. ", sub_name)

    def tag_submodule(self, sub_name, tag_name):
        g_sub = git.Git(os.path.join(self.work_dir, sub_name))
        g_sub.tag('-a', tag_name, '-m', tag_name)
        g_sub.push('origin', tag_name)

    def commit(self, tag_name):
        self.commit_submodule('env', tag_name)
        self.commit_submodule('meta-5g', tag_name)
        g = git.Git(self.work_dir)
        changes = self.get_git_changes(g)
        logging.info('get chagnes : %s', changes)
        if 'M' in changes and changes['M']:
            self.git_reset_author(g)
            g.add('meta-5g')
            g.add('env')
            g.add('meta-5g-cb')
            g.commit('-m', 'create knife tag: %s' % tag_name)
        else:
            logging.info("No changes. Won't commit. Use last revision. ")

    def tag(self, tag_name, push_remote=True):
        """
        Tag integration/ repository
        """
        self.tag_submodule('env', tag_name)
        self.tag_submodule('meta-5g', tag_name)
        g = git.Git(self.work_dir)
        # g.tag(tag_name, '-m', tag_name)
        g.tag('-a', tag_name, '-m', tag_name)
        if push_remote:
            g.push('origin', tag_name)

    def push_to_branch(self, repo_hash):
        logging.info("Push change of %s to Integarion repo", repo_hash)
        g = git.Git(self.work_dir)
        # branch_pattern = self.pipeline.split('_')[0]
        # branch = conf.get('5G_CB_Integration', branch_pattern)
        branch = g.branch().split()[1]
        g.fetch('--all')
        g.pull('origin', branch, '--rebase')
        if g.diff('env'):
            logging.warn(
                'Env not rebase succeed, please check:\n%s',
                g.diff('env'))
        if g.diff('meta-5g'):
            g.add('meta-5g')
            g.commit('-m', 'sync meta-5g from remote')
        g.push('origin', 'HEAD:%s' % branch)

    def prepare_workspace(self):
        """
        Clone and checkout proper integration/ revision
        """
        logging.info('prepare workspace in %s', self.work_dir)
        if os.path.exists(os.path.join(self.work_dir)):
            if not self.repo_ver:
                logging.warn("#### using existing workspace ###")
                return
            shutil.rmtree(self.work_dir)
        git.Repo.clone_from(self.repo_url, self.work_dir)
        logging.info("checkout_ver: %s", self.repo_ver)
        logging.debug("#### work_dir: %s ###", self.work_dir)
        g = git.Git(self.work_dir)
        try:
            g.checkout(self.repo_ver)
        except git.exc.GitCommandError:
            logging.info("Executing git fetch %s %s", self.repo_url, self.repo_ver)
            g.fetch(self.repo_url, self.repo_ver)
            g.checkout(self.repo_ver)
        try:
            self.update_workspace_submodule()
        except Exception:
            # wa, skip poky clone issue
            logging.warn("#### update submodule failed ###")

    def update_workspace_submodule(self):
        git_integration = git.Git(self.work_dir)
        logging.info("Executing git submodule init + sync + update --init")
        git_integration.submodule("init")
        git_integration.submodule("sync")
        git_integration.submodule("update", "-f", "--init", "--recursive")

    def get_comp_info_by_regx(self,
                              comp_name,
                              regx_str,
                              idx_list,
                              platform=''):
        logging.info('get bb file for %s, platform:%s', comp_name, platform)
        comp_bb_list = []
        for dep_file in self.dep_file_list:
            logging.info(
                'get %s, platform:%s in dep file %s',
                comp_name, platform, dep_file)
            logging.info('search comp: %s from file:%s', comp_name, dep_file)
            with open(dep_file, 'r') as fr:
                file_content = fr.read()
                if platform:
                    if '"integration-{}"'.format(platform) not in file_content:
                        logging.info(
                            'fetch dep file only match paltform: %s', platform)
                        continue
                for line in file_content.splitlines():
                    logging.debug('line is : %s', line)
                    m = re.match(regx_str, line)
                    if m:
                        logging.info('matched....')
                        if len(idx_list) == 1:
                            idx = idx_list[0]
                            comp_bb_list.append(m.group(idx))
                        else:
                            ret_list = []
                            for idx in idx_list:
                                ret_list.append(m.group(idx))
                            comp_bb_list.append(ret_list)
        return comp_bb_list

    def get_comp_info(self, comp_name, platform=''):
        return self.get_comp_info_by_regx(
            comp_name,
            r'"%s" \[label="([^\\]+)\\n:([^\\]+)\\n[a-z:]*([^\\]+)"\]' %
            comp_name,
            [2, 3],
            platform)

    def get_comp_bb(self, comp_name, platform=''):
        return self.get_comp_info_by_regx(
            comp_name,
            r'"%s" \[label="([^\\]+)\\n:([^\\]+)\\n[a-z:]*([^\\]+)"\]' %
            comp_name,
            [3],
            platform)

    def get_dep_comp_bb(self, comp_name, platform=''):
        dep_comp_list = self.get_comp_info_by_regx(
            comp_name,
            r'"([^\"]+)" -> "%s"' %
            comp_name,
            [1],
            platform)
        dep_comp_bb_list = []
        for dep_comp in dep_comp_list:
            dep_comp_bb_list.extend(self.get_comp_bb(dep_comp, platform))
        return dep_comp_bb_list

    def get_deped_comp_bb(self, comp_name, platform=''):
        deped_comp_list = self.get_comp_info_by_regx(
            comp_name,
            r'"%s" -> "([^\"]+)"' %
            comp_name,
            [1],
            platform)
        deped_comp_bb_list = []
        for deped_comp in deped_comp_list:
            deped_comp_bb_list.extend(self.get_comp_bb(deped_comp, platform))
        return deped_comp_bb_list

    def get_version_for_comp(self, comp_name, platform=''):
        possible_subpath = os.path.join(self.work_dir, comp_name)
        if os.path.exists(possible_subpath):
            try:
                g = git.Git(self.work_dir)
                repo_msg = g.remote('-v')
                sub_g = git.Git(possible_subpath)
                sub_repo_msg = sub_g.remote('-v')
                if sub_repo_msg != repo_msg:
                    comp_hash = sub_g.log('-1', '--pretty=format:%H').strip('"')
                    return {'repo_ver': comp_hash}
            except Exception:
                logging.warn('Not able to find hash in %s', possible_subpath)
        bb_target = 'integration-%s' % platform if platform else ''
        comp_info = self.get_comp_info(comp_name, platform)
        logging.info('comp_info %s', comp_info)
        comp_dict = self.get_version_from_bb(
            comp_info[0][1], comp_name, comp_info[0][0], bb_target)
        return comp_dict.values()[0]

    def get_version_from_bb(
            self,
            bb_file,
            comp_name='',
            comp_ver='HEAD',
            int_bb_target=''):
        content = ''
        with open(bb_file, 'r') as fr:
            content = fr.read()
        bb_dict = {}
        bb_list = os.path.basename(bb_file).split('_')
        if not comp_name:
            bb_pn = bb_list[0]
        else:
            bb_pn = comp_name
        bb_pv = comp_ver
        if len(bb_list) > 1 and bb_pv == 'HEAD':
            bb_pv = bb_list[1]
        if 'inherit fakerecipe' in content:
            logging.warn('Skip fakerecipe %s', bb_file)
            return {}
        for line in content.splitlines():
            m_srcuri = re.match(r'\s*\?*(SRC_URI)\s*[\?]?=\s*"(\S+)"', line)
            if m_srcuri:
                bb_dict['srcuri'] = m_srcuri.group(2).split(';')[0]
            m_svn_srv = re.match(
                r'\s*\?*(SVNSERVER)\s*[\?]?=\s*"(\S+)"',
                line)
            if m_svn_srv:
                bb_dict['svn_srv'] = m_svn_srv.group(2)
            m_svn_repo = re.match(
                r'\s*(SVNREPO)\s*=\s*"(\S+)"',
                line)
            if m_svn_repo:
                bb_dict['svn_repo'] = m_svn_repo.group(2)
            m_svn_brh = re.match(
                r'\s*(SVNBRANCH)\s*=\s*"(\S+)"',
                line)
            if m_svn_brh:
                bb_dict['svn_branch'] = m_svn_brh.group(2)
            m_svn_tag = re.match(
                r'\s*(SVNTAG)\s*=\s*"(\S+)"',
                line)
            if m_svn_tag:
                bb_dict['svn_tag'] = m_svn_tag.group(2)
            m = re.match(
                r'\s*(GIT_REPO|GIT_URI)\s*=\s*"(\S+)"',
                line)
            if m:
                bb_dict['repo_url'] = m.group(2)
            m_ver = re.match(
                r'\s*(SRCREV|SRC_REV|SVNREV|REVISION)\s*=\s*"(\S+)"',
                line)
            if m_ver:
                bb_dict['repo_ver'] = m_ver.group(2)
        if 'repo_url' not in bb_dict and \
           'svn_srv' in bb_dict and \
           'svn_repo' in bb_dict and \
           'svn_branch' in bb_dict:
            bb_dict['repo_url'] = '%s/%s/%s' % (bb_dict['svn_srv'],
                                                bb_dict['svn_repo'],
                                                bb_dict['svn_branch'])
        if 'repo_url' not in bb_dict and 'srcuri' in bb_dict:
            if bb_dict['srcuri'].startswith('git:') or \
                    bb_dict['srcuri'].startswith('gitsm:') or \
                    bb_dict['srcuri'].startswith('http:') or \
                    bb_dict['srcuri'].startswith('https:'):
                bb_dict['repo_url'] = bb_dict['srcuri']
                self.replace_var_in_bb(bb_dict, bb_pn, bb_pv)
            if 'repo_url' not in bb_dict or '$' in bb_dict['repo_url']:
                bb_dict['repo_url'] = bb_dict['srcuri']
        self.replace_var_in_bb(bb_dict, bb_pn, bb_pv)
        if int_bb_target and (
            'repo_url' not in bb_dict or
            '$' in bb_dict['repo_url'] or
            'repo_ver' not in bb_dict or
                '$' in bb_dict['repo_ver']):
            bb_dict.update(self.get_comp_info_by_bitbake(int_bb_target, bb_pn, bb_file))
        logging.info('repo info is %s', bb_dict)
        if 'repo_ver' in bb_dict and 'repo_url' in bb_dict:
            return {'{}_{}'.format(bb_pn, bb_pv): bb_dict}
        logging.warn('Not Find Full repo info from %s', bb_file)
        logging.warn('repo info is %s', bb_dict)
        return {}

    def replace_var_in_bb(self, bb_dict, bb_pn, bb_pv):
        if 'svn_tag' in bb_dict:
            bb_dict['repo_url'] = re.sub(
                r'\${SVNTAG}',
                bb_dict['svn_tag'],
                bb_dict['repo_url'])
        if 'repo_ver' in bb_dict and 'repo_url' in bb_dict:
            bb_dict['repo_url'] = bb_dict['repo_url'].replace(r'${PN}', bb_pn)
            bb_dict['repo_url'] = bb_dict['repo_url'].replace(r'${PV}', bb_pv)
            bb_dict['repo_ver'] = bb_dict['repo_ver'].replace(r'${PV}', bb_pv)

    def get_base_dep_dict(self):
        base_dep_dict = {}
        for target in self.targets:
            comp_info_list = []
            logging.info('get dep info for target: %s', target)
            for comp_bb_file in self.get_deped_comp_bb(
                    target.split('.')[1],
                    target.split('.')[1].lstrip(r'integration-')):
                comp_prop = self.get_version_from_bb(comp_bb_file,)
                if comp_prop:
                    comp_info_list.append(comp_prop)
            logging.info('dep info: %s', comp_info_list)
            if comp_info_list:
                base_dep_dict[target.split('.')[0]] = comp_info_list
        logging.info('base_dep_dict: %s', base_dep_dict)
        return base_dep_dict

    def replace_submodule(self, comp_name, replace_dict):
        if 'repo_ver' not in replace_dict:
            logging.error(
                '[DESCRIPTION]repo_ver not containted in %s',
                replace_dict)
            sys.exit(2)
        logging.info(
            'update submodule:%s to: %s',
            comp_name, replace_dict['repo_ver'])
        revision = replace_dict['repo_ver']
        if (revision.startswith('refs/') and 'repo_url' in replace_dict):
            self.replace_zuul_submodule(comp_name, replace_dict, revision)
        else:
            g_sub = git.Git(os.path.join(self.work_dir, comp_name))
            g_sub.checkout('master')
            g_sub.pull()
            if not self._contains_ref(g_sub, revision):
                g_sub.fetch(
                    '-u',
                    '-f',
                    '--prune',
                    '--progress',
                    'origin',
                    'refs/*:refs/*')
            g_sub.checkout(revision)
        g = git.Git(self.work_dir)
        changes = self.get_git_changes(g)
        logging.info('get chagnes : %s', changes)
        if 'M' in changes and changes['M']:
            g.add(comp_name)
            g.commit(
                '-m', 'update submodule:%s to: %s' %
                (comp_name, revision))
            logging.info(
                'update submodule:%s to: %s',
                comp_name, revision)

    def replace_zuul_submodule(self, comp_name, replace_dict, revision):
        """
        Replaces content of submodule to what is inside its Zuul counterpart
        """
        subm_repo_url = replace_dict['repo_url']
        if 'protocol' in replace_dict:
            subm_repo_url = re.sub(r'^gitsm',
                                   replace_dict['protocol'],
                                   subm_repo_url)
        new_comp_dir = os.path.join(self.work_dir,
                                    '%s_new' % comp_name)
        os.mkdir(new_comp_dir)
        g_sub_new = git.Git(new_comp_dir)
        g_sub_new.init()
        g_sub_new.fetch(subm_repo_url, revision)
        g_sub_new.checkout('FETCH_HEAD')
        comp_dir = os.path.join(self.work_dir, comp_name)
        g_sub = git.Git(comp_dir)
        self.git_reset_author(g_sub)
        g_sub.rm('-r', '*')
        tar_name = '%s.tar' % comp_name
        tar = tarfile.open(tar_name, 'w')
        tar.add(
            new_comp_dir,
            arcname=comp_name,
            exclude=lambda x: x.startswith(
                '%s/.git' %
                new_comp_dir) or x.endswith('.pyc'))
        tar.close()
        tar_ext = tarfile.open(tar_name)
        old_wkdir = os.getcwd()
        os.chdir(self.work_dir)
        tar_ext.extractall()
        os.chdir(old_wkdir)
        g_sub.add('.')
        g_sub.commit('-m', 'update to : %s' % replace_dict['repo_ver'])

    def git_reset_author(self, git_obj):
        git_obj.config('user.name', self.git_user)
        git_obj.config('user.email', self.git_email)
        git_obj.commit(
            '--amend',
            '-m',
            'ammend origin tag: %s' %
            self.repo_ver,
            '--reset-author',
            '--allow-empty')

    def replace_comp(self, comp_name, replace_dict):
        logging.info('replace %s and data is %s', comp_name, replace_dict)
        comp_bb_list = self.get_comp_bb(comp_name, replace_dict['platform'])
        if not comp_bb_list:
            raise Exception('Cannot find component: {} for {}'.format(
                comp_name,
                replace_dict['platform']))
        if 'bb_ver' in replace_dict:
            dep_comp_bb_list = self.get_dep_comp_bb(
                comp_name,
                replace_dict['platform'])
            logging.info('dep_comp_bb_list: %s', dep_comp_bb_list)
            for bb_file in dep_comp_bb_list:
                self.replace_bbfile_dep(
                    bb_file,
                    comp_name,
                    replace_dict['bb_ver'])
            if 'parent' in replace_dict:
                find_in_dep = False
                for dep_comp_bb in dep_comp_bb_list:
                    if replace_dict['parent'] in dep_comp_bb:
                        find_in_dep = True
                if not dep_comp_bb_list or not find_in_dep:
                    parent_bb_list = self.get_comp_bb(
                        replace_dict['parent'],
                        replace_dict['platform'])
                    if parent_bb_list:
                        self.replace_bbfile_dep(
                            parent_bb_list[0],
                            comp_name,
                            replace_dict['bb_ver'])
        logging.info('comp_bb_list: %s', comp_bb_list)
        for comp_bb_file in set(comp_bb_list):
            if 'string_replace' in replace_dict:
                self.replace_bbfile_str(
                    comp_bb_file,
                    replace_dict['string_replace'])
            if 'repo_url' in replace_dict:
                self.replace_bbfile_repo(
                    comp_bb_file,
                    replace_dict['repo_url'])
            if 'repo_ver' in replace_dict:
                self.replace_bbfile_repo_ver(
                    comp_bb_file,
                    replace_dict['repo_ver'])
            for key, val in replace_dict.items():
                if key not in RESERVED_KEYS:
                    self.replace_file_by_key(
                        comp_bb_file,
                        key,
                        val)

    def replace_bbfile_str(self, bbfile, replace_str_obj):
        inc_file = ''
        if 'orign' not in replace_str_obj or 'new' not in replace_str_obj:
            logging.error('Cannot find origin/new in string replace object')
        else:
            if os.path.basename(bbfile).startswith('integration-'):
                inc_file = os.path.join(
                    os.path.dirname(bbfile),
                    'components-%s.inc' % self.pipeline)
                logging.info('try find inc file: %s', inc_file)
                if not os.path.exists(inc_file):
                    inc_file = ''
        self.replace_file_str(bbfile, replace_str_obj)
        if inc_file:
            self.replace_file_str(inc_file, replace_str_obj)

    def replace_file_str(self, filepath, replace_str_obj):
        content = ''
        new_content = ''
        with open(filepath, 'r') as fr:
            content = fr.read()
            new_content = re.sub(
                replace_str_obj['origin'],
                replace_str_obj['new'],
                content)
        if new_content == content:
            new_content = content.replace(
                replace_str_obj['origin'],
                replace_str_obj['new'])
        if new_content != content:
            logging.info('replace string in file: %s succed', filepath)
            with open(filepath, 'w') as fw:
                fw.write(new_content)
        else:
            logging.info('replace no need in file: %s', filepath)

    def replace_dependency_content(self, old_recipe_content, component, version):
        for ver_regex in VERSION_REGEX:
            old_regex = r'{}{}[\s"]'.format(component, ver_regex)
            new_regex = r"{}-{}".format(component, version)
            match_elems = re.findall(old_regex, old_recipe_content)
            if len(match_elems) == 1:
                old_component_str = match_elems[0].rstrip().rstrip('"')
                return re.sub(old_component_str, new_regex, old_recipe_content)
            if len(match_elems) > 1:
                logging.warn('Get multi match elems %s for %s', match_elems, old_regex)
        raise Exception('No match elem for {} {}'.format(component, VERSION_REGEX))

    def replace_bbfile_dep(self, bbfile, comp_name, bb_ver):
        dep_file = bbfile
        if os.path.basename(bbfile).startswith('integration-'):
            inc_file = os.path.join(
                os.path.dirname(bbfile),
                'components-%s.inc' % self.pipeline)
            logging.info('try find inc file: %s', inc_file)
            if os.path.exists(inc_file):
                dep_file = inc_file
        dep_content = ''
        logging.info('find dep file: %s', dep_file)
        with open(dep_file, 'r') as fr:
            dep_content = fr.read()
        new_dep_content = self.replace_dependency_content(
            dep_content, comp_name, bb_ver)
        if comp_name not in dep_content:
            new_dep_content = re.sub(
                r'(DEPENDS\s*=\s*")',
                r'\1{}-{} '.format(comp_name, bb_ver))
        with open(dep_file, 'w') as fw:
            fw.write(new_dep_content)

    def replace_bbfile_repo(self, bbfile, repo_url):
        m_svn = re.match(
            r'https://([^/]*)(/isource/svnroot/[^/]*)/(.*)',
            repo_url)
        if m_svn:
            self.replace_file_by_key(bbfile, 'SVNSERVER', m_svn.group(1))
            self.replace_file_by_key(bbfile, 'SVNREPO', m_svn.group(2))
            self.replace_file_by_key(bbfile, 'SVNBRANCH', m_svn.group(3))
        else:
            self.replace_file_by_key(bbfile, 'GIT_REPO', repo_url)

    def replace_bbfile_repo_ver(self, bbfile, repo_ver):
        self.replace_file_by_key(bbfile, 'SRCREV', repo_ver, skip_nomatch=True)
        self.replace_file_by_key(bbfile, 'SRC_REV', repo_ver, skip_nomatch=True)
        self.replace_file_by_key(bbfile, 'REVISION', repo_ver, skip_nomatch=True)
        self.replace_file_by_key(bbfile, 'SVNREV', repo_ver, skip_nomatch=True)

    def replace_file_by_key(self, filename, key, value,
                            dst_file=None, skip_nomatch=False):
        content = ''
        replace_file = filename
        logging.info('replace bbfile: %s by key: %s', replace_file, key)
        if (key == 'DEPENDS' and
                os.path.basename(filename).startswith('integration-')):
            inc_file = os.path.join(
                os.path.dirname(filename),
                'components-%s.inc' % self.pipeline)
            logging.info('try find inc file: %s', inc_file)
            if os.path.exists(inc_file):
                replace_file = inc_file
        if not dst_file:
            dst_file = replace_file
        with open(replace_file, 'r') as fr:
            content = fr.read()
        new_content = content
        m = re.search(r'^\s*%s\s*=\s*"[^"]+"|\n\s*%s\s*=\s*"[^"]+"' %
                      (key, key),
                      content)
        match_key = False
        if m:
            match_key = True
            logging.info('find matched for %s in %s', key, replace_file)
            new_content = content.replace(
                m.group(0),
                re.sub(r'(=\s*)"[^"]+"', r'\1"%s"' % value, m.group(0)))
        else:
            m = re.search(r'([";]\s*%s\s*=\s*)([^;]+)' % key, content)
            if m:
                match_key = True
                logging.info('find matched for %s in %s', key, replace_file)
                new_content = re.sub(
                    r'%s%s' %
                    (m.group(1), m.group(2)), '%s%s' %
                    (m.group(1), value),
                    content)
        if not match_key:
            logging.warn('Can not find key matched %s', key)
            if not skip_nomatch:
                if self.add_if_no:
                    logging.warn('We will add new line: %s=%s', key, value)
                    new_content = new_content + '\n%s = %s' % (key, value)
                else:
                    sys.exit(2)
        if new_content != content:
            with open(dst_file, 'w') as fw:
                fw.write(new_content)

    def gen_dep_all(self):
        dep_all_file = os.path.join(self.work_dir, 'build/dep_all', 'all.dep')
        os.mkdir(os.path.join(self.work_dir, 'build/dep_all'))
        if os.path.exists(dep_all_file):
            os.unlink(dep_all_file)
        with open(dep_all_file, 'w') as fall:
            for dep_file in self.dep_file_list:
                fall.write('dep_file: {}\n'.format(dep_file))
                with open(dep_file) as fdep:
                    fall.write('\n{}'.format(fdep.read()))

    def get_comp_dep_dict(self):
        dep_all_file = os.path.join(self.work_dir, 'build/dep_all', 'all.dep')
        comp_dep_dict = {}
        regex_deps = r'"([^\"]+)" -> "([^\"]+)"'
        with open(dep_all_file, 'r') as fr:
            for line in fr.read().splitlines():
                logging.debug('line is : %s', line)
                m = re.match(regex_deps, line)
                if m:
                    logging.debug('matched....')
                    comp = m.group(1)
                    comp_dep = m.group(2)
                    if comp not in comp_dep_dict:
                        comp_dep_dict[comp] = [comp_dep]
                    else:
                        comp_dep_dict[comp].append(comp_dep)
        return comp_dep_dict

    def get_all_comps(self):
        dep_all_file = os.path.join(self.work_dir, 'build/dep_all', 'all.dep')
        comp_obj_list = []
        regex_comps = r'" \[label="([^\\]+)\\n:([^\\]+)\\n([^\\]+)"\]'
        regex_dep_file = r'dep_file:\s*(\S+)'
        int_bb_target = ''
        with open(dep_all_file, 'r') as fr:
            for line in fr.read().splitlines():
                logging.debug('line is : %s', line)

                m_f = re.match(regex_dep_file, line)
                if m_f:
                    dep_file = m_f.group(1)
                    int_bb_target = os.path.basename(dep_file).split('.dep')[0]
                m = re.search(regex_comps, line)
                if m:
                    comp_name = m.group(1)
                    if comp_name.startswith('integration-'):
                        continue
                    ver_obj = self.get_version_from_bb(
                        m.group(3),
                        comp_name=comp_name,
                        comp_ver=re.sub(r'-r[0-9]+$', '', m.group(2)),
                        int_bb_target=int_bb_target)
                    revision = ''
                    if ver_obj.values():
                        if 'repo_ver' in ver_obj.values()[0]:
                            revision = ver_obj.values()[0]['repo_ver']
                    logging.debug('matched....')
                    comp_obj_list.append({
                        'comp': m.group(1),
                        'version': m.group(2),
                        'file': m.group(3),
                        'revision': revision})
        return comp_obj_list

    def check_dep_files(self):
        logging.info('check dep files for integration')
        pipeline = self.pipeline
        comp_name = None
        logging.info('=== %s ===', self.int_targets)
        dep_result = os.path.join(os.getcwd(), "dep_result.txt")
        cmd = "cd %s && \
            mkdir -p build && \
            source ./oe-init-build-env build/dep > /dev/null && \
            ../../env/prefix-root-gen-script.d/NATIVE ./prefix_root && \
            source ./prefix_root/environment-setup.sh && \
            PIPELINE=%s bitbake -g %s " % (self.work_dir,
                                           self.pipeline,
                                           ' '.join(self.int_targets))
        try:
            out_log = subprocess.check_output(cmd)
            out_ret = 0
        except Exception:
            out_ret = 2
            for err_msg in ERR_MSG_LIST:
                err_line = re.search(err_msg, out_log)
                if err_line:
                    full_name = err_line.group(1) + BBFILE_EXT
                    group_name = re.search(
                        r"(.*?)(-|_)([vV\d\.-]*|[a-z0-9]{24,})(-(.*))?\.bb",
                        full_name)
                    if group_name:
                        comp_name = group_name.group(1)
                        with open(dep_result, "w") as fn:
                            fn.write("pipeline=%s\n" % (pipeline))
                            fn.write("ISSUE=%s_%s\n" % (self.version_pattern,
                                                        comp_name))
                        logging.warn(
                            "MEET ERROR: pip=%s comp=%s", pipeline, comp_name)
                        return out_ret
        with open(dep_result, "w") as fn:
            fn.write("pipeline=%s\n" % (pipeline))
            fn.write("ISSUE=%s\n" % (comp_name))
        logging.info(
            "FINE! check dependence files finish. pip=%s comp=%s",
            pipeline, comp_name)
        return out_ret

    def _contains_ref(self, git_repo, commit_hash):
        try:
            git_repo.log('--pretty=oneline', '-n', '1', commit_hash)
            logging.info('Find commit: %s', commit_hash)
        except Exception:
            logging.info('Not find commit: %s', commit_hash)
            return False
        return True

    def patch(self, patch_file):
        """
        patch workspace
        """
        if os.path.exists(patch_file):
            os.chdir(self.work_dir)
            subprocess.check_output('patch -p0 < {}'.format(patch_file))
        else:
            logging.error('Patch file: %s not exists', patch_file)
            sys.exit(2)

    def get_ver_pattern(self, version_pattern):
        """
        get version pattern
        """
        if not version_pattern:
            m = re.match(r'^([0-9]+\.[0-9]+)\.', self.repo_ver)
            if m:
                return m.group(1)
        return version_pattern

    def set_config_file(self, config_file):
        self.config_file = config_file
        self.version_pattern = self.get_config_value('VERSION_PATTERN')
        self.pipeline = self.get_config_value('PIPELINE')

    def get_config_file(self):
        """
        get config file
        """
        if self.config_file:
            return self.config_file
        if self.version_pattern:
            conf_list = utils.get_sub_files(self.work_dir, r'\.config-.*')
            for conf_file in conf_list:
                conf_content = utils.get_file_content(
                    os.path.join(self.work_dir, conf_file))
                for line in conf_content.splitlines():
                    if line.endswith(
                            'VERSION_PATTERN={}'.format(self.version_pattern)):
                        return conf_file
            raise Exception(
                'Cannot find config file for  {}'.format(
                    self.version_pattern))
        raise Exception('Cannot find config file')

    def get_pipeline(self, pipeline=''):
        if pipeline:
            return pipeline
        return self.get_config_value('PIPELINE')

    def get_wft_pkg_name(self):
        return self.get_config_value('WFT_PACKAGE_NAME')

    def get_config_value(self, key_name):
        if not self.config_file:
            self.get_config_file()
        conf_content = utils.get_file_content(
            os.path.join(
                self.work_dir,
                self.config_file))
        m1 = re.search(r'{}="([^"]+)"'.format(key_name), conf_content)
        m2 = re.search(r'{}=(\S+)'.format(key_name), conf_content)
        if m1:
            return m1.group(1)
        elif m2:
            return m2.group(1)
        else:
            logging.error('Config content : %s', conf_content)
            raise Exception('Cannot find {} in {}'.format(
                key_name,
                self.config_file))

    def get_targets(self, targets=''):
        if targets:
            return targets
        target_list = []
        for platform in self.get_config_value('MODULES').split():
            m_target = self.get_config_value('TARGET_{}'.format(platform.replace('-', '_')))
            if m_target:
                target_list.append(
                    '{}.integration-{}'.format(
                        m_target,
                        platform))
            else:
                raise Exception(
                    'Cannot find Target for {}'.format(
                        platform))
        return target_list
