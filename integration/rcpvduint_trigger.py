#!/usr/bin/env python
import os
import sys
import re
import codecs
import time
import json
import argparse
import logging
import jenkins
import requests
from api import gerrit_rest
from scm_tools.wft.api import WftAPI


wft = WftAPI()
integration = 'MN/5G/COMMON/integration'
wft_api = '{}/ALL/api/v1/build.json'.format(os.environ['WFT_API_URL'])
jenkins_server = 'http://wrlinb147.emea.nsn-net.net:9090/'
knife_job = 'Knives.START'
mail_job = 'vran.mail_notification.CI'
download_list = [
    'http://es-si-s3-z4.eecloud.nsn-net.net/5g-cb/BucketList/index.html?prefix=knife/',
    'http://s3-china-1.eecloud.nsn-net.net/5g-cb/BucketList/index.html?prefix=knife/'
]
filter_str = '''
{
  "page": "",
  "items": "1",
  "sorting_field": "created_at",
  "sorting_direction": "DESC",
  "group_by": "",
  "group_by_processor": "",
  "columns": {
    "0": {
      "id": "version"
    },
    "1": {
      "id": "branch.title"
    },
    "2": {
      "id": "state"
    },
    "3": {
      "id": "planned_delivery_date"
    }
  },
  "projects": [
    "5G:WMP"
  ],
  "view_filters_attributes": {
    "0": {
      "column": "branch.title",
      "operation": "eq",
      "value": [
        "%(branch)s"
      ],
      "parameter": ""
    }%(version)s
  },
  "access_key": "%(WFT_KEY)s"
}
'''


def get_latest_build(branch, build_status=None):
    if build_status:
        ver_filter = build_status
    else:
        ver_filter = ""
    values = {
        'branch': branch,
        'version': ver_filter,
        'WFT_KEY': os.environ['WFT_KEY']
    }
    str_filter = filter_str % values
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    response = requests.post(
        wft_api,
        headers=headers,
        data=str_filter,
        verify=False
    )
    if not response.ok:
        log.error("get latest build from wft error!")
        sys.exit(1)
    return json.loads(response.text)['items'][0]['version']


def create_integration_change():
    version_filter = '''
,
    "1": {
      "column": "state",
      "operation": "eq_any",
      "value": ["RELEASED", "RELEASED_WITH_RESTRICTIONS"],
      "parameter": ""
    }
'''
    latest_ver = get_latest_build("master_allincloud_int", version_filter)
    log.info("The latest released build is {}".format(latest_ver))
    parent_id = rest.get_tag(
        integration,
        latest_ver.replace('5G_', '')
    )['object']
    change = rest.create_ticket(
        integration,
        '',
        'master',
        'rcpvduint trigger',
        base_change=parent_id
    )[1]
    log.info("ticket id is {}".format(change))
    return change, latest_ver


def arguments():
    parse = argparse.ArgumentParser()
    parse.add_argument(
        '--changes',
        '-c',
        required=True,
        help="--rcp versions"
    )
    parse.add_argument(
        '--mails',
        '-m',
        required=True,
        help="--receiver mail list"
    )
    parse.add_argument(
        '--gerrit',
        '-g',
        required=True,
        help="--gerrit_info_path"
    )
    return parse.parse_args()


def update_env_file():
    env_path = 'env/env-config.d/ENV'
    env_content = rest.get_file_content(env_path, change_id)
    log.debug(env_content)
    for item in version_dict:
        if re.search(r'\n *{}=[^\n]*\n'.format(item), env_content):
            log.info("update {} version".format(item))
            env_content = re.sub(
                r'\n *{}=[^\n]*\n'.format(item),
                '\n{}={}\n'.format(item, version_dict[item]),
                env_content
            )
        else:
            log.error("Can not find {} from env file!".format(item))
            sys.exit(1)
    rest.add_file_to_change(change_id, env_path, env_content)
    rest.publish_edit(change_id)
    commit_hash = rest.get_commit(change_id)['commit']
    log.info("ticket {}'s hash is {}".format(change_id, commit_hash))
    return commit_hash


def generate_releasenote():
    json_file = '5G_{}.json'.format(
        tar_pkg.replace('knifeanonymous', 'RCPVDUINT')
    )
    latest_ver = get_latest_build("RCPVDUINT")
    log.info("RCPVDUINT latest build: {}".format(latest_ver))
    releasenote = wft.get_json_releasenote(latest_build)
    note = json.loads(releasenote)
    log.info("Generate new releasenote {}".format(json_file))
    note['releasenote']['baseline']['basedOn']['version'] = latest_ver
    note['releasenote']['baseline']['branch'] = 'RCPVDUINT'
    note['releasenote']['baseline']['branchFor'] = ['RCPVDUINT']
    note['releasenote']['baseline']['homepage'] = build_url
    note['releasenote']['baseline']['version'] = '5G_' \
        + tar_pkg.replace('knifeanonymous', 'RCPVDUINT')
    old_downloads = note['releasenote']['baseline'].pop('download')
    downloads = list()
    elements = list()
    for item in old_downloads:
        if not item["path"].startswith('http'):
            item['name'] = description
            item["path"] = item["path"].replace(
                latest_build.replace('5G_', ''),
                description
            )
            downloads.append(item)
    for download in download_list:
        downloads.append(
            {
                'name': tar_pkg,
                'path': download + tar_pkg,
                'storage': 'S3'
            }
        )
    old_elements = note['releasenote'].pop('element_list')
    for comp in old_elements:
        for item in version_dict:
            if comp['name'] == item.replace('ENV_', ''):
                log.debug(version_dict[item])
                comp['version'] = version_dict[item]
                break
        elements.append(comp)
    note['releasenote']['baseline']['download'] = downloads
    note['releasenote']['element_list'] = elements
    json_str = json.dumps(
        note,
        encoding="utf-8",
        sort_keys=True,
        indent=4,
        separators=(',', ': ')
    )
    with open(json_file, 'w') as f:
        f.write(json_str)
    wft.json(json_file)


def trigger_mail_job():
    params = {
        'mails': args.mails,
        'baseline': "5G_{}".format(
            tar_pkg.replace('knifeanonymous', 'RCPVDUINT')
        ),
        'identifier': 'RCPVDUINT'
    }
    trigger_jenkins_job(mail_job, params, 15)


def trigger_jenkins_job(job_name, params, interval_time):
    log.info("start trigger {} job.".format(job_name))
    queue_id = server.build_job(
        job_name,
        parameters=params,
        token='secretOnlyKnownByWFT'
    )
    while True:
        queue_info = server.get_queue_item(queue_id)
        if 'executable' in queue_info:
            build_id = queue_info['executable']['number']
            break
        time.sleep(90)
    log.info("{} build #{} start".format(job_name, build_id))
    build_info = dict()
    while True:
        build_info = server.get_build_info(job_name, build_id)
        if not build_info['building']:
            break
        time.sleep(interval_time)
    log.info("{} build #{} {}".format(job_name, build_id, build_info['result']))
    return build_id, build_info


def setup_logger(debug="False"):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s:\t%(module)s@%(lineno)s:\t%(message)s'
    )
    ch = logging.StreamHandler()
    if debug.lower() == "true":
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.WARNING)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


def trigger_knife_job():
    desc = None
    url = None
    params = {
        'MAIL_LIST': args.mails,
        'KNIFE_JSON': '{ "integration": {"repo_ver": "%s"} }' % change_hash,
        'FORCED_LABEL': 'cores-beast-knife',
        'BASE_PACKAGE': latest_build.replace('5G_', '')
    }
    build_id, build_info = trigger_jenkins_job(knife_job, params, 512)
    tar_pkg_name = ''
    with codecs.open('console.log', 'w+', 'utf-8') as f:
        f.write(server.get_build_console_output(knife_job, build_id))
        f.seek(0)
        for line in f:
            if 'PKG_NAME={}'.format(latest_build.replace('5G_', '')) in line:
                print(line)
                tar_pkg_name = line.split('=')[1].strip()
                break
    if build_info['result'] == 'SUCCESS':
        desc = build_info['description']
        url = build_info['url']
    return desc, url, tar_pkg_name


def get_version_dict(versions):
    ver_dict = dict()
    log.info("Start parse rcp change versions.")
    for line in versions.split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            key = line.split('=', 1)[0].strip().upper()
            value = line.split('=', 1)[1].strip()
            log.info("{}: {}".format(key, value))
            ver_dict[key] = value
    return ver_dict


if __name__ == "__main__":
    args = arguments()
    server = jenkins.Jenkins(jenkins_server)
    log = setup_logger(debug="True")
    rest = gerrit_rest.init_from_yaml(args.gerrit)
    version_dict = get_version_dict(args.changes)
    change_id, latest_build = create_integration_change()
    change_hash = update_env_file()
    description, build_url, tar_pkg = trigger_knife_job()
    if description and build_url:
        generate_releasenote()
        trigger_mail_job()
    rest.abandon_change(change_id)
