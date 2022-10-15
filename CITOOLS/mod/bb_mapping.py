import os
import json
import logging
import requests
from six.moves import configparser
from api import config
from mod import origin_mapping
from mod import yocto_mapping
from mod import wft_tools

# in ci-scripsts this will be get from ENV
WFT_CONFIG_FILE = os.path.join(config.get_config_path(), 'properties/wft.properties')
WFT_CONFIG = configparser.ConfigParser()
WFT_CONFIG.read(WFT_CONFIG_FILE)
WFT_URL = WFT_CONFIG.get('wft', 'url')
WFT_KEY = WFT_CONFIG.get('wft', 'key')
WFT_API_URL = "{}:8091".format(WFT_URL)
WFT_ATTACHMENT_URL = "{}:8091/api/v1/5G:WMP/5G_Central/builds".format(WFT_URL)
INTEGRATION_PROJ_REPO = 'MN/5G/COMMON/integration.git'


class BB_Mapping(object):
    """
    A Class to do operations on cloned integration/ repository
    """

    def __init__(self, package, mapping_file='', force_download=False, no_platform=False):
        self.package = package
        self.mapping_file = mapping_file if mapping_file else os.path.join(os.getcwd(), '{}.bbmap.json'.format(package))
        self.force_download = force_download
        self.mapping_dict = self.get_bb_mapping()
        self.src_list = self.mapping_dict['sources']
        self.no_platform = no_platform
        self.parser = self.get_mapping_parser()

    def get_mapping_parser(self):
        for src in self.src_list:
            if 'src_uri' in src and src['src_uri'].endswith(INTEGRATION_PROJ_REPO) \
                    or self.package.startswith('SBTS'):
                return yocto_mapping.Yocto_Mapping(self.mapping_dict)
        return origin_mapping.Origin_Mapping(self.mapping_dict, no_platform=self.no_platform)

    def get_bb_mapping(self):
        if not os.path.exists(self.mapping_file) or self.force_download:
            return self.get_bbmapping_from_wft()
        else:
            with open(self.mapping_file, 'r') as fr:
                return json.load(fr)

    def get_bbmapping_from_wft(self):
        wft_version = self.package
        if not self.package.startswith('SBTS'):
            version_part = self.package.split('_')[-1]
            stream_name = wft_tools.get_stream_name(version_part)
            wft_version = stream_name + '_' + version_part
            print('WFT version is {0}'.format(wft_version))
        bbmapping_id = wft_tools.get_build_bbmapping_id(wft_version)
        if not bbmapping_id:
            raise Exception('Cannot get bb_mapping id from {}'.format(wft_version))
        response = requests.get(
            '{}/{}/attachments/{}.json'.format(WFT_ATTACHMENT_URL, wft_version, bbmapping_id),
            params={'access_key': WFT_KEY})
        if response.ok:
            with open(self.mapping_file, 'w') as bb_mapping_fd:
                bb_mapping_fd.write(response.text)
            logging.info("Write WFT yocto_mapping to %s", self.mapping_file)
            with open(self.mapping_file, 'r') as fhandler_r:
                return json.loads(fhandler_r.read())
        raise Exception("WFT return {} when download {} bbmapping".format(response.status_code, self.package))

    def get_depended_files(self, comp_name, platform=''):
        return self.parser.get_depended_files(comp_name, platform)

    def get_component_value(self, comp_name, mapping_key):
        return self.parser.get_component_value(comp_name, mapping_key)

    def get_component_source(self, comp_name, platform=''):
        return self.parser.get_component_source(comp_name, platform=platform)

    def get_component_file(self, comp_name, platform=''):
        return self.parser.get_component_file(comp_name, platform=platform)

    def get_component_files(self, comp_name, platform=''):
        return self.parser.get_component_files(comp_name, platform=platform)

    def get_comp_value_by_keys(self, comp_name, keys):
        return self.parser.get_comp_value_by_keys(comp_name, keys)

    def get_integration_targets(self, comp_name):
        return self.parser.get_integration_targets(comp_name)
