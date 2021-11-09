from datetime import datetime
import json
import time
import fire
from jenkinsapi.jenkins import Jenkins
import ruamel.yaml as yaml

from mod import wft_actions
from api import log_api


LOG = log_api.get_console_logger(name='COOP')


def get_jenkins_build_time(build_job, build_number, yaml_path):
    LOG.info("Getting build start end time from Jenkins")
    with open(yaml_path) as f:
        obj = yaml.load(f, Loader=yaml.Loader, version='1.1')
        jenkins_server = obj['5g_jenkins']
    jenkins_obj = Jenkins(jenkins_server['host'], jenkins_server['user'], jenkins_server['password'])
    current_build = jenkins_obj.get_job(":8080/{0}".format(build_job)).get_build(build_number)
    wft_rn_build = jenkins_obj.get_job(":8080/{0}".format(current_build.get_upstream_job_name())).get_build(current_build.get_upstream_build_number())
    build = jenkins_obj.get_job(":8080/{0}".format(wft_rn_build.get_upstream_job_name())).get_build(wft_rn_build.get_upstream_build_number())
    start_time = build.get_timestamp()
    duration = build.get_duration()
    end_time = start_time + duration
    return time.mktime(datetime.timetuple(start_time)), time.mktime(datetime.timetuple(end_time))


def generate_coop_json(project, baseline, build_job, build_number, yaml_path):
    LOG.info("Generating COOP json file")
    build_detail = wft_actions.WFTUtils.get_build_detail(baseline)
    LOG.info("{0} content get from WFT".format(baseline))
    component_list = dict()
    for sub_build in build_detail['subbuilds']:
        if sub_build.tag == 'peg_revision':
            continue
        component_list[sub_build.attrib.get('component')] = sub_build.text
    start_time, end_time = get_jenkins_build_time(build_job=build_job, build_number=build_number, yaml_path=yaml_path)
    json_template = {
        "bl": project,
        "product": "GNB",
        "branch": build_detail['branch'],
        "type": "product",
        "provider_email": "I_5G_CB_SCM@internal.nsn.com",
        "buildid": baseline,
        "buildstart": start_time,
        "buildend": end_time,
        "buildresult": "PASS",
        "buildurl": "http://production-5g.cb.scm.nsn-rdnet.net/job/integration-knives.START/",
        "buildlinks": [
            {
                "name": "Software download",
                "link": "https://wft.int.net.nokia.com/5G:WMP/5G_Central/builds/{0}#build=7".format(baseline)
            }
        ],
        "promotion": component_list
    }
    LOG.info("Writing coop json content into coop.json")
    with open('coop.json', 'w+') as cj:
        json.dump(json_template, cj)


if __name__ == "__main__":
    fire.Fire()
