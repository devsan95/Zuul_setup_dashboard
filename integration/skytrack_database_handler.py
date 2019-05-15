import re
import time
import datetime
import json
import requests
import fire
import jenkinsapi

from api import gerrit_rest
from api import mysql_api
from mod import wft_tools
from generate_bb_json import get_description


JENKINS_URL = "http://wrlinb147.emea.nsn-net.net:9090"


def get_jira_id(integration_change, gerrit_info_path):
    print("Getting JIRA ID from {0} commit message".format(integration_change))
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    rest.init_cache(1000)
    description, rest_id = get_description(rest, integration_change)
    jira_key = ''
    for line in description.split('\n'):
        match = re.findall(r'\%JR=(.*)', line)
        if match:
            jira_key = match[0]
            break
    if not jira_key:
        raise Exception('JIRA ID Not found')
    print('JIRA ID found: {0}'.format(jira_key))
    return jira_key


def string_time_format_validator(str_time):
    """
    validate string time format, 2019-01-01 12:00:00 is accepted
    :param str_time: date time like 2019-01-01 12:00:00
    :return: boolean
    """
    return True if re.match(r'\d+-\d+-\d+\s\d+:\d+:\d+', str_time) else False


def get_job_timestamp(jenkins_url, job_name, build_number):
    build = jenkinsapi.api.get_build(jenkins_url, job_name, build_number)
    start_timestamp = build.get_timestamp()
    duration = build.get_duration()
    end_timestamp = start_timestamp + duration
    return int(time.mktime(start_timestamp.timetuple())) * 1000, int(
        time.mktime(end_timestamp.timetuple())) * 1000


def skytrack_detail_api(integration_name,
                        product,
                        package_name,
                        mini_branch,
                        type_name,
                        status,
                        link=None,
                        start_time=None,
                        end_time=None):
    url = "http://skytrack.dynamic.nsn-net.net:8080/integration/add?pretty"
    package_info = {
        "integration_name": integration_name,
        "product": product,
        "package_name": package_name,
        "mini_branch": mini_branch,
        "type": type_name,
        "status": status,
        "link": link,
        "start_timestamp": start_time,
        "end_timestamp": end_time
    }
    if start_time:
        package_info['start_timestamp'] = start_time
    if end_time:
        package_info['end_timestamp'] = end_time
    content = json.dumps({"packages": [package_info]})
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    print "updating build info in detailed page"
    print package_info
    r = requests.put(url, data=content, headers=headers)
    print r.text
    if r.status_code != 200:
        print r.text
        raise Exception("Failed to update build info in detailed page")


def mysql_connector(database_info_path, server_name, database_name):
    mydb = mysql_api.init_from_yaml(database_info_path, server_name=server_name)
    mydb.init_database(database_name)
    return mydb


def auto_update_build_info(integration_change,
                           pkg_info_file,
                           gerrit_info_path,
                           database_info_path,
                           job_name=None,
                           build_number=None,
                           dry_run=False):
    jira_key = get_jira_id(integration_change, gerrit_info_path)
    mydb = mysql_connector(database_info_path, 'skytrack', 'skytrack')
    knife_link_temp = 'http://5g-cb.es-si-s3-z4.eecloud.nsn-net.net' \
                      '/BucketList/index.html?prefix=knife/{knife}/'
    with open(pkg_info_file) as pkg_info:
        match = re.findall(r'knife\/(.*)\/', pkg_info.read())
        if not match:
            raise Exception('Knife ID can not be found in {0}'.format(pkg_info_file))
    knife_id = match[0]
    knife_link = knife_link_temp.format(knife=knife_id)
    search_info = mydb.executor("SELECT entity_build "
                                "FROM t_issue WHERE issue_key = '{0}'".format(jira_key),
                                output=True)
    origin_entity_info = search_info[0][0]
    entity_info = '{0}*{1}'.format(knife_id.rsplit('.', 1)[0], knife_link)
    if origin_entity_info:
        for line in origin_entity_info.split(','):
            if line.split('*')[0] in knife_id:
                continue
            entity_info += ',{0}'.format(line)
    if dry_run:
        print('DRY-RUN MODE:')
        print('Will update entity_build: {0}'.format(entity_info))
    else:
        mydb.update_info(
            table='t_issue',
            replacements={
                'entity_build': entity_info
            },
            conditions={
                'issue_key': jira_key
            }
        )
        print('Entity build info updated')
        print('Entity build: {0}'.format(entity_info))

    # update build info in detailed page
    start_time, end_time = get_job_timestamp(JENKINS_URL, job_name, build_number)
    stream = wft_tools.get_stream_name('{0}.'.format(knife_id.rsplit('.', 1)[0]))
    skytrack_detail_api(
        integration_name=jira_key,
        product='5G',
        package_name=knife_id,
        mini_branch=stream,
        type_name='Integration Build',
        status=1,
        link=knife_link,
        start_time=start_time,
        end_time=end_time
    )
    update_events(
        database_info_path=database_info_path,
        integration_name=jira_key,
        description="{0} integration package created: {1}".format(stream, knife_link)
    )


def clean_build_info(integration_change, gerrit_info_path, database_info_path, dry_run=False):
    jira_key = get_jira_id(integration_change, gerrit_info_path)
    mydb = mysql_api.init_from_yaml(database_info_path, server_name='skytrack')
    mydb.init_database('skytrack')
    print('Clean up {0} entity build info'.format(jira_key))
    if dry_run:
        print('DRY-RUN MODE:')
        print('entity_build, entity_build_status and entity_test_status will be cleanup')
        return
    if mydb.executor(
        sql='SELECT * FROM t_issue WHERE issue_key = "{0}"'.format(jira_key),
        output=True
    ):
        mydb.update_info(
            table='t_issue',
            replacements={
                'entity_build': "",
                'entity_test_status': 0
            },
            conditions={
                'issue_key': jira_key
            }
        )


def update_qt_result(database_info_path, jira_key, package_name, type_name, result, start_time=None, end_time=None):
    result_map = {
        'released': 1,
        'not_released': 2,
        'released_with_restrictions': 3
    }
    t_issue_result_map = {
        'released': 1,
        'not_released': -1,
        'released_with_restrictions': 1
    }
    start_time = int(time.mktime(datetime.datetime.strptime(
        start_time, "%Y[-/]%m[-/]%d %H:%M:%S").timetuple())) * 1000 \
        if start_time and string_time_format_validator(start_time) else int(time.time()) * 1000
    end_time = int(time.mktime(datetime.datetime.strptime(
        end_time, "%Y[-/]%m[-/]%d %H:%M:%S").timetuple())) * 1000 \
        if end_time and string_time_format_validator(end_time) else int(time.time()) * 1000
    regex_match = re.match(r'(.*_)?(\d+\.\d+).*', package_name)
    if not regex_match:
        raise Exception('Wrong package name given: {0}'.format(package_name))
    stream = wft_tools.get_stream_name('{0}.'.format(regex_match.group(2)))
    skytrack_detail_api(
        integration_name=jira_key,
        package_name=package_name,
        mini_branch=stream,
        product="5G",
        type_name=type_name,
        status=result_map[result],
        start_time=start_time,
        end_time=end_time
    )
    mydb = mysql_connector(database_info_path, 'skytrack', 'skytrack')
    mydb.update_info(
        table='t_issue',
        replacements={
            'entity_test_status': t_issue_result_map[result]
        },
        conditions={
            'issue_key': jira_key
        }
    )


def update_events(database_info_path, integration_name, description, highlight=False, date=None):
    mydb = mysql_connector(database_info_path, 'skytrack', 'skytrack')
    date = date if date else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    values = {
        'integration_name': integration_name,
        'description': description,
        'hightlight': int(highlight),
        'date': date
    }
    mydb.insert_info(
        table='t_integration_events',
        values=values
    )


if __name__ == '__main__':
    fire.Fire()
