import os
import re
import git
import logging
import traceback
import urllib
import json
import requests

from six.moves import configparser
from mod import integration_repo
from api import http_api
from api import config

logging.basicConfig(level=logging.INFO)
WFT_CONFIG_FILE = os.path.join(config.get_config_path(), 'properties/wft.properties')
WFT_CONFIG = configparser.ConfigParser()
WFT_CONFIG.read(WFT_CONFIG_FILE)
WFT_URL = WFT_CONFIG.get('wft', 'url')
WFT_KEY = WFT_CONFIG.get('wft', 'key')
WFT_ATTACHMENT_URL = "{}:8091/api/v1/5G:WMP/5G_Central/builds".format(WFT_URL)
WFT_SEARCH_BUILD = "{}:8091/5G:WMP/api/v1/build.json?" \
    "access_key={}&view[items]=50&view[sorting_field]=created_at" \
    "&view[sorting_direction]=DESC&view[columns[][id]]=deliverer.project.full_path" \
    "&view[columns[][id]]=deliverer.title&view[columns[][id]]=version" \
    "&view[columns[][id]]=branch.title&view[columns[][id]]=state" \
    "&view[columns[][id]]=planned_delivery_date&view[columns[][id]]=common_links" \
    "&view[columns[][id]]=compare_link" \
    "&view[view_filters_attributes[128671826645388]][column]=deliverer.project.full_path" \
    "&view[view_filters_attributes[128671826645388]][operation]=eq" \
    "&view[view_filters_attributes[128671826645388]][value][]=5G%3AWMP" \
    "&view[view_filters_attributes[122019703348590]][column]=deliverer.title" \
    "&view[view_filters_attributes[122019703348590]][operation]=eq" \
    "&view[view_filters_attributes[122019703348590]][value][]=5G_Central" \
    "&view[view_filters_attributes[24216713295283]][column]=version" \
    "&view[view_filters_attributes[24216713295283]][operation]=matches_regexp" \
    "&view[view_filters_attributes[24216713295283]][value][]=%5CA5G%5B0-9a-zA-Z%5D*_{}%5Cz&"
HTTP_HEADERS = {'Content-Type': 'application/json', 'Accept': 'application/json'}
INTEGRATION_URL = 'ssh://gerrit.ext.net.nokia.com:29418/MN/5G/COMMON/integration'


class GET_COMPONENT_INFO(object):

    def __init__(self, base_pkg, no_dep_file=False, only_mapping_file=False):
        self.base_pkg = base_pkg
        self.if_bb_mapping, self.src_list = self.check_bb_mapping_file()
        self.only_mapping_file = only_mapping_file
        if not only_mapping_file:
            with_dep_file = not self.if_bb_mapping
            integration_dir = os.path.join(
                os.getcwd(), 'Integration_{}'.format(base_pkg))
            self.int_repo = integration_repo.INTEGRATION_REPO(
                INTEGRATION_URL, base_pkg, work_dir=integration_dir)
            branch = self.int_repo.get_integration_branch()
            if with_dep_file and not no_dep_file:
                self.int_repo.get_dep_files()
                self.int_repo.gen_dep_all()
            try:
                print('Base tag: {} add to gerrit'.format(base_pkg))
                g = git.Git(integration_dir)
                g.push('origin', '{}:refs/for/{}%merged'.format(base_pkg, branch))
            except Exception:
                traceback.print_exc()
                print('Tag {} may already exists'.format(base_pkg))
                print('Please ignore above error, \
                      it will not cause the job build failed! \
                      The build is moving on....')

    def find_bb_target(self, comp_name, dep_dict):
        if comp_name in dep_dict:
            up_comp = dep_dict[comp_name]
            if up_comp.startswith('integration-'):
                return up_comp
            else:
                return self.find_bb_target(up_comp, dep_dict)
        return ''

    def get_comp_bbver_from_dep_file(self, comp_name):
        dep_all_file = os.path.join(self.int_repo.work_dir, 'build/dep_all', 'all.dep')
        regex_comps = r'" \[label="{}\\n:([^\\]+)\\n([^\\]+)"\]'.format(comp_name)
        # regex_dep_file = r'dep_file:\s*(\S+)'
        # int_bb_target = '
        comp_bbver = ''
        with open(dep_all_file, 'r') as fr:
            content = fr.read()
            for line in content.splitlines():
                logging.debug('line is : %s', line)
                m_v = re.match(regex_comps, line)
                if m_v:
                    comp_bbver = m_v.group(1)
        logging.info('%s bbver  %s', comp_name, comp_bbver)
        return comp_bbver

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
                    dep_dict[down_comp.split('.')[0]] = up_comp.split('.')[0]
        platform = self.find_bb_target(comp_name, dep_dict).split('integration-')[-1]
        logging.info('Get %s version on %s', comp_name, platform)
        version_dict = self.int_repo.get_version_for_comp(comp_name, platform=platform)
        return version_dict['repo_ver']

    def check_bb_mapping_file(self):
        src_list = []
        file_exists = self.download_bbmapping_from_wft()
        if not file_exists:
            logging.info("Get %s bb_mapping form WFT failed, try Artifactory", self.base_pkg)
            file_exists = self.download_bbmapping_from_artifactory()
        if file_exists:
            with open("bb_mapping.json", 'r') as f:
                json_str = f.read()
            bb_mapping_dict = json.loads(json_str)
            src_list = bb_mapping_dict['sources']
        return file_exists, src_list

    def search_build_on_wft(self):
        response = requests.get(
            WFT_SEARCH_BUILD.format(WFT_URL, WFT_KEY, self.base_pkg),
            headers=HTTP_HEADERS
        )
        if response.ok:
            try:
                build_list = json.loads(response.text)['items']
            except Exception:
                logging.warn("Can not find build %s on WFT", self.base_pkg)
                return False
            if len(build_list) == 1:
                return build_list[0]["version"]
            else:
                logging.warn("Multiple builds are found on WFT for %s", self.base_pkg)
                return False
        else:
            logging.warn("WFT return %s when search %s", response.status_code, self.base_pkg)
            return False

    def get_build_bbmapping_id(self, wft_version):
        response = requests.get(
            "{}/{}/attachments.json".format(WFT_ATTACHMENT_URL, wft_version),
            params={'access_key': WFT_KEY}
        )
        if response.ok:
            for attachment in json.loads(response.text):
                if attachment['attachment_file_name'] == 'bb_mapping.json':
                    return attachment['id']
        else:
            logging.warn("WFT return %s when get %s attachments", response.status_code, self.base_pkg)
        return False

    def download_bbmapping_from_wft(self):
        wft_version = self.search_build_on_wft()
        if not wft_version:
            return False
        bbmapping_id = self.get_build_bbmapping_id(wft_version)
        if not bbmapping_id:
            return False
        response = requests.get(
            '{}/{}/attachments/{}.json'.format(WFT_ATTACHMENT_URL, wft_version, bbmapping_id),
            params={'access_key': WFT_KEY}
        )
        if response.ok:
            with open("bb_mapping.json", 'w') as bb_mapping_fd:
                bb_mapping_fd.write(response.text)
            logging.info("Write WFT yocto_mapping to bb_mapping.json")
            return True
        else:
            logging.warn("WFT return %s when download %s bbmapping", response.status_code, self.base_pkg)
        return False

    def download_bbmapping_from_artifactory(self):
        artifactory_url = "http://artifactory-espoo1.int.net.nokia.com/artifactory/mnp5g-central-public-local/System_Release/{}/bb_mapping.json".format(self.base_pkg)
        file_exists = False
        f = urllib.urlopen(artifactory_url)
        print(f.getcode())
        if f.getcode() == 200:
            file_exists = True
        print("[Info] find bb mapping file from: {}".format(artifactory_url))
        print("[Info] result of finding bb mapping file: {}".format(file_exists))
        file_name = os.path.join(os.getcwd(), artifactory_url.split('/')[-1])
        http_api.download(artifactory_url, file_name)
        return file_exists

    def get_integration_target(self, comp_name):
        for src in self.src_list:
            recipe_list = src['recipes']
            for recipe in recipe_list:
                for key_name in recipe.keys():
                    if key_name.endswith('.bb'):
                        if 'depends' not in recipe[key_name]:
                            continue
                        depends = recipe[key_name]['depends']
                        m = re.search(r'\s*{}\s*'.format(comp_name), depends)
                        if m and len(m.group(0)) > len(comp_name) or depends == comp_name:
                            if recipe['component'].startswith('integration-'):
                                return recipe['component'].split('.')[0]
                            else:
                                return self.get_integration_target(recipe['component']).split('.')[0]
        raise Exception('Cannot get integration target for {}'.format(comp_name))

    def get_comp_hash_from_mapping_file(self, comp_name):
        revision = self.get_value_from_mapping_and_env(comp_name, 'revision', 'repo_ver')
        if not revision:
            revision = self.get_value_from_mapping_and_env(comp_name, 'rev', 'repo_ver')
        if not revision:
            revision = self.get_value_from_mapping_and_env(comp_name, 'PV', 'repo_ver')
        return revision

    def get_recipe_from_mapping(self, comp_name):
        for src in self.src_list:
            recipe_list = src['recipes']
            for recipe in recipe_list:
                if comp_name == recipe['component']:
                    for key_name in recipe.keys():
                        if key_name.endswith('.bb'):
                            return key_name
        return ''

    def get_value_from_mapping_and_env(self, comp_name, mapping_key, env_key):
        value = ''
        for src in self.src_list:
            recipe_list = src['recipes']
            for recipe in recipe_list:
                if comp_name == recipe['component']:
                    print("[Info] Get info for {}: {}".format(comp_name, recipe))
                    if mapping_key in src:
                        value = src[mapping_key]
                    elif not self.only_mapping_file:
                        integration_target = self.get_integration_target(comp_name)
                        for key_name in recipe.keys():
                            if key_name.endswith('.bb'):
                                # get env_key from bb file
                                logging.info('Get %s  for %s', env_key, key_name)
                                recipe_path = os.path.join(self.int_repo.work_dir, key_name)
                                comp_dict = self.int_repo.get_comp_info_by_bitbake(
                                    integration_target, comp_name, recipe_path)
                                if env_key in comp_dict:
                                    value = comp_dict[env_key]
        print("[Info] Get value {} from bb mapping and env for {} result is: {}".format(mapping_key, comp_name, value))
        return value

    def get_comp_bbver_from_mapping_file(self, comp_name):
        return self.get_value_from_mapping_and_env(comp_name, 'bb_ver', 'pv')

    def get_comp_hash(self, comp_name):
        if self.if_bb_mapping:
            return self.get_comp_hash_from_mapping_file(comp_name)
        else:
            return self.get_comp_hash_from_dep_file(comp_name)

    def get_comp_bb_ver(self, comp_name):
        if self.if_bb_mapping:
            return self.get_comp_bbver_from_mapping_file(comp_name)
        else:
            return self.get_comp_bbver_from_dep_file(comp_name)
