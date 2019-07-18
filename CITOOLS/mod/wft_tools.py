import os
import json
import sys

import requests
import xml.etree.ElementTree as ET
from scm_tools.wft.api import WftAPI
from scm_tools.wft.build_content import BuildContent

from api import config


WFT = WftAPI(config_path=os.path.join(config.get_config_path(), 'properties/wft.properties'))
RELEASED_STATUS = ['released', 'released_with_restrictions']
BUILD_FILTER = "{wft_url}:8091/ALL/api/v1/build.json?" \
               "access_key={access_key}" \
               "&view[items]=20&view[sorting_field]=created_at&view[sorting_direction]=DESC" \
               "&view[columns[][id]]=deliverer.project.full_path&v" \
               "iew[columns[][id]]=deliverer.title" \
               "&view[columns[][id]]=version&view[columns[][id]]=branch.title" \
               "&view[columns[][id]]=state&view[columns[][id]]=planned_delivery_date" \
               "&view[columns[][id]]=common_links" \
               "&view[columns[][id]]=compare_link" \
               "&view[view_filters_attributes[243063142841311]][column]=version" \
               "&view[view_filters_attributes[243063142841311]][operation]=cont" \
               "&view[view_filters_attributes[243063142841311]][value][]={version}&"


def get_lasted_success_build(stream):
    success_state = [
        'released_for_quicktest',
        'released',
        'not_released',
        'released_with_restrictions',
        'skipped_by_qt'
    ]
    build_list = WFT.get_build_list(stream, items=100)
    xml_tree = ET.fromstring(build_list)
    for build in xml_tree.findall('build'):
        if build.find('state').text in success_state:
            return build.find('baseline').text, build.find('date').text
    return None, None


def get_latest_qt_passed_build(stream):
    build_list = WFT.get_build_list(branch_name=stream)
    root = ET.fromstring(build_list)
    build_name = ''
    release_date = ''
    for build in root.findall('build'):
        build_state = build.find('state').text
        if build_state in RELEASED_STATUS:
            release_date = build.find('date').text
            build_name = build.find('baseline').text
            break
    return build_name, release_date


def get_stream_name(version):
    stream = ''
    r = requests.get(BUILD_FILTER.format(wft_url=WFT.url, access_key=WFT.key, version=version))
    if r.status_code != 200:
        print('Failed to get build list with filter {0}'.format(version))
        sys.exit(1)
    build_list = json.loads(r.text.encode('utf-8'))
    for build in build_list['items']:
        if "INT" in build['branch.title']:
            continue
        stream = build['branch.title']
        break
    return stream


def get_release_date(package):
    package = package.strip()
    if package.startswith('5.3'):
        package_name = '5G19_' + package
    elif package.startswith('6.'):
        package_name = '5G19A_' + package
    else:
        package_name = '5G_' + package
    rs = WFT.get_build_content(package_name)
    tree = ET.fromstring(rs)
    for one in tree.findall("delivery_date"):
        return package, one.text


def get_newer_base_load(base_load_list):
    stream_build = dict()
    for base_load in base_load_list:
        build_name, release_date = get_release_date(base_load)
        if release_date:
            stream_build[release_date] = build_name
    release_time = stream_build.keys()
    release_time.sort(reverse=True)
    return stream_build[release_time[0]]


def get_latest_qt_load(stream_list):
    stream_build = dict()
    for stream in stream_list:
        stream = 'master_classicalbts_l1r51_tdd' if stream == 'default' \
            else get_stream_name(stream + '.')
        build_name, release_date = get_latest_qt_passed_build(stream)
        if not build_name:
            build_name, release_date = get_lasted_success_build(stream)
        stream_build[release_date] = build_name.split('_')[-1]
    time_stamp = stream_build.keys()
    time_stamp.sort(reverse=True)
    return stream_build[time_stamp[0]], stream_build.values()


def get_planed_delivery_date(baseline):
    build_content = BuildContent.get(baseline)
    return build_content.get_planned_delivery_date()
