import os
import re
import logging
import traceback

from six.moves import configparser
from mod import integration_repo
from mod import utils
from mod import bb_mapping
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
REVISION_KEYS = ['revision', 'rev', 'pv']


class GET_COMPONENT_INFO(object):

    def __init__(self, base_pkg, no_dep_file=False, only_mapping_file=False):
        self.base_pkg = base_pkg
        self.bb_mapping = self.check_bb_mapping_file()
        self.only_mapping_file = only_mapping_file
        if base_pkg.startswith('SBTS'):
            self.only_mapping_file = True
        self.int_repo = None
        self.no_dep_file = no_dep_file

    def initial_work_dir(self):
        if self.int_repo:
            return
        if not self.only_mapping_file:
            with_dep_file = not self.bb_mapping
            integration_dir = os.path.join(
                os.getcwd(), 'Integration_{}'.format(self.base_pkg))
            self.int_repo = integration_repo.INTEGRATION_REPO(
                utils.INTEGRATION_URL, self.base_pkg, work_dir=integration_dir)
            if with_dep_file and not self.no_dep_file:
                self.int_repo.get_dep_files()
                self.int_repo.gen_dep_all()

    def find_bb_target(self, comp_name, dep_dict):
        if comp_name in dep_dict:
            up_comp = dep_dict[comp_name]
            if up_comp.startswith('integration-'):
                return up_comp
            else:
                return self.find_bb_target(up_comp, dep_dict)
        return ''

    def get_comp_bbver_from_dep_file(self, comp_name):
        self.initial_work_dir()
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
        self.initial_work_dir()
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
        try:
            return bb_mapping.BB_Mapping(self.base_pkg)
        except Exception:
            logging.warn('Cannot get bb_mapping for %s', self.base_pkg)
            traceback.print_exc()
            return None

    def get_integration_target(self, comp_name):
        targets = self.bb_mapping.get_integration_targets(comp_name)
        if targets:
            return targets[0]
        raise Exception('Cannot get integration target for {}'.format(comp_name))

    def get_comp_hash_from_mapping_file(self, comp_name):
        logging.info('Run get_comp_value_by_keys for %s', comp_name)
        comp_hash = self.bb_mapping.get_comp_value_by_keys(comp_name, REVISION_KEYS)
        if comp_hash:
            return comp_hash
        # comp_hash is None
        # means we do not found matched component in mapping
        if comp_hash is None:
            return None
        if self.base_pkg.startswith('SBTS'):
            return ''
        try:
            return self.get_value_from_bitbake_env(comp_name, 'repo_ver')
        except Exception:
            logging.info('Run bitbake -e for %s Failed', comp_name)
        return ''

    def get_value_from_bitbake_env(self, comp_name, env_key):
        value = ''
        self.initial_work_dir()
        integration_target = self.get_integration_target(comp_name)
        recipe_files = self.bb_mapping.get_component_files(comp_name)
        for recipe_file in recipe_files:
            # get env_key from bb file
            logging.info('Get %s  for %s', env_key, comp_name)
            recipe_path = os.path.join(self.int_repo.work_dir, recipe_file)
            comp_dict = self.int_repo.get_comp_info_by_bitbake(
                integration_target, comp_name, recipe_path)
            if env_key in comp_dict:
                value = comp_dict[env_key]
        return value

    def get_comp_hash(self, comp_name):
        if self.bb_mapping:
            return self.get_comp_hash_from_mapping_file(comp_name)
        elif self.only_mapping_file:
            return ''
        else:
            try:
                return self.get_comp_hash_from_dep_file(comp_name)
            except Exception:
                return ''
