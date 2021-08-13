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

    def __init__(self, base_load):
        self.base_load = base_load
        self.bb_mapping_dict = self.get_bbmapping_from_wft()

    def get_bbmapping_from_wft(self):
        bbmapping_id = self.get_build_bbmapping_id(self.base_load)
        if not bbmapping_id:
            raise Exception('Cannot get bb_mapping id from {}'.format(self.base_load))
        response = requests.get(
            '{}/{}/attachments/{}.json'.format(WFT_ATTACHMENT_URL, self.base_load, bbmapping_id),
            params={'access_key': WFT_KEY}
        )
        if response.ok:
            return json.loads(response.text)
        raise Exception("WFT return {} when download {} bbmapping".format(response.status_code, self.base_load))

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
            print("WFT return {} when get {} id".format(response.status_code, self.base_load))
        return None

    def get_component_dict(self, comp_name):
        for source in self.bb_mapping_dict['sources']:
            if 'recipes' not in source:
                continue
            for recipe_dict in source['recipes']:
                if 'src_uri' in recipe_dict and recipe_dict['src_uri']:
                    return recipe_dict, None, None
                for recipe_dict_key, recipe_dict_value in recipe_dict.items():
                    if os.path.basename(recipe_dict_key).split('.bb')[0].split('_')[0] == comp_name:
                        return recipe_dict, recipe_dict_key, recipe_dict_value
        return None, None, None

    def get_component_sources(self, comp_name):
        recipe_dict, recipe_path, recipe_info = self.get_component_dict(comp_name)
        if recipe_info and 'subsources' in recipe_info:
            return recipe_info['subsources']
        return {}

    def get_component_hash(self, comp_name):
        sources = self.get_component_sources(comp_name)
        for source in sources:
            if 'rev' in source:
                return source['rev']
        return ''
