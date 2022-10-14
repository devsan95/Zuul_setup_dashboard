import os
import re
import json
import git
import shutil
import time

import requests
import ruamel.yaml as yaml
import xml.etree.ElementTree as ET
from scm_tools.wft.api import WftAPI
from scm_tools.wft.build_content import BuildContent

from api import config
from api import retry


WFT = WftAPI(config_path=os.path.join(config.get_config_path(), 'properties/wft.properties'))
RELEASED_STATUS = ['released', 'released_with_restrictions']
BUILD_FILTER = "{wft_url}:8091/ALL/api/v1/build.json?" \
               "access_key={access_key}" \
               "&view[items]=20&view[sorting_field]=created_at&view[sorting_direction]=DESC" \
               "&view[columns[][id]]=deliverer.project.full_path" \
               "&view[columns[][id]]=deliverer.title" \
               "&view[columns[][id]]=version&view[columns[][id]]=branch.title" \
               "&view[columns[][id]]=state&view[columns[][id]]=planned_delivery_date" \
               "&view[columns[][id]]=common_links" \
               "&view[columns[][id]]=compare_link" \
               "&view[view_filters_attributes[438525425682223]][column]=version" \
               "&view[view_filters_attributes[438525425682223]][operation]=cont" \
               "&view[view_filters_attributes[438525425682223]][value][]={version}" \
               "&view[view_filters_attributes[208462639699611]][column]=deliverer.title" \
               "&view[view_filters_attributes[208462639699611]][operation]=eq" \
               "&view[view_filters_attributes[208462639699611]][value][]=CI_CRAN&"
PKG_REGEX_FOR_5G = r"(5G|vDUCNF|vCUCNF|CUCNF|CUVNF|VDU|pDU)[0-9,A-Z]+_[0-9]+\.[0-9]+\.[0-9]"
inherit_json = '''{
  "page": "",
  "items": "20",
  "sorting_field": "created_at",
  "sorting_direction": "DESC",
  "group_by": "",
  "group_by_processor": "",
  "columns": {
    "0": {
      "id": "deliverer.project.full_path"
    },
    "1": {
      "id": "deliverer.title"
    },
    "2": {
      "id": "version"
    },
    "3": {
      "id": "branch.title"
    },
    "4": {
      "id": "state"
    },
    "5": {
      "id": "build_deliverers"
    }
  },
  "projects": [
    "ALL"
  ],
  "view_filters_attributes": {
    "0": {
      "column": "version",
      "operation": "eq",
      "value": "%(build)s",
      "parameter": ""
    }
  },
  "access_key": "%(wft_key)s"
}
'''


def get_lasted_success_build(stream):
    success_state = [
        'released_for_quicktest',
        'released',
        'not_released',
        'released_with_restrictions',
        'skipped_by_qt'
    ]
    return get_latest_build_by_state(stream, success_state, with_yocto_map=True)


def get_latest_qt_passed_build(stream, status=None):
    release_status = [status] if status else RELEASED_STATUS
    return get_latest_build_by_state(stream, release_status)


def get_latest_build_by_state(stream, release_status, with_yocto_map=False):
    build_name = ''
    release_date = ''
    build_list = get_build_list(stream)
    root = ET.fromstring(build_list)
    for build in root.findall('build'):
        build_state = build.find('state').text
        build_wft_name = build.find('baseline').text
        if build_state in release_status and is_central_package(build_wft_name):
            if with_yocto_map:
                if not get_build_bbmapping_id(build_wft_name):
                    continue
            release_date = build.find('date').text
            build_name = build_wft_name
            break
    print('Get build name: {}'.format(build_name))
    print('Get release date: {}'.format(release_date))
    return build_name, release_date


def is_central_package(build_wft_name):
    if re.match(PKG_REGEX_FOR_5G, build_wft_name):
        return True
    if build_wft_name.startswith('SBTS'):
        return True
    return False


def get_build_list(stream, items=100):
    return WFT.get_build_list(branch_name=stream, baseline_type=0, items=items)


def get_build_list_from_custom_filter(custom_filter):
    return WFT.get_build_list_from_custom_filter(custom_filter)


def get_stream_name(version):
    to_path = '{}/comp-deps-tmp'.format(os.environ["WORKSPACE"])
    if os.path.exists(to_path):
        shutil.rmtree(to_path)
    git.Repo.clone_from(
        url='http://gerrit.ext.net.nokia.com/gerrit/MN/SCMTA/zuul/comp-deps',
        to_path=to_path
    )
    yaml_path = '{}/config/integration-config.yaml'.format(to_path)
    comp_config = yaml.load(open(yaml_path), Loader=yaml.Loader, version='1.1')
    for stream in comp_config['streams']:
        if version.startswith(stream["value"]):
            return stream["name"]
    raise Exception('Can not get {} stream name from comp-deps repo'.format(version))


def get_repository_info(package):
    rs = WFT.get_build_content(get_wft_release_name(package))
    tree = ET.fromstring(rs)
    repository_info = {}
    for key_name in ['url', 'branch', 'revision', 'type']:
        repository_key = 'repository_{}'.format(key_name)
        for one in tree.findall(repository_key):
            repository_info[key_name] = one.text
            break
    return repository_info


def get_release_date(package):
    rs = WFT.get_build_content(package)
    tree = ET.fromstring(rs)
    for one in tree.findall("delivery_date"):
        release_date = one.text
    if not release_date:
        release_date = get_planed_delivery_date(package)
    return package, release_date


def get_wft_release_name(version):
    if version.startswith('SBTS') or '_' in version:
        return version
    stream_name = get_stream_name(version)
    build_list = get_build_list(stream_name, items=1000)
    root = ET.fromstring(build_list)
    oldest_build = ''
    for build in root.findall('build'):
        build_wft_name = build.find('baseline').text
        if is_central_package(build_wft_name):
            build_name = build_wft_name
            if build_name.endswith(version):
                oldest_build = build_name
                break
            else:
                oldest_build = build_name
    if oldest_build:
        return oldest_build.split('_')[0] + '_' + version
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
        stream_pattern = stream
        try:
            wft_stream = get_stream_name(stream + '.')
        except Exception:
            print('Not find stream name for {}'.format(stream))
            continue
        stream = 'master_classicalbts_l1r51_tdd' if stream == 'default' \
            else wft_stream
        if not stream:
            continue
        print('Get package for stream {}'.format(stream))
        build_name, release_date = get_build_function(stream)
        if '_{}'.format(stream_pattern) not in build_name and '{}_'.format(stream_pattern) not in build_name:
            raise Exception('{} is not aligned with {}'.format(build_name, stream))
        if not build_name:
            raise Exception('Build is not find from WFT for {}'.format(stream))
        if strip_prefix:
            stream_build[release_date] = build_name.split('_')[-1]
        else:
            stream_build[release_date] = build_name
    time_stamp = stream_build.keys()
    time_stamp.sort(reverse=True)
    return stream_build[time_stamp[0]], stream_build.values()


def get_latest_build_load(stream_list, strip_prefix=True):
    latest_builds = retry.retry_func(
        retry.cfn(get_latest_loads_by_streams, stream_list, get_lasted_success_build, strip_prefix),
        max_retry=5, interval=3)
    return latest_builds


def get_latest_qt_load(stream_list, strip_prefix=True):
    return get_latest_loads_by_streams(stream_list, get_lasted_success_build, strip_prefix)


def get_planed_delivery_date(baseline):
    build_content = BuildContent.get(baseline)
    delivery_date = build_content.get_planned_delivery_date()
    if isinstance(delivery_date, str):
        return delivery_date
    else:
        return delivery_date.strftime('%Y-%m-%d %H:%M:%S %Z')


def get_ps(baseline):
    build_content = BuildContent.get(baseline)
    return build_content.get_ps()


def get_poject_and_component(wft_name):
    build_content = ''
    time.sleep(5)
    try:
        build_content = retry.retry_func(retry.cfn(WFT.get_build_content, wft_name), max_retry=5, interval=5)
    except Exception:
        print('Cannot get build_content for {}'.format(wft_name))
    if not build_content:
        return None, None
    tree = ET.fromstring(build_content)
    component = tree.find('component').text
    project = tree.find('project').text
    return project, component


def get_staged_from_wft(wft_name, component=None, project=None):
    build_content = ''
    time.sleep(2)
    try:
        if component and project:
            build_content = retry.retry_func(retry.cfn(WFT.get_build_content, wft_name, component, project), max_retry=5, interval=3)
        else:
            build_content = retry.retry_func(retry.cfn(WFT.get_build_content, wft_name), max_retry=5, interval=3)
    except Exception:
        print('Cannot get build_content for {}'.format(wft_name))
    if not build_content:
        return {}
    tree = ET.fromstring(build_content)
    bbrecipe = tree.find('bbrecipe')
    if bbrecipe is not None:
        bbrecipe_location = bbrecipe.get("location", '')
        bbrecipe_commit = bbrecipe.get("commit", '')
        bbrecipe_type = bbrecipe.get("type", '')
        print('bbrecipe: location="{}" type="{}" commit="{}"'.format(
              bbrecipe_location, bbrecipe_type, bbrecipe_commit))
        return {'location': bbrecipe_location,
                'type': bbrecipe_type,
                'commit': bbrecipe_commit}
    return {}


def get_subuild_from_wft(wft_name, component=None, project=None):
    time.sleep(2)
    build_content = ''
    sub_builds = []
    project_list = ["5G", "Common", "ALL"]
    try:
        build_content = WFT.get_build_content(wft_name)
    except Exception:
        if component:
            if project:
                project_list = [project]
            for proj_name in project_list:
                print('Try to get from WFT, version:{}, component:{}, project:{}'.format(wft_name, component, proj_name))
                try:
                    build_content = WFT.get_build_content(wft_name, component=component, project=proj_name)
                    break
                except Exception:
                    print('Cannot get get from WFT, version:{}, component:{}, project:{}'.format(wft_name, component, proj_name))
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


def get_build_config(base_wft_name):
    print("Try download build configration!")
    build_config = requests.get(
        '{}:8091/ext/build_config/{}'.format(WFT.url, base_wft_name),
        params={'access_key': WFT.key},
    )
    if not build_config.ok:
        print(build_config)
        raise Exception("Get {}'s build config failed!".format(base_wft_name))
    return build_config.text


def get_subbuilds(build):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    wft_url = "{}:8091/ALL/api/v1/build.json".format(WFT.url)
    values = {"build": build, "wft_key": WFT.key}
    response = requests.post(wft_url, headers=headers, data=inherit_json % values, verify=False)
    if not response.ok:
        return []
    return json.loads(response.text)['items'][0]['build_deliverers']


def get_build_bbmapping_id(wft_version):
    attachement_url = "{}:8091/api/v1/5G:WMP/5G_Central/builds/{}/attachments.json".format(WFT.url, wft_version)
    response = requests.get(attachement_url, params={'access_key': WFT.key})
    if response.ok:
        for attachment in json.loads(response.text):
            if attachment['attachment_file_name'] == 'bb_mapping.json' or \
                    attachment['attachment_type'] == 'yocto_mapping':
                return attachment['id']
    else:
        print("WFT return %s when get %s attachments", response.status_code, wft_version)
        print(response)
    return False


def get_subbuild_version(wft_name, subbuild, component='', project='', ):
    sub_builds = get_subuild_from_wft(wft_name=wft_name, component=component, project=project)
    for sub_build in sub_builds:
        if sub_build['component'] == subbuild:
            return sub_build['version']
    return None
