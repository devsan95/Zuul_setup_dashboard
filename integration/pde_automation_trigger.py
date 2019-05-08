#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-


import fire
import re
import os
import json
import filecmp
from api import gerrit_rest
from api import retry
from api import s3tools
from mod import jenkins_job_trigger
from abandon_changes import parse_comments


def get_ps_change(rest, flist, change_no):
    for f in flist:
        if "env-config.d/ENV" in f:
            file_change = rest.get_file_change(f, change_no)
            ps_ver = re.search(r'ENV_PS_REL=(.*)', file_change['new']).group(1)
            return ps_ver
        else:
            return None


def get_interface_change(rest, change_no):
    name = None
    commit = None
    mess = retry.retry_func(
        retry.cfn(rest.get_commit, change_no),
        max_retry=10, interval=3
    )
    interface_ino = re.search(r'interface.*bb_version:(.*)-(.*)commit-ID:\W+(\w+).*',
                              mess["message"].encode('utf-8'), re.DOTALL)
    if interface_ino:
        try:
            name = interface_ino.group(1).strip().split("-")[1]
        except IndexError:
            name = "internal"
        commit = interface_ino.group(3).strip()

    return name, commit


def get_oam_info(rest, change_no):
    oam_comments = ''
    oam_dict = {}
    oam_re = re.compile(r'Patch Set .*\n.*\nMR created in (.*)\n.*title:(.*)\n.*branch:(.*)')

    changes = parse_comments(change_no, rest)
    for change in changes:
        ticket = retry.retry_func(
            retry.cfn(rest.get_detailed_ticket, change),
            max_retry=10, interval=3
        )
        for message in ticket['messages']:
            if 'MR created in' in message['message']:
                oam_comments = message['message']
        if oam_comments:
            oam_info = oam_re.match(oam_comments)
            if oam_info:
                oam_project = oam_info.group(1).strip()
                oam_branch = oam_info.group(3).strip()
                if "racoam" in oam_project:
                    oam_dict["racoam"] = "{}/tree/{}".format(oam_project, oam_branch)
                if "nodeoam" in oam_project:
                    oam_dict["nodeoam"] = "{}/tree/{}".format(oam_project, oam_branch)
                if "oamagentjs" in oam_project:
                    oam_dict["oamagentjs"] = "{}/tree/{}".format(oam_project, oam_branch)

    return json.dumps(oam_dict)


def generate_ps_interface_file(info_path, ps_ver=None, if_name=None, if_commit=None):
    if os.path.exists(info_path):
        os.remove(info_path)
    with open(info_path, "w") as f:
        if ps_ver:
            f.write("ENV_PS_REL={}\n".format(ps_ver))
        if if_name and if_commit:
            f.write("{}={}\n".format(if_name, if_commit))


def generate_pde_params(branch, ps_ver, if_name, if_commit, oam_info):
    params = {}
    params["jenkins_url"] = "http://mzoamci.eecloud.dynamic.nsn-net.net:8080"
    params["job_name"] = "5g-auto-pde-generation"
    params["key_params"] = ""
    params["retry_times"] = 1
    params["data"] = {}
    params["data"]["TARGET_BRACNH"] = branch
    params["data"]["PS_REL_VERSION"] = ps_ver
    params["data"]["CHANGE_TYPE"] = if_name
    params["data"]["CHANGE_COMMIT_ID"] = if_commit
    params["data"]["OAM_BRANCHES"] = oam_info
    params["data"]["PDE_TYPE"] = "knife"
    params["data"]["token"] = "pde_trigger"

    return params


def trigger_pde(branch, ps_ver, if_name, if_commit, oam_info):
    params = generate_pde_params(branch, ps_ver, if_name, if_commit, oam_info)
    jenkins_job_trigger.jenkins_job_trigger(params)


def main(path, gerrit_info_path, root_change, branch):
    s3_path = "s3://5g-cb/integration/ps_if_info/{}/ps_interface_info".format(root_change)
    local_d_path = os.path.join(path, "ps_interface_info_s3")
    info_path = os.path.join(path, "ps_interface_info")
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    flist = retry.retry_func(
        retry.cfn(rest.get_file_list, root_change),
        max_retry=10, interval=3
    )
    s3_handler = s3tools.S3Server("default")

    ps_ver = get_ps_change(rest, flist, root_change)
    if_name, if_commit = get_interface_change(rest, root_change)
    generate_ps_interface_file(info_path, ps_ver, if_name, if_commit)
    oam_info = get_oam_info(rest, root_change)

    if s3_handler.is_object(s3_path):
        s3_handler.download_file(s3_path, local_d_path)
        if not filecmp.cmp(local_d_path, info_path):
            s3_handler.upload_file(info_path, s3_path)
            trigger_pde(branch, ps_ver, if_name, if_commit, oam_info)
    else:
        s3_handler.upload_file(info_path, s3_path)
        trigger_pde(branch, ps_ver, if_name, if_commit, oam_info)


if __name__ == '__main__':
    fire.Fire(main)
