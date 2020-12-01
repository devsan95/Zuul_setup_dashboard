#!/usr/bin/env python
import os
import re
import time
import json
import yaml
import argparse
import jenkins
import requests
import git
import subprocess
from api import gerrit_rest, log_api
from scm_tools.wft.api import WftAPI


log = log_api.get_console_logger("rcpvduint_knife")
wft = WftAPI()
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


def create_integration_change(base, version_dict):
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
    repo = git.Repo.clone_from(
        url='ssh://gerrit.ext.net.nokia.com:29418/MN/5G/COMMON/integration',
        to_path='integration'
    )
    integration = repo.git
    if base.lower() != "head":
        log.info("use specify version {} as base".format(base))
        latest_ver = base
    integration.checkout(re.sub("^5G_", "", latest_ver))
    update_env_config_file(version_dict)
    if not integration.diff():
        raise Exception("config.yaml and env file no change!")
    integration.config("user.name", "CA 5GCV")
    integration.config("user.email", "5g_cb.scm@nokia.com")
    integration.add("config.yaml", "env/env-config.d/ENV")
    integration.commit('-m', 'Automated rcpvduint trigger')
    process = subprocess.Popen(
        "gitdir=$(git rev-parse --git-dir); scp -p -P 8282 ca_5gcv@gerrit.ext.net.nokia.com:hooks/commit-msg ${gitdir}/hooks/",
        shell=True,
        cwd=os.path.join(os.getcwd(), "integration")
    )
    process.wait()
    integration.commit("--amend", "--no-edit")
    process = subprocess.Popen(
        "git push origin HEAD:refs/for/master",
        shell=True,
        cwd=os.path.join(os.getcwd(), "integration"),
        stderr=subprocess.PIPE
    )
    process.wait()
    output = process.stderr.read()
    change_id = re.findall(r"/([0-9]*) *Automated rcpvduint t", output)[0]
    change_hash = integration.execute(["git", "rev-parse", "HEAD"])
    log.info("ticket id is {}; base pakage is {}".format(change_id, latest_ver))
    return change_hash, latest_ver, change_id


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
        '--base',
        '-b',
        required=True,
        help="--Base pkg"
    )
    parse.add_argument(
        '--gerrit',
        '-g',
        required=True,
        help="--gerrit_info_path"
    )
    return parse.parse_args()


def update_env_config_file(version_dict):
    origin_cwd = os.getcwd()
    os.chdir(os.path.join(os.getcwd(), "integration"))
    with open('env/env-config.d/ENV', 'r') as env, open('config.yaml', 'r') as config:
        env_content = env.read()
        config_yaml = yaml.safe_load(config)
    log.info(env_content)
    log.info(config_yaml)
    for item in version_dict:
        if re.search(r'\n *{}=[^\n]*\n'.format(item), env_content):
            log.info("update env {} version".format(item))
            env_content = re.sub(
                r'\n *{}=[^\n]*\n'.format(item),
                '\n{}={}\n'.format(item, version_dict[item]),
                env_content
            )
        else:
            raise Exception("Can not find {} from env file!".format(item))
        for project_comp in config_yaml['components']:
            if "env_key" in config_yaml['components'][project_comp] \
                    and item == config_yaml['components'][project_comp]["env_key"]:
                log.info("update config.yaml {} version".format(item))
                config_yaml['components'][project_comp]["commit"] = version_dict[item]
                config_yaml['components'][project_comp]["version"] = version_dict[item]
                break
        else:
            raise Exception("Can not find {} from config.yaml file!".format(item))
    with open('env/env-config.d/ENV', 'w') as env, open('config.yaml', 'w') as config:
        log.info("start write env and config.yaml file")
        yaml.safe_dump(config_yaml, config, default_flow_style=False)
        env.write(env_content)
    log.info("env and config.yaml file update finish.")
    os.chdir(origin_cwd)


def generate_releasenote(version_dict, latest_build, tar_pkg, build_url, download_urls):
    if "5G_" not in latest_build:
        latest_build = "5G_{}".format(latest_build)
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
    downloads = list()
    for url in download_urls:
        log.info(url)
        downloads.append({
            'path': url,
            'storage': "Artifactory" if "artifactory" in url else "S3",
            'name': tar_pkg
        })
    note['releasenote']['baseline']['download'] = downloads
    elements = list()
    old_elements = note['releasenote'].pop('element_list')
    for comp in old_elements:
        for item in version_dict:
            if comp['name'] == item.replace('ENV_', ''):
                log.debug(version_dict[item])
                comp['version'] = version_dict[item]
                break
        elements.append(comp)
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
            log.warning("Get queue_info error, try again.")
            time.sleep(20)
            continue
        if 'executable' in queue_info:
            build_id = queue_info['executable']['number']
            break
        time.sleep(70)
    log.info("{}job/{}/{} start".format(jenkins_server, job_name, build_id))
    build_info = dict()
    try_time = 0
    while True:
        try:
            build_info = server.get_build_info(job_name, build_id)
        except Exception:
            try_time += 1
            if try_time > 400:
                raise Exception("Get build_info error,no more tries left")
            log.warning("Get build_info error, try again.")
            time.sleep(30)
            continue
        if not build_info['building']:
            break
        time.sleep(interval_time)
    log.info("{}job/{}/{} {}".format(jenkins_server, job_name, build_id, build_info['result']))
    return build_id, build_info


def trigger_knife_job(rest, mails, latest_build, change_hash, change_id):
    url = None
    params = {
        'MAIL_LIST': mails,
        'KNIFE_JSON': '{ "integration": {"repo_ver": "%s"} }' % change_hash,
        'FORCED_LABEL': 'cores-beast-knife',
        'BASE_PACKAGE': latest_build.replace('5G_', '')
    }
    build_id, build_info = trigger_jenkins_job(knife_job, params, 512)
    tar_pkg_name = ''
    console_output = server.get_build_console_output(knife_job, build_id)
    download_urls = re.findall(
        r'(?:hangzhou_|espoo_)[\w ]*(?:=|value )(http[^\n]*)\n',
        console_output
    )
    tar_pkg_name = re.search(
        r'Setting variable from ECL PKG_NAME=([^\n]*)\n',
        console_output
    ).groups()[0].strip()
    if build_info['result'] == 'SUCCESS':
        url = build_info['url']
    else:
        rest.abandon_change(change_id)
        raise Exception("Knife job failed: {}".format(build_info['url']))
    return url, tar_pkg_name, download_urls


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
    change_hash, base_build, change_id = create_integration_change(args.base, version_dict)
    build_url, tar_pkg, download_urls = trigger_knife_job(
        rest,
        args.mails,
        base_build,
        change_hash,
        change_id
    )
    if download_urls and build_url:
        generate_releasenote(
            version_dict,
            base_build,
            tar_pkg,
            build_url,
            download_urls
        )
    rest.abandon_change(change_id)


if __name__ == "__main__":
    main()
