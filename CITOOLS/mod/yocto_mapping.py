import os
import json
import requests

from six.moves import configparser
from api import config


WFT_CONFIG_FILE = os.path.join(config.get_config_path(), 'properties/wft.properties')
WFT_CONFIG = configparser.ConfigParser()
WFT_CONFIG.read(WFT_CONFIG_FILE)
WFT_URL = WFT_CONFIG.get('wft', 'url')
WFT_KEY = WFT_CONFIG.get('wft', 'key')
WFT_ATTACHMENT_URL = "{}:8091/api/v1/5G:WMP/5G_Central/builds".format(WFT_URL)


class Yocto_Mapping(object):
    """
    A Class to do operations on yocto mapping from WFT
    """

    def __init__(self, base_pkg):
        self.base_pkg = base_pkg
        self.bb_mapping_dict = self.get_bbmapping_from_wft()

    def get_bbmapping_from_wft(self):
        bbmapping_id = self.get_build_bbmapping_id(self.base_pkg)
        if not bbmapping_id:
            raise Exception('Cannot get bb_mapping id from {}'.format(self.base_pkg))
        response = requests.get(
            '{}/{}/attachments/{}.json'.format(
                WFT_ATTACHMENT_URL,
                self.base_pkg,
                bbmapping_id),
            params={'access_key': WFT_KEY})
        if response.ok:
            yocto_mapping_path = os.path.join(os.getcwd(), '{}.yocto_mapping'.format(self.base_pkg))
            print('Write yocto mapping to {}'.format(yocto_mapping_path))
            with open(yocto_mapping_path, 'w') as fw:
                fw.write(response.text)
            with open(yocto_mapping_path, 'r') as fr:
                return json.load(fr)
        raise Exception("WFT return {} when download {} bbmapping".format(response.status_code, self.base_pkg))

    def get_build_bbmapping_id(self, wft_version):
        print("{}/{}/attachments.json".format(WFT_ATTACHMENT_URL, wft_version))
        response = requests.get(
            "{}/{}/attachments.json".format(WFT_ATTACHMENT_URL, wft_version),
            params={'access_key': WFT_KEY}
        )
        if response.ok:
            for attachment in json.loads(response.text):
                if attachment['attachment_type'] == 'yocto_mapping':
                    return attachment['id']
        else:
            print("WFT return {} when get {} id".format(response.status_code, self.base_pkg))
        return None

    def get_component_source_by_project(self, project_name):
        for source in self.bb_mapping_dict['sources']:
            if 'recipes' not in source:
                continue
            if 'src_uri' in source and self.is_src_uri_match(source['src_uri'], project_name):
                return source
        return None

    def is_src_uri_match(self, src_uri1, src_uri2):
        print('Compare {} and {}'.format(src_uri1, src_uri2))
        if src_uri1.endswith(src_uri2) or src_uri1.endswith('{}.git'.format(src_uri2)):
            return True
        return False

    def get_component_dict(self, comp_name):
        for source in self.bb_mapping_dict['sources']:
            if 'recipes' not in source:
                continue
            for recipe_dict in source['recipes']:
                if 'src_uri' in source and source['src_uri'] == comp_name:
                    return source, recipe_dict.keys[0], recipe_dict.values[0]
                for recipe_dict_key, recipe_dict_value in recipe_dict.items():
                    if os.path.basename(recipe_dict_key).split('.bb')[0].split('_')[0] == comp_name:
                        return source, recipe_dict_key, recipe_dict_value
        return None, None, None

    def get_component_sub_sources(self, comp_name):
        source, recipe_path, recipe_info = self.get_component_dict(comp_name)
        if recipe_info:
            if 'subsources' in recipe_info:
                return recipe_info['subsources'], source['src_uri_type']
            return [recipe_info], source['src_uri_type']
        return {}, ''

    def get_comp_hash(self, comp_name):
        sub_sources, src_uri_type = self.get_component_sub_sources(comp_name)
        if sub_sources:
            print('Get sub_sources {}'.format(sub_sources))
        for sub_source in sub_sources:
            if 'rev' in sub_source:
                if src_uri_type != 'svn':
                    return sub_source['rev']
                else:
                    return '{}@{}'.format(sub_source['module'], sub_source['rev'])
        return ''
