import os
import re
import git
import logging
import traceback
import urllib
import json

from mod import integration_repo
from api import http_api

logging.basicConfig(level=logging.INFO)
INTEGRTION_URL = 'ssh://gerrit.ext.net.nokia.com:29418/MN/5G/COMMON/integration'


class GET_COMPONENT_INFO(object):

    def __init__(self, base_pkg):
        self.base_pkg = base_pkg
        self.if_bb_mapping, self.src_list = self.check_bb_mapping_file()
        with_dep_file = not self.if_bb_mapping
        integration_dir = os.path.join(
            os.getcwd(), 'Integration_{}'.format(base_pkg))
        self.int_repo = integration_repo.INTEGRATION_REPO(
            INTEGRTION_URL, base_pkg, work_dir=integration_dir)
        branch = self.int_repo.get_integration_branch()
        if with_dep_file:
            self.int_repo.get_dep_files()
            self.int_repo.gen_dep_all()
        try:
            print('Base tag: {} add to gerrit'.format(base_pkg))
            g = git.Git(integration_dir)
            g.push('origin', '{}:refs/for/{}%merged'.format(base_pkg, branch))
        except Exception:
            traceback.print_exc()

    def find_bb_target(self, comp_name, dep_dict):
        if comp_name in dep_dict:
            up_comp = dep_dict[comp_name]
            if up_comp.startswith('integration-'):
                return up_comp
            else:
                return self.find_bb_target(up_comp, dep_dict)
        return ''

    def get_comp_hash_from_dep_file(self, comp_name):
        dep_all_file = os.path.join(self.int_repo.work_dir, 'build/dep_all', 'all.dep')
        regex_deps = r'"([^"]+)" -> "([^"]+)"'
        # regex_dep_file = r'dep_file:\s*(\S+)'
        # int_bb_target = ''
        dep_dict = dict()
        with open(dep_all_file, 'r') as fr:
            content = fr.read()
            for line in content.splitlines():
                logging.debug('line is : %s', line)
                m_d = re.match(regex_deps, line)
                if m_d:
                    up_comp = m_d.group(1)
                    down_comp = m_d.group(2)
                    dep_dict[down_comp] = up_comp
        platform = self.find_bb_target(comp_name, dep_dict).split('integration-')[-1]
        logging.info('Get %s version on %s', comp_name, platform)
        version_dict = self.int_repo.get_version_for_comp(comp_name, platform=platform)
        return version_dict['repo_ver']

    def check_bb_mapping_file(self):
        artifactory_url = "http://artifactory-espoo1.int.net.nokia.com/artifactory/mnp5g-central-public-local/System_Release/{}/bb_mapping.json".format(self.base_pkg)
        file_exists = False
        f = urllib.urlopen(artifactory_url)
        print(f.getcode())
        if f.getcode() == 200:
            file_exists = True
        print("[Info] find bb mapping file from: {}".format(artifactory_url))
        print("[Info] result of finding bb mapping file: {}".format(file_exists))
        src_list = []
        if file_exists:
            file_name = os.path.join(os.getcwd(), artifactory_url.split('/')[-1])
            http_api.download(artifactory_url, file_name)
            with open(file_name, 'r') as f:
                json_str = f.read()
            bb_mapping_dict = json.loads(json_str)
            src_list = bb_mapping_dict['sources']
        return file_exists, src_list

    def get_comp_hash_from_mapping_file(self, comp_name):
        comp_hash = ''
        if comp_name == 'env':
            comp_hash = self.int_repo.get_env_submodule_ver()
        for src in self.src_list:
            recipe_list = src['recipes']
            for recipe in recipe_list:
                if comp_name == recipe['component']:
                    if 'revision' in src:
                        comp_hash = src['revision']
                    else:
                        for key_name in recipe.keys():
                            if key_name.endswith('.bb'):
                                # get comp_hash from bb file
                                logging.info('Get commit hash for {}'.format(key_name))
                                recipe_path = os.path.join(self.int_repo.work_dir, key_name)
                                logging.info('Get commit hash from {}'.format(recipe_path))
                                comp_dict = self.int_repo.get_version_from_bb(recipe_path).values()[0]
                                if 'repo_ver' in comp_dict:
                                    comp_hash = comp_dict['repo_ver']
        print("[Info] Get comp hash from bb mapping file for {} result is: {}".format(comp_name, comp_hash))
        return comp_hash

    def get_comp_hash(self, comp_name):
        if self.if_bb_mapping:
            return self.get_comp_hash_from_mapping_file(comp_name)
        else:
            return self.get_comp_hash_from_dep_file(comp_name)
