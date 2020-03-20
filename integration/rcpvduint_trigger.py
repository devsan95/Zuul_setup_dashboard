#!/usr/bin/env python
import os
import re
import codecs
import time
import json
import argparse
import jenkins
import requests
from api import gerrit_rest, log_api
from scm_tools.wft.api import WftAPI


log = log_api.get_console_logger("rcpvduint_knife")
wft = WftAPI()
integration = 'MN/5G/COMMON/integration'
wft_api = '{}/ALL/api/v1/build.json'.format(os.environ['WFT_API_URL'])
jenkins_server = 'http://wrlinb147.emea.nsn-net.net:9090/'
knife_job = 'Knives.START'
mail_job = 'vran.mail_notification.CI'
server = jenkins.Jenkins(jenkins_server)
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
        raise Exception("get latest build from wft error!")
    return json.loads(response.text)['items'][0]['version']


def create_integration_change(rest):
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
    change = rest.create_ticket(
        integration,
        '',
        'master',
        'rcpvduint trigger',
        base_change=None
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


def update_env_file(rest, version_dict, change_id):
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
            raise Exception("Can not find {} from env file!".format(item))
    rest.add_file_to_change(change_id, env_path, env_content)
    rest.publish_edit(change_id)
    commit_hash = rest.get_commit(change_id)['commit']
    log.info("ticket {}'s hash is {}".format(change_id, commit_hash))
    return commit_hash


def generate_releasenote(version_dict, latest_build, tar_pkg, build_url, description):
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
        if "/System_Release/" not in item["path"]:
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


def trigger_mail_job(mails, tar_pkg):
    params = {
        'mails': mails,
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
    try_time = 0
    while True:
        try:
            queue_info = server.get_queue_item(queue_id)
        except Exception:
            try_time += 1
            if try_time > 200:
                raise Exception("Get queue_info error,no more tries left")
            log.warining("Get queue_info error, try again.")
            time.sleep(20)
            continue
        if 'executable' in queue_info:
            build_id = queue_info['executable']['number']
            break
        time.sleep(70)
    log.info("{} build #{} start".format(job_name, build_id))
    build_info = dict()
    try_time = 0
    while True:
        try:
            build_info = server.get_build_info(job_name, build_id)
        except Exception:
            try_time += 1
            if try_time > 400:
                raise Exception("Get build_info error,no more tries left")
            log.warining("Get build_info error, try again.")
            time.sleep(30)
            continue
        if not build_info['building']:
            break
        time.sleep(interval_time)
    log.info("{} build #{} {}".format(job_name, build_id, build_info['result']))
    return build_id, build_info


def trigger_knife_job(rest, mails, latest_build, change_hash, change_id):
    desc = None
    url = None
    params = {
        'MAIL_LIST': mails,
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
    else:
        rest.abandon_change(change_id)
        raise Exception("Knife job failed: {}".format(build_info['url']))
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


def main():
    args = arguments()
    rest = gerrit_rest.init_from_yaml(args.gerrit)
    version_dict = get_version_dict(args.changes)
    change_id, latest_build = create_integration_change(rest)
    change_hash = update_env_file(rest, version_dict, change_id)
    description, build_url, tar_pkg = trigger_knife_job(
        rest,
        args.mails,
        latest_build,
        change_hash,
        change_id
    )
    if description and build_url:
        generate_releasenote(
            version_dict,
            latest_build,
            tar_pkg,
            build_url,
            description
        )
        trigger_mail_job(args.mails, tar_pkg)
    rest.abandon_change(change_id)


if __name__ == "__main__":
    main()
