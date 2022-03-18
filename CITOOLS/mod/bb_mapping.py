import os
import json
import logging
import requests
from six.moves import configparser
from api import config
from mod import origin_mapping
from mod import yocto_mapping

# in ci-scripsts this will be get from ENV
WFT_CONFIG_FILE = os.path.join(config.get_config_path(), 'properties/wft.properties')
WFT_CONFIG = configparser.ConfigParser()
WFT_CONFIG.read(WFT_CONFIG_FILE)
WFT_URL = WFT_CONFIG.get('wft', 'url')
WFT_KEY = WFT_CONFIG.get('wft', 'key')
WFT_API_URL = "{}:8091".format(WFT_URL)
WFT_ATTACHMENT_URL = "{}:8091/api/v1/5G:WMP/5G_Central/builds".format(WFT_URL)
WFT_SEARCH_BUILD = "{}/5G:WMP/api/v1/build.json?" \
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
    "&view[view_filters_attributes[24216713295283]][value][]=%5E(5G%7CvDU%7CvCU%7CVDU%7CCUCNF%7CCUVNF%7CpDU)%5B0-9a-zA-Z%5D*_{}%5Cz&"
HTTP_HEADERS = {'Content-Type': 'application/json', 'Accept': 'application/json'}
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

    def search_build_on_wft(self):
        response = requests.get(
            WFT_SEARCH_BUILD.format(WFT_API_URL, WFT_KEY, self.package),
            headers=HTTP_HEADERS
        )
        if response.ok:
            try:
                build_list = json.loads(response.text)['items']
            except Exception:
                logging.warn("Can not find build %s on WFT", self.package)
                return False
            if len(build_list) == 1:
                logging.info('Get build list : %s', build_list)
                return build_list[0]["version"]
            else:
                logging.warn("Multiple builds are found on WFT for %s", self.package)
                return False
        else:
            logging.warn("WFT return %s when search %s", response.status_code, self.package)
            return False

    def get_bbmapping_from_wft(self):
        wft_version = self.package
        if not self.package.startswith('SBTS'):
            wft_version = self.search_build_on_wft()
            if not wft_version:
                raise Exception('Cannot get wft name for {}'.format(self.package))
        bbmapping_id = get_build_bbmapping_id(wft_version)
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


def get_build_bbmapping_id(wft_version):
    attachement_url = "{}/{}/attachments.json".format(WFT_ATTACHMENT_URL, wft_version)
    response = requests.get(attachement_url, params={'access_key': WFT_KEY})
    if response.ok:
        for attachment in json.loads(response.text):
            if attachment['attachment_file_name'] == 'bb_mapping.json' or \
                    attachment['attachment_type'] == 'yocto_mapping':
                return attachment['id']
    else:
        logging.warn("WFT return %s when get %s attachments", response.status_code, wft_version)
        logging.warn(response)
    return False
