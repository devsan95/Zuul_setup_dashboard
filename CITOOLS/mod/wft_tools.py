import os
import json

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


def get_latest_qt_passed_build(stream, status=None):
    build_list = WFT.get_build_list(branch_name=stream)
    root = ET.fromstring(build_list)
    build_name = ''
    release_date = ''
    release_status = [status] if status else RELEASED_STATUS
    for build in root.findall('build'):
        build_state = build.find('state').text
        if build_state in release_status:
            release_date = build.find('date').text
            build_name = build.find('baseline').text
            break
    return build_name, release_date


def get_build_list(stream):
    return WFT.get_build_list(branch_name=stream)


def get_build_list_from_custom_filter(custom_filter):
    return WFT.get_build_list_from_custom_filter(custom_filter)


def get_stream_name(version):
    stream = ''
    ignored_keywords = ['INT', 'lonerint', 'airphone']
    r = requests.get(BUILD_FILTER.format(wft_url=WFT.url, access_key=WFT.key, version=version))
    if r.status_code != 200:
        raise Exception('Failed to get build list with filter {0}'.format(version))
    build_list = json.loads(r.text.encode('utf-8'))
    for build in build_list['items']:
        for ignored_keyword in ignored_keywords:
            if ignored_keyword in build['branch.title']:
                break
        else:
            stream = build['branch.title']
            break
        continue
    print(stream)
    return stream


def get_release_date(package):
    rs = WFT.get_build_content(package)
    tree = ET.fromstring(rs)
    for one in tree.findall("delivery_date"):
        release_date = one.text
    if not release_date:
        release_date = get_planed_delivery_date(package)
    return package, release_date


def get_wft_release_name(version):
    stream_name = get_stream_name(version)
    latest_build, release_date = get_lasted_success_build(stream_name)
    if latest_build:
        return latest_build.split('_')[0] + '_' + version
    else:
        raise Exception("Can't find WFT name for {0}".format(version))


def get_newer_base_load(base_load_list):
    stream_build = dict()
    for base_load in base_load_list:
        package_name = get_wft_release_name(base_load)
        build_name, release_date = get_release_date(package_name)
        if release_date:
            stream_build[release_date] = build_name
    release_time = stream_build.keys()
    release_time.sort(reverse=True)
    newer_base_load = stream_build[release_time[0]]
    for base_load in base_load_list:
        if base_load in newer_base_load:
            return base_load
    raise Exception("Can't find newer base load from {0}".format(base_load_list))


def get_latest_loads_by_streams(stream_list, get_build_function, strip_prefix=True):
    stream_build = dict()
    for stream in stream_list:
        wft_stream = ''
        try:
            wft_stream = get_stream_name(stream + '.')
        except Exception:
            print('Not find stream name for {}'.format(stream))
            continue
        stream = 'master_classicalbts_l1r51_tdd' if stream == 'default' \
            else wft_stream
        if not stream:
            continue
        print('Get pcakge for stream {}'.format(stream))
        build_name, release_date = get_build_function(stream)
        if not build_name:
            build_name, release_date = get_build_function(stream)
        if build_name:
            if strip_prefix:
                stream_build[release_date] = build_name.split('_')[-1]
            else:
                stream_build[release_date] = build_name
    time_stamp = stream_build.keys()
    time_stamp.sort(reverse=True)
    return stream_build[time_stamp[0]], stream_build.values()


def get_latest_build_load(stream_list, strip_prefix=True):
    return get_latest_loads_by_streams(stream_list, get_lasted_success_build, strip_prefix)


def get_latest_qt_load(stream_list, strip_prefix=True):
    return get_latest_loads_by_streams(stream_list, get_lasted_success_build, strip_prefix)


def get_planed_delivery_date(baseline):
    build_content = BuildContent.get(baseline)
    return build_content.get_planned_delivery_date()


def get_ps(baseline):
    build_content = BuildContent.get(baseline)
    return build_content.get_ps()


def get_subuild_from_wft(wft_name, component=None):
    build_content = ''
    sub_builds = []
    try:
        build_content = WFT.get_build_content(wft_name)
    except Exception:
        if component:
            for project in ["5G", "Common", "ALL"]:
                print('Try to get from WFT, version:%s, component:%s, project:%s',
                      wft_name, component, project)
                try:
                    build_content = WFT.get_build_content(wft_name, component=component, project=project)
                except Exception:
                    print('Cannot get get from WFT, version:%s, component:%s, project:%s',
                          wft_name, component, project)
    if build_content:
        tree = ET.fromstring(build_content)
        for one in tree.findall("content/baseline"):
            sub_build = {}
            sub_build['version'] = one.text
            sub_build['project'] = one.attrib['project']
            sub_build['component'] = one.attrib['component']
            sub_builds.append(sub_build)
        for one in tree.findall("peg_revisions/peg_revision"):
            sub_build = {}
            sub_build['version'] = one.text
            sub_build['project'] = one.attrib['project']
            sub_build['component'] = one.attrib['sc']
            sub_builds.append(sub_build)
    else:
        raise Exception('Cannot find from WFT version:{}, component:{}'.format(wft_name, component))
    return sub_builds
