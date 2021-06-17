#!/usr/bin/env python3
import os
import sys
import signal
import sh
import yaml
import re
import docker
import argparse
import fnmatch
import jenkins
import requests
import time
import git
import atexit
import json
import datetime
import pexpect
from api import log_api
from api import gerrit_rest
from bs4 import BeautifulSoup
from multiprocessing import Process, Queue


log = log_api.get_console_logger("releasenote")
wft_api = '{}/ALL/api/v1/build.json'.format(os.environ['WFT_API_URL'])
wft_url = os.environ['WFT_URL']
wft_post_url = '{}/ext/api/json'.format(os.environ['WFT_URL'])
jenkins_server = 'http://wrlinb147.emea.nsn-net.net:9090/'
integration_repo = os.environ['INTEGRATION_REPO_URL']
job_url = jenkins_server + 'job/{}/{}/'
base_path = os.path.join(os.environ["WORKSPACE"], "integration")
verify_ssl = os.getenv('WFT_VERIFY_SSL') != '0'
important_notes = {
    'note': "For zuul repo &amp;&amp; version info like this :\n \
'gitsm://eslinb34.emea.nsn-net.net:8882/p/MN/5G/NB/gnb - \
refs/zuul/master/Z2e81e3068a354df7a0c58030fe68b63'\n \
you can download code by steps:\n git clone --depth 1 \
http://eslinb34.emea.nsn-net.net:8882/p/MN/5G/NB/gnb\n \
cd gnb\n git fetch refs/zuul/master/Z2e81e3068a354df7a0c58030fe68b63 &amp;&amp; \
git checkout FETCH_HEAD",
    'name': "5G_PreIntegration"
}
docker_repo = "mnp5gcb-docker-repo-local.artifactory-espoo1.int.net.nokia.com"
docker_auth = {"HttpHeaders": {"User-Agent": "Docker-Client/18.03.1-ce (linux)"}}
docker_auth["auths"] = {docker_repo: {"auth": os.environ["ARTIFACTORY_API_AUTH"]}}
releasenote_file = os.path.join(os.environ["WORKSPACE"], "relnote.json")
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
releasenote_template = '''{
    "releasenote": {
        "baseline": {
            "author": "5g_cb.scm@nokia.com",
            "basedOn": {
                "name": "5G_Central",
                "project": "5G:WMP",
                "version": ""
            },
            "branch": "",
            "branchFor": [],
            "download": [],
            "homepage": "",
            "importantNotes": [],
            "name": "5G_Central",
            "project": "5G:WMP",
            "releaseDate": "",
            "releaseTime": "",
            "version": ""
        },
        "element_list": [],
        "releasenote_version": "2"
    }
}
'''
create_branch_template = {
    "branch": {
        "title": "",
        "template": "5Gxx_x.x.x",
        "project_full_path": "5G:WMP",
        "branch_type_title": "",
        "release_name": "5G00",
        "branch_system_releases_attributes": [],
        "feature_policy": "",
        "featurebuild_title": "",
        "visible": 1,
        "writable": 1,
        "build_deletion": "",
        "autobuild_state_machine_title": "inactive",
        "load_request_tag_check": 1,
        "upstream_branch_title": "",
        "parent_branch_title": "",
        "branchpoint_baseline": "",
        "important_notes": "",
        "supported_hardware": []
    },
    'access_key': os.environ['WFT_KEY'],
}


class bitbake_terminal(object):
    timeout = 300
    expect_str = b' \\x1b\[0m\$ '

    def __init__(self, docker_info):
        '''
        : dict: docker_info {'pkg': tag, 'stream_config': stream_config_file, 'image': docker_image}
        '''
        self.tag = docker_info['pkg']
        self.image = docker_info['image']
        self.container = self.run_container()
        self.init_cmds = [
            'source {}'.format(docker_info['stream_config']),
            'source oe-init-build-env build',
            '../env/prefix-root-gen-script.d/NATIVE prefix_root',
            'source prefix_root/environment-setup.sh'
        ]
        self.log_file = open(
            os.path.join(os.environ["WORKSPACE"], 'bitbake_terminal_{}.log'.format(os.getpid())),
            'wb'
        )
        self.terminal = pexpect.spawn("docker exec -it {} bash".format(self.container.id))
        self.terminal.logfile = self.log_file
        self.terminal.expect(bitbake_terminal.expect_str, timeout=bitbake_terminal.timeout)
        self.init_environment()

    def run_container(self):
        self.work_dir = os.path.join(os.environ["WORKSPACE"], "integration_{}".format(os.getpid()))
        self.prepare_workspace()
        client = docker.from_env()
        container = client.containers.run(
            self.image,
            detach=True,
            name="bitbake_{}".format(os.getpid()),
            network_mode='host',
            volumes={self.work_dir: {'bind': '/ephemeral', 'mode': 'rw'}},
            privileged=True
        )
        log.info("{}: container {} for {}".format(os.getpid(), container.id, self.tag))
        time.sleep(5)
        client.close()
        return container

    def e(self, component):
        if not component.strip().startswith('bitbake '):
            component = 'bitbake -e {}'.format(component.strip())
        return self.run(component)

    def init_environment(self):
        for cmd in self.init_cmds:
            self.run(cmd, check_wft_name=False)
        log.info("{}: terminal environment init finish. ^_^".format(os.getpid()))

    def run(self, cmd, check_wft_name=True):
        wft_name = None
        if not self.terminal.isalive():
            raise Exception("Terminal is lost!")
        if isinstance(cmd, str):
            cmd = bytes(cmd, encoding='utf-8')
        cmd = cmd.strip() + b'\n'
        self.terminal.write(cmd)
        self.terminal.expect(bitbake_terminal.expect_str, timeout=bitbake_terminal.timeout)
        if check_wft_name:
            wft_name = self.parse_wft_name(self.terminal.before.decode())
        return wft_name

    def close(self):
        self.terminal.close(force=True)
        self.log_file.close()
        self.container.stop()
        self.container.remove()
        sh.rm('-rf', self.work_dir)

    def parse_wft_name(self, output):
        wft_name = None
        if isinstance(output, bytes):
            output = str(output, encoding='utf-8')
        if re.search(r'\r\nWFT_COMPONENT *=', output):
            wft_name = re.findall(r"\r\nWFT_COMPONENT *=\W*([^\r\n'\"]*)\W*\r\n", output)[0]
        return wft_name

    def prepare_workspace(self):
        log.info("{}: Prepare {} workspace {}...".format(os.getpid(), self.tag, self.work_dir))
        if os.path.exists(self.work_dir) and self.work_dir.startswith(os.environ["WORKSPACE"]):
            sh.rm('-rf', self.work_dir)
        sh.cp('-ax', base_path, self.work_dir)
        integration = git.Repo(self.work_dir).git
        integration.checkout(self.tag)
        integration.submodule("update", "-f", "--init", "--recursive")
        log.info("{}: Prepare {} workspace {} finish.".format(os.getpid(), self.tag, self.work_dir))


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
    if response.ok:
        return json.loads(response.text)['items'][0]['version']
    elif "No records" in response.text:
        return "_000000_000000"
    else:
        raise Exception("get latest build from wft error!")


def check_config_yaml_change(base_pkg, pkg, integration):
    diff_output = integration.diff(base_pkg, pkg, "--stat")
    log.debug(diff_output)
    if " config.yaml " in diff_output:
        return True
    return False


def clone_integration_repo(path, tag):
    if os.path.exists(path):
        log.info("Remove dir: {}".format(path))
        sh.rm('-rf', path)
    log.info('Clone integration repo...')
    repo = git.Repo.clone_from(url=integration_repo, to_path=path)
    integration = repo.git
    integration.checkout(tag)
    integration.submodule("update", "--init", "--recursive")
    log.info("Clone integration repo to {} done".format(path))
    return integration


def arguments():
    parse = argparse.ArgumentParser()
    parse.add_argument('--pkg_name', '-p', required=True, help="PKG_NAME")
    parse.add_argument('--zuul_branch', '-z', required=True, help="ZUUL_BRANCH")
    parse.add_argument('--topic', '-t', required=True, help="TOPIC")
    parse.add_argument('--ver_pattern', '-v', required=False, help="ver_pattern")
    parse.add_argument('--branch', '-b', required=False, help="BRANCH")
    parse.add_argument('--branch_for', '-d', required=False, help="BRANCHFOR")
    parse.add_argument('--gerrit_info_path', '-f', required=False, help="gerrit_info_path")
    parse.add_argument('--upload_to_wft', '-u', required=True, help="UPLOAD_TO_WFT")
    parse.add_argument('--knife_json', '-k', required=False, help="use parameter instead of fetching from jenkins")
    parse.add_argument('--upstream_job', '-j', required=False, help="use 'project/number' as upstream job (eg. Knives.START/27769)")
    parse.add_argument('--release_name', '-r', required=False, help="use parameter as build name in releasenote")
    parse.add_argument('--release_state', '-s', required=False, help="use parameter as build state in registration")
    return parse.parse_args()


def get_branch(pkg, ver_pattern):
    if not re.match(r"^\d+\.\d+\.\d+(-\w+INT\+\d+)?$", pkg):
        raise Exception("Error, package name format is not right.")
    branch = re.findall(r"-(\w*)\+", pkg)[0]
    stream_file = get_stream_config_file(ver_pattern)[0]
    stream_name = ''
    if stream_file:
        stream_name = stream_file.split('-')[1]
    if branch == "L1INT":
        branch = "{}_lonerint".format(stream_name)
    elif branch in ["PSINT", "NIDDINT"] and "sran" in stream_name:
        branch = "{}_5G_IN_SRAN".format(branch)
    elif branch in ["FEINT", "PSINT", "NIDDINT", "LOMINT", "CPIINT", "RCPINT"]:
        # master cloud streams have already been split to pDU CU_VNF vDU
        for stream_type in ['pDU', 'CU_VNF', 'vDU', 'CU_CNF']:
            if stream_type in stream_name:
                branch = "{}_{}".format(branch, stream_type)
        # Maintenance branches still have stream_name such as 20Bb1_cloudbts
        if "cloud" in stream_name:
            branch = "{}_cloudbts".format(branch)
    log.info("branch: {}".format(branch))
    return branch


def set_branch_for(args, knife_json):
    if args.branch_for:
        return

    args.branch_for = args.branch
    if args.pkg_name.startswith('0.990') and 'integration' in knife_json:
        log.info("Only 5G_IN_SRAN need to reset branchFor from root subject")
        commitid = knife_json['integration']['repo_ver']
        gerritclient = gerrit_rest.init_from_yaml(args.gerrit_info_path)
        rootchange = gerritclient.get_detailed_ticket(commitid)
        subject = rootchange['subject']
        branch = re.search(r'[^\w]int_branch:\s*(\w+)', subject)
        if branch:
            args.branch_for = branch.group(1)


def get_stream_config_file(ver_pattern, file_pattern='.config-master*'):
    wft_prefix = None
    config_file = None
    log.info("Get stream config file")
    for file_name in os.listdir(base_path):
        full_path = os.path.join(base_path, file_name)
        if os.path.isfile(full_path) and fnmatch.fnmatch(file_name, file_pattern):
            with open(full_path, encoding='utf-8') as config:
                content = config.read()
                if "export VERSION_PATTERN={}".format(ver_pattern) in content:
                    wft_prefix = re.findall(
                        r'\nexport WFT_PACKAGE_NAME=([^\n]*)\n',
                        content
                    )[0].strip()
                    log.info("Find config file: {}, WFT_PACKAGE_NAME: {}".format(file_name, wft_prefix))
                    config_file = file_name
                    break
    return config_file, wft_prefix


def get_upstream_job(args):
    if args.upstream_job:
        job = args.upstream_job.split('/')
        if len(job) != 2:
            raise Exception("Invalid upstream job format. Expected 'project/number'")
        return job

    upstream_project = None
    upstream_build = None
    server = jenkins.Jenkins(jenkins_server)
    build_info = server.get_build_info(os.environ["JOB_NAME"], int(os.environ["BUILD_NUMBER"]))
    for action in build_info['actions']:
        if "causes" in action and "upstreamProject" in action['causes'][0]:
            upstream_project = action['causes'][0]['upstreamProject']
            upstream_build = action['causes'][0]['upstreamBuild']
            break
    else:
        raise Exception("Can not get upstream job!")
    return upstream_project, upstream_build


def get_image_version():
    image_version = ''
    with open(os.path.join(base_path, '.docker-config'), encoding='utf-8') as docker_config:
        for line in docker_config.readlines():
            if 'DOCKER_IMAGE_VERSION=' in line:
                image_version = line.split('=', 1)[1].strip()
                log.info("image_version: {}".format(image_version))
                break
        else:
            raise Exception("Can not get image version!")
    return image_version


def pull_docker_image():
    generate_json_file(docker_auth, os.path.join(os.environ["HOME"], ".docker/config.json"))
    image_version = get_image_version()
    client = docker.from_env()
    client.images.pull('{}/5g/cbbuild:{}'.format(docker_repo, image_version))
    client.close()
    return '{}/5g/cbbuild:{}'.format(docker_repo, image_version)


def process_wft_name(docker_info, task_queue, done_queue):
    atexit.register(cleanup_and_exit)
    log.info("{}: child process start.".format(os.getpid()))
    try:
        bitbake = bitbake_terminal(docker_info)
    except Exception:
        log.error("{}: init bitbake terminal error, exit!")
        cleanup_and_exit()
    for component in iter(task_queue.get, None):
        try:
            wft_name = bitbake.e(component)
        except Exception:
            log.error("{}: bitbake -e command error, exit!")
            bitbake.close()
            cleanup_and_exit()
        if wft_name:
            done_queue.put({'knife': component, 'wft': wft_name})
        else:
            done_queue.put({'knife': component, 'wft': component})
    bitbake.close()
    log.info("{}: child process exit.".format(os.getpid()))


def sync_wft_name(knife_json, docker_info):
    knife_json_wft = dict()
    child_prosess_list = list()
    processes_number = len(knife_json) // 5 + 1
    if processes_number > 5:
        processes_number = 5
    task_queue = Queue()
    done_queue = Queue()
    for component in knife_json.keys():
        task_queue.put(component)
    for _ in range(processes_number):
        task_queue.put(None)
    for _ in range(processes_number):
        child_prosess = Process(
            target=process_wft_name,
            args=(docker_info, task_queue, done_queue)
        )
        child_prosess.start()
        child_prosess_list.append(child_prosess)
    for _ in range(len(knife_json)):
        try:
            wft_info = done_queue.get(timeout=600)
        except Exception:
            log.error("Get wft_info dict form done_queue timeout, exit!")
            time.sleep(5)
            for child_prosess in child_prosess_list:
                if child_prosess.is_alive():
                    child_prosess.terminate()
            cleanup_and_exit()
        log.info(wft_info)
        knife_json_wft[wft_info['wft']] = knife_json[wft_info['knife']]
    return knife_json_wft


def optimize_json_dict(knife_json):
    for key in list(knife_json.keys()):
        if ":" in key:
            version = knife_json.pop(key)
            component = key.split(":")[-1]
            if component not in knife_json:
                knife_json[component] = version


def get_knife_json_dict(args, base_pkg, integration):
    pkg = args.pkg_name
    if args.knife_json:
        knife_json = args.knife_json
    else:
        knife_json = None
        job, build = get_upstream_job(args)
        response = requests.get(job_url.format(job, build) + 'parameters/')
        if not response.ok:
            raise Exception("Get upstream job parameters html failed!")
        soup = BeautifulSoup(response.text, 'html.parser')
        for tbody in soup.find_all('tbody'):
            td = tbody.find('td', class_="setting-name")
            if td and td.get_text() == "KNIFE_JSON":
                try:
                    knife_json = tbody.find('textarea').get_text()
                except AttributeError:
                    log.info("Get textarea failed, try get input value.")
                    knife_json = tbody.find('input').get('value')
                break
        else:
            raise Exception("Get upstream job knofe json text failed!")
    knife_json = json.loads(knife_json)
    optimize_json_dict(knife_json)
    check_integration_change(pkg, base_pkg, integration, knife_json)
    log.info("KNIFE_JSON: {}".format(knife_json))
    return knife_json


def get_config_yaml_change(base_pkg, pkg, integration):
    change_dict = dict()
    if not check_config_yaml_change(base_pkg, pkg, integration):
        log.info("knife json not contain config.yaml change.")
        return change_dict
    config_yaml_path = os.path.join(base_path, 'config.yaml')
    integration.checkout(base_pkg)
    with open(config_yaml_path, 'r') as config:
        base_config_yaml = yaml.safe_load(config)['components']
    integration.checkout(pkg)
    with open(config_yaml_path, 'r') as config:
        new_config_yaml = yaml.safe_load(config)['components']
    for comp in new_config_yaml:
        if new_config_yaml[comp]['version'] != base_config_yaml[comp]['version']:
            comp_name = comp.split(':')[-1]
            comp_ver = new_config_yaml[comp]['version']
            change_dict[comp_name] = {"version": comp_ver}
            log.info("config.yaml: {} version is {}".format(comp_name, comp_ver))
    return change_dict


def check_integration_change(pkg, base_pkg, integration, knife_json):
    if 'integration' not in knife_json:
        log.info("Knife json not contain integration change.")
        return
    config_yaml_dict = get_config_yaml_change(base_pkg, pkg, integration)
    for comp in config_yaml_dict:
        knife_json[comp] = config_yaml_dict[comp]


def get_component_version(knife_json, component, parse=True):
    ver_fields = ['repo_ver', 'bb_ver', 'version', 'PV', 'BIN_VER', 'SVNREV', 'WFT_NAME', "commit"]
    version = None
    if parse:
        for ver_field in ver_fields:
            if ver_field in knife_json[component]:
                if ver_field == 'BIN_VER':
                    path_key = "not_exist"
                    for key in knife_json[component].keys():
                        if '_ARTIFACTORY_DIRECTORY' in key:
                            path_key = key
                            break
                    version = "{} {}".format(
                        knife_json[component][ver_field],
                        knife_json[component].get(path_key, '')
                    )
                elif ver_field == 'SVNREV':
                    version = "{} {}".format(
                        knife_json[component].get("SVNBRANCH", ''),
                        knife_json[component][ver_field]
                    )
                else:
                    version = knife_json[component][ver_field]
                # knife_json.pop(component)
                break
        else:
            log.warning("Failed to parse {}'s version from knife json".format(component))
    else:
        version = str(knife_json[component])
        version = re.sub(r"'|\{|\}| ", '', version)
    return version


def traverse_element_list(releasenote, knife_json, action="update"):
    for item in releasenote['releasenote']['element_list']:
        if not knife_json:
            log.info("Knife_json dict empty!")
            return
        new_version = None
        knife_json_key = None
        if item['name'] in knife_json:
            new_version = get_component_version(knife_json, item['name'], parse=True)
            knife_json_key = item['name']
        else:
            item_re_name = re.sub(r'_|-', '(?:-|_)', item['name'])
            item_re_name = re.sub(r'^', '^', item_re_name)
            item_re_name = re.sub(r'$', '$', item_re_name)
            for component in knife_json.keys():
                if re.match(item_re_name, component, re.I):
                    new_version = get_component_version(knife_json, component, parse=True)
                    knife_json_key = component
                    break
        if new_version:
            item['version'] = new_version
            log.info("Update {}'s version to {}".format(item['name'], new_version))
            knife_json.pop(knife_json_key)
    if knife_json and action == "add":
        add_list = list()
        for component in knife_json.keys():
            version = get_component_version(knife_json, component, parse=True)
            if version:
                add_list.append(component)
                log.info('Add {}:"{}" to releasenote directely.'.format(component, version))
                releasenote['releasenote']['element_list'].append(
                    {'name': component, 'project': "5G", 'version': version}
                )
        if add_list:
            for component in add_list:
                knife_json.pop(component)


def update_element_list(releasenote, knife_json, docker_info):
    if 'integration' in knife_json:
        releasenote['releasenote']['element_list'].append(
            {'name': "integration", 'project': "5G", 'version': ""}
        )
    traverse_element_list(releasenote, knife_json)
    if knife_json:
        log.warning("Parse WFT name for the remaining components:\n {}".format(knife_json))
        knife_json = sync_wft_name(knife_json, docker_info)
        traverse_element_list(releasenote, knife_json, action="add")
    if knife_json:
        log.warning("The remaining components can not matched:\n {}".format(knife_json))


def update_downloads_url(args, releasenote):
    pkg = args.pkg_name
    downloads = list()
    job, build = get_upstream_job(args)
    log.info("Download {} #{} artifact file package-bb.prop".format(job, build))
    response = requests.get(
        job_url.format(job, build) + 'artifact/artifacts/package-bb.prop'
    )
    if not response.ok:
        log.error("Get {} #{}'s package-bb.prop failed!, try console log".format(job, build))
        response = requests.get(job_url.format(job, build) + 'consoleText')
        if not response.ok:
            raise Exception("Can not get build console log!")
    urls = re.findall(r'(?:hangzhou_|espoo_)[\w ]*(?:=|value )(http[^\n]*)\n', response.text)
    if not urls:
        raise Exception("Can not get package downloads url!")
    for url in urls:
        log.info(url)
        downloads.append({
            'path': url,
            'storage': "Artifactory" if "artifactory" in url else "S3",
            'name': pkg
        })
    if downloads:
        releasenote['releasenote']['baseline']['download'] = downloads


def update_release_date(args, releasenote):
    job, build = get_upstream_job(args)
    home_page = '{}job/{}/{}/'.format(jenkins_server, job, build)
    releasenote['releasenote']['baseline']['homepage'] = home_page
    response = requests.get(home_page)
    if not response.ok:
        raise Exception("Get {} #{}'s html failed!".format(job, build))
    soup = BeautifulSoup(response.text, 'html.parser')
    h1 = soup.find('h1', "build-caption page-headline")
    date_str = re.findall(r'.*\((.*)\).*', h1.get_text())[0]
    if not date_str:
        raise Exception("Get date string from {} #{} failed".format(job, build))
    log.info(date_str)
    time_zone = date_str.split(' ')[4]
    date_time = datetime.datetime.strptime(
        date_str,
        f'%a %b %d %X {time_zone} %Y'
    ).strftime('%Y-%m-%d %H:%M:%S')
    build_date, build_time = date_time.split(' ')
    releasenote['releasenote']['baseline']['releaseDate'] = build_date
    releasenote['releasenote']['baseline']['releaseTime'] = build_time


def generate_local_releasenote(build_config):
    element_list = list()
    component_list = yaml.safe_load(build_config)['components']
    for component in component_list:
        element_list.append({
            'name': component.split(':')[-1].strip(),
            'project': ":".join(component.split(':')[:-1]).strip(),
            'version': component_list[component]['version']
        })
    local_template = json.loads(releasenote_template)
    local_template['releasenote']["element_list"] = element_list
    return local_template


def get_releasenote(base_pkg, wft_prefix):
    base_wft_name = "{}_{}".format(wft_prefix, base_pkg)
    response = requests.get(
        f"{wft_url}/ext/releasenote/{base_wft_name}.json",
        params={'access_key': os.environ['WFT_KEY']},
        verify=verify_ssl
    )
    if not response.ok:
        log.warn("Get releasenote failed, try download build configration!")
        build_config = requests.get(
            f"{wft_url}/ext/build_config/{base_wft_name}",
            params={'access_key': os.environ['WFT_KEY']},
            verify=verify_ssl
        )
        if not build_config.ok:
            raise Exception(f"Get {base_wft_name}'s configuration and releasenote failed!")
        return generate_local_releasenote(build_config.text)
    return json.loads(response.text)


def generate_json_file(data_dict, json_file):
    data_str = json.dumps(data_dict, sort_keys=True, indent=4, separators=(',', ': '))
    with open(json_file, 'w') as f:
        f.write(data_str)


def generate_releasenote(args, base_pkg, knife_json, wft_prefix, docker_info):
    latest_build = get_latest_build(args.branch)
    releasenote = get_releasenote(base_pkg, wft_prefix)
    docker_info['pkg'] = args.pkg_name
    set_branch_for(args, knife_json)
    update_element_list(releasenote, knife_json, docker_info)
    update_downloads_url(args, releasenote)
    releasenote['releasenote']['baseline']['branchFor'] = [args.branch_for]
    releasenote['releasenote']['baseline']['importantNotes'] = [important_notes]
    releasenote['releasenote']['baseline']['basedOn']['version'] = latest_build
    releasenote['releasenote']['baseline']['notes'] = args.topic
    releasenote['releasenote']['baseline']['version'] = args.release_name or args.pkg_name
    releasenote['releasenote']['baseline']['branch'] = args.branch
    update_release_date(args, releasenote)
    generate_json_file(releasenote, releasenote_file)


def add_storage_to_build(pkg_name):
    '''
    : knife storage id is 267
    '''
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    post_url = "{}/api/v1/5G:WMP/5G_Central/builds/{}/storages/267.json".format(
        os.environ['WFT_API_URL'],
        pkg_name
    )
    data = {
        'access_key': os.environ['WFT_KEY'],
        'settings': {
            'path': 'mnp5g-central-public-local/Knife/{}/'.format(pkg_name),
            'prefix': '',
            'server': 'espoo1'
        }
    }
    response = requests.post(post_url, json=data, headers=headers)
    if not response.ok:
        log.error(response.text)
        raise Exception("Add artifactory storage to {} failed!".format(pkg_name))
    log.info("Add artifactory storage to {} successful!".format(pkg_name))


def register_on_wft(args):
    if args.upload_to_wft == "true":
        data = {
            'access_key': os.environ['WFT_KEY'],
            'state': args.release_state or 'released_for_quicktest',
            'state_machine': 'imported_central'
        }
        response = requests.post(
            wft_post_url,
            data=data,
            files={'file': open(releasenote_file, 'rb')},
            verify=verify_ssl
        )
        if not response.ok:
            raise Exception(response.text)
        log.info("Registered build {} on WFT".format(args.pkg_name))
        # add_storage_to_build(args.pkg_name)


def create_wft_branch(branch):
    if not branch:
        sys.exit("branch is empty, exit create branch")
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    create_url = 'https://wft.int.net.nokia.com:8091/api/v1/branches/{}/create.json'.format(branch)
    create_branch_template['branch']['title'] = branch
    log.info("start to create new branch {} on WFT".format(branch))
    response = requests.post(
        create_url,
        json=create_branch_template,
        headers=headers,
        verify=verify_ssl
    )
    if not response.ok:
        raise Exception(response.text)
    log.info("New branch {} is created on WFT".format(branch))


def cleanup_and_exit(signum=None, frame=None):
    if signum:
        log.info("{}: capture signal {}".format(os.getpid(), signum))
    work_dir = os.path.join(os.environ["WORKSPACE"], "integration_{}".format(os.getpid()))
    client = docker.from_env()
    for container in client.containers.list():
        if re.search(r'^bitbake_{pid}$'.format(pid=os.getpid()), container.name):
            log.info("{}: cleanup container: {}".format(os.getpid(), container.name))
            container.stop()
            container.remove()
    client.close()
    if os.path.exists(work_dir):
        log.info("{}: cleanup work dir: {}".format(os.getpid(), work_dir))
        sh.rm('-rf', work_dir)
    log.info("{}: clean up successfully.".format(os.getpid()))
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, cleanup_and_exit)
    signal.signal(signal.SIGABRT, cleanup_and_exit)
    signal.signal(signal.SIGINT, cleanup_and_exit)
    atexit.register(cleanup_and_exit)
    args = arguments()
    if args.zuul_branch == "dev/test":
        log.info("Dev/test branch, no need to release to WFT")
        return
    base_pkg = args.pkg_name.split("-")[0]
    integration = clone_integration_repo(base_path, args.pkg_name)
    image = pull_docker_image()
    if not args.ver_pattern:
        args.ver_pattern = re.findall(r"^([0-9]+\.[0-9]+)\.", args.pkg_name)[0]
        log.info("ver_pattern: {}".format(args.ver_pattern))
    if not args.branch:
        args.branch = get_branch(args.pkg_name, args.ver_pattern)
    stream_config, wft_prefix = get_stream_config_file(args.ver_pattern, file_pattern='.config-*')
    if not stream_config or not wft_prefix:
        raise Exception("Can not get stream config file or wft name prefix!")
    docker_info = {'image': image, 'stream_config': stream_config}
    knife_json = get_knife_json_dict(args, base_pkg, integration)
    generate_releasenote(args, base_pkg, knife_json, wft_prefix, docker_info)
    try:
        register_on_wft(args)
    except Exception as e:
        if "does not exist in WFT" in str(e):
            log.info(e)
            create_wft_branch(args.branch)
        register_on_wft(args)


if __name__ == "__main__":
    main()
