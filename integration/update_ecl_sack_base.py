#! /usr/bin/env python
import os
import git
import argparse
import requests
import json
import yaml
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from api import gerrit_rest, log_api
from scm_tools.wft.api import WftAPI


log = log_api.get_console_logger("update_ecl_sack_base")
branch_match = {"master": "5G00_ECL_SACK_BASE", "rel/5G20A_B1": "5G20A_B1_ECL_SACK_BASE"}
WFT_API_URL = os.environ['WFT_API_URL']
WFT_KEY = os.environ['WFT_KEY']
wft_api = '{}/ALL/api/v1/build.json'.format(os.environ['WFT_API_URL'])
filter_str = '''
{
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
      "id": "branches_title"
    }
  },
  "projects": [
    "ALL"
  ],
  "view_filters_attributes": {
    "0": {
      "column": "%(item)s",
      "operation": "eq",
      "value": [
        "%(value)s"
      ],
      "parameter": ""
    }
  },
  "access_key": "%(WFT_KEY)s"
}
'''
increment = '''
{
  "parent_version": "%(current_version)s",
  "parent_component": "ECL_SACK_BASE",
  "parent_project": "Common",
  "branch": "%(branch)s",
  "branch_for": %(branch_for)s,
  "increment": [ ],
  "access_key": "%(WFT_KEY)s"
}
'''
headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
inherit_comp = ["PS:PS_LFS_REL", "Common:GLOBAL_ENV"]


def get_latest_ecl_sack_base_from_wft(branch):
    values = {'value': branch, 'item': "branch.title", 'WFT_KEY': WFT_KEY}
    str_filter = filter_str % values
    response = requests.post(
        wft_api,
        headers=headers,
        data=str_filter,
        verify=True
    )
    if not response.ok:
        log.error(response.text)
        raise Exception("Failed to get latest version of ECL_SACK_BASE from WFT")
    versions_dict = json.loads(response.text)['items']
    version = versions_dict[0]['version']
    branch_for = versions_dict[0]['branches_title']
    log.info("Latest version of ECL_SACK_BASE in WFT is: {}".format(version))
    return version, branch_for, versions_dict


def arguments():
    parse = argparse.ArgumentParser()
    parse.add_argument('--change_no', '-c', required=True, help="change id")
    parse.add_argument('--branch', '-b', required=True, help="branch")
    parse.add_argument('--gerrit_yaml', '-g', required=True, help="gerrit_yaml")
    parse.add_argument(
        '--framework_only',
        '-f',
        action='store_true',
        default=False,
        help='create new ECL_SACK_BASE for integration framework change only'
    )
    return parse.parse_args()


def get_latest_ecl_sack_base_content(branch):
    data = {'accept': 'text/legacy', 'access_key': WFT_KEY}
    if branch in branch_match:
        wft_branch = branch_match[branch]
    else:
        raise Exception("No gerrit branch and wft branch match info!")
    log.info("ecl_sack_base's wft branch: {}".format(wft_branch))
    current_version, branch_for, versions_dict = get_latest_ecl_sack_base_from_wft(wft_branch)
    url = "{}/api/v1/Common/ECL_SACK_BASE/builds/{}.json?items[]=sub_builds".format(
        WFT_API_URL, current_version
    )
    response = requests.get(url, data)
    if not response.ok:
        log.error(response.text)
        raise Exception("Failed to get content of latest ECL_SACK_BASE from WFT")
    sub_builds = json.loads(response.text)["sub_builds"]
    log.info("Latest ECL_SACL_BASE content:\n{}".format(sub_builds))
    log.info("Latest ECL_SACK_BASE branch_for: {}".format(branch_for))
    return current_version, sub_builds, wft_branch, branch_for, versions_dict


def ecl_increment(current_version, change, branch, branch_for, versions_dict):
    if not change:
        log.warning("No difference between ENV and latest ECL_SACK_BASE, no need to create")
        return
    new_version = generate_new_version(versions_dict)
    var = {
        "current_version": current_version,
        "branch": branch,
        "branch_for": json.dumps(branch_for),
        "WFT_KEY": WFT_KEY
    }
    increment_info = json.loads(increment % var)
    increment_info['increment'] = change
    url = "{}/api/v1/Common/ECL_SACK_BASE/builds/{}/increment.json".format(
        WFT_API_URL, new_version
    )
    response = requests.post(
        url,
        headers=headers,
        data=json.dumps(increment_info),
        verify=True
    )
    if not response.ok:
        log.error(response.text)
        raise Exception("Failed to increment new ECL_SACK_BASE in WFT")
    log.info("New ECL_SACK_BASE {} created in WFT successfully.".format(new_version))


def get_config_yaml_dict(rest, change_no):
    branch = rest.get_ticket(change_no)['branch']
    path = os.path.join(os.environ["WORKSPACE"], "integration")
    if os.path.exists(path):
        log.info("Remove dir: {}".format(path))
        shutil.rmtree(path)
    log.info('Clone integration repo...')
    repo = git.Repo.clone_from(url=os.environ['INTEGRATION_REPO_URL'], to_path=path)
    integration = repo.git
    integration.checkout(branch)
    with open(os.path.join(path, "config.yaml"), 'r') as config:
        config_yaml = yaml.safe_load(config)
    log.info('config_yaml dict: {}'.format(config_yaml['components']))
    return config_yaml['components']


def get_component_name(version):
    component = '-'
    values = {'value': version, 'item': "version", 'WFT_KEY': WFT_KEY}
    str_filter = filter_str % values
    response = requests.post(
        wft_api,
        headers=headers,
        data=str_filter,
        verify=True
    )
    if not response.ok:
        log.error("Failed to get component name for {} from WFT".format(version))
        log.error(response.text)
        return component
    response_dict = json.loads(response.text)
    if response_dict['total'] == 1:
        component = json.loads(response.text)['items'][0]['deliverer.title']
    log.info("current version is: {}".format(version))
    return component


def generate_new_version(versions_dict):
    version_list = list()
    for version_dict in versions_dict:
        log.info(version_dict['version'])
        version_list.append(version_dict['version'])
    version_list.sort(reverse=True)
    version = version_list[0]
    date_now = datetime.strftime(datetime.now(), '%Y%m%d')[2:]
    latest_version_date = version.split("_")[-2:-1][0]
    if date_now == latest_version_date:
        release_id = int(version.split("_")[-1]) + 1
    else:
        release_id = 1
    new_version = "{0}_{1}_{2:06d}".format(
        "_".join(version.split("_")[:-2]),
        date_now,
        release_id
    )
    log.info("new ecl_sack_base: {}".format(new_version))
    return new_version


def get_diff(config_yaml_dict, sub_builds):
    wft = WftAPI()
    diff_list = list()
    for sub_build in sub_builds:
        config_key = "{}:{}".format(sub_build['project'], sub_build['component'])
        if config_key in config_yaml_dict \
                and config_key not in inherit_comp \
                and sub_build['version'] != config_yaml_dict[config_key]["version"]:
            diff = dict()
            diff["version"] = config_yaml_dict[config_key]["version"]
            diff["project"] = sub_build["project"]
            diff["component"] = sub_build['component']
            try:
                ET.fromstring(wft.get_build_content(config_yaml_dict[config_key]["version"]))
            except Exception:
                log.warning('Cannot find {} in wft'.format(config_yaml_dict[config_key]["version"]))
            else:
                diff_list.append(diff)
        else:
            log.info("{} do not need update.".format(sub_build['component']))
    log.debug("ENV change list: {}".format(diff_list))
    return diff_list


def whether_integration_ticket(rest, framework, change_no):
    if framework:
        commit_msg = rest.get_commit(change_no)['message']
        if "%JR=SCMHGH-" in commit_msg and "%FIFI=" in commit_msg:
            log.info(
                "{} is integration framework change, need to create new ECL_SACK_BASE".format(
                    change_no
                )
            )
            return True
        else:
            log.info(
                "{} is not integration framework change, no need to create new ECL_SACK_BASE".format(
                    change_no
                )
            )
            return False
    else:
        return True


def main():
    args = arguments()
    rest = gerrit_rest.init_from_yaml(args.gerrit_yaml)
    if not whether_integration_ticket(rest, args.framework_only, args.change_no):
        return
    config_yaml_dict = get_config_yaml_dict(rest, args.change_no)
    latest_version, sub_build_list, branch_wft, branch_for, versions_dict = get_latest_ecl_sack_base_content(args.branch)
    change_list = get_diff(config_yaml_dict, sub_build_list)
    ecl_increment(latest_version, change_list, branch_wft, branch_for, versions_dict)


if __name__ == "__main__":
    main()
