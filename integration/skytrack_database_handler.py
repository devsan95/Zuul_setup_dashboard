import re
import time
import datetime
import json
import requests
import fire
from jenkinsapi.jenkins import Jenkins

from api import gerrit_rest
from api import mysql_api
from mod import wft_tools
import generate_bb_json
from mod.integration_change import RootChange


JENKINS_URL = "http://production-5g.cb.scm.nsn-rdnet.net:80"


def get_specified_ticket(change_no, database_info_path, gerrit_info_path, ticket_type='root'):
    '''
    get root ticket or get integration tocket.
    :param ticket_type: root or integration
    :return ticket id or None
    '''
    print("Getting {} ticket according to the {}".format(ticket_type, change_no))
    if ticket_type == "root":
        reg = re.compile(r'\bROOT CHANGE\b')
    elif ticket_type == "integration":
        reg = re.compile(r'\bMANAGER CHANGE\b')
    else:
        raise Exception('ticket_type just can be root or integration!')
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    msg = " ".join(rest.get_commit(change_no)['message'].split('\n'))
    if reg.search(msg):
        return change_no
    else:
        change_list = get_changes_from_db(change_no, database_info_path, gerrit_info_path)
        for change in change_list:
            msg = " ".join(rest.get_commit(change)['message'].split('\n'))
            if reg.search(msg):
                print('The {} ticket is: {}'.format(ticket_type, change))
                return change
        raise Exception("Can't get {} ticket!".format(ticket_type))


def get_jira_id(integration_change, gerrit_info_path):
    print("Getting JIRA ID from {0} commit message".format(integration_change))
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    rest.init_cache(1000)
    description, rest_id = generate_bb_json.get_description(rest, integration_change)
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
    jenkins_server = Jenkins(jenkins_url, timeout=180, ssl_verify=False)
    jenkins_job = jenkins_server[job_name]
    build = jenkins_job.get_build(build_number)
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


def auto_update_build_info(integration_tag,
                           pkg_name,
                           stream,
                           gerrit_info_path,
                           database_info_path,
                           job_url=None,
                           dry_run=False):
    integration_change = integration_tag.split('_')[0]
    jira_key = get_jira_id(integration_change, gerrit_info_path)
    knife_link_temp = 'https://artifactory-espoo1.int.net.nokia.com/artifactory/' \
                      'mnp5g-central-public-local/Knife/{pkg_name}/'
    knife_link = knife_link_temp.format(pkg_name=pkg_name)
    if job_url:
        # example of job_url: http://production-5g.cb.scm.nsn-rdnet.net/job/job_name/build_number/
        job_name = job_url.strip('/').split('/')[-2]
        build_number = int(job_url.strip('/').split('/')[-1])
        start_time, end_time = get_job_timestamp(JENKINS_URL, job_name, build_number)
    else:
        print("Can't get build start_time and end_time because job url is missing")
        start_time = end_time = ''
    print("Update integration package in skytrack: {0}".format(pkg_name))
    if dry_run:
        print("DRY-RUN MODE:")
        print("integration_name: {jira_key}".format(jira_key=jira_key))
        print ("product: 5G")
        print ("package_name: {pkg_name}".format(pkg_name=pkg_name))
        print ("mini_branch: {stream}".format(stream=stream))
        print ("type_name: Integration Build")
        print ("link: {knife_link}".format(knife_link=knife_link))
        return
    skytrack_detail_api(
        integration_name=jira_key,
        product='5G',
        package_name=pkg_name,
        mini_branch=stream,
        type_name='Integration Build',
        status=1,
        link=knife_link,
        start_time=start_time,
        end_time=end_time
    )
    knife_info_in_link = "<a href='{knife_link}'>{pkg_name}</a>".format(knife_link=knife_link, pkg_name=pkg_name)
    update_events(
        database_info_path=database_info_path,
        integration_name=jira_key,
        description="{0} integration package created: {1}".format(stream, knife_info_in_link)
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


def add_integration_tickets(jira_key, change_list, database_info_path, dry_run=False):
    mydb = mysql_api.init_from_yaml(database_info_path, server_name='skytrack')
    mydb.init_database('skytrack')
    print('Add change info for {0}'.format(jira_key))
    if dry_run:
        print('DRY-RUN MODE:')
        print('changes for {0} will be added'.format(jira_key))
        return
    for gerrit_change in change_list:
        values = {
            'topic_key': jira_key,
            '`change`': gerrit_change
        }
        mydb.insert_info(
            table='t_integration_topic',
            values=values
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
    formated_start_time = start_time.replace('/', '-') if start_time else start_time
    formated_end_time = end_time.replace('/', '-') if end_time else end_time
    start_time = int(time.mktime(datetime.datetime.strptime(
        formated_start_time, "%Y-%m-%d %H:%M:%S").timetuple())) * 1000 \
        if formated_start_time and string_time_format_validator(formated_start_time) else int(time.time()) * 1000
    end_time = int(time.mktime(datetime.datetime.strptime(
        formated_end_time, "%Y-%m-%d %H:%M:%S").timetuple())) * 1000 \
        if formated_end_time and string_time_format_validator(formated_end_time) else int(time.time()) * 1000
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


def update_events(database_info_path, integration_name, description, highlight=False, date=None,
                  user='SKYTRACK'):
    mydb = mysql_connector(database_info_path, 'skytrack', 'skytrack')
    date = date if date else datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    values = {
        'integration_name': integration_name,
        'description': description,
        'hightlight': int(highlight),
        'modify_user': user,
        'date': date
    }
    mydb.insert_info(
        table='t_integration_events',
        values=values
    )


def update_integration_mode(database_info_path, issue_key, integration_mode, fixed_build=None):
    mydb = mysql_connector(database_info_path, 'skytrack', 'skytrack')
    replacements = {
        'integration_mode': integration_mode,
        'fixed_base': ''
    } if not fixed_build else {
        'integration_mode': integration_mode,
        'fixed_base': fixed_build
    }
    mydb.update_info(
        table='t_issue',
        replacements=replacements,
        conditions={
            'issue_key': issue_key
        }
    )


def if_issue_exist(database_info_path, issue_key):
    mydb = mysql_connector(database_info_path, 'skytrack', 'skytrack')
    sql = "SELECT * FROM t_issue WHERE issue_key='{0}'".format(issue_key)
    return True if mydb.executor(sql, output=True) else False


def get_changes_from_db(change_no, database_info_path, gerrit_info_path, only_id=True):
    mydb = mysql_connector(database_info_path, 'skytrack', 'skytrack')
    jira_key = get_jira_id(change_no, gerrit_info_path)
    sql = 'SELECT distinct `change`, project  FROM t_commit_info where issue_key="{}";'.format(jira_key)
    changes = mydb.executor(sql, output=True)
    changes_list = list()
    if only_id:
        for change in changes:
            changes_list.append(change[0])
        return changes_list
    return changes


def get_env_change(change_no, database_info_path, gerrit_info_path):
    integration_change = None
    env_change = None
    changes = get_changes_from_db(change_no, database_info_path, gerrit_info_path, only_id=False)
    root_change = get_specified_ticket(change_no, database_info_path, gerrit_info_path)
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    commits = RootChange(rest, root_change).get_all_changes_by_comments(with_root=True)
    for change_id, project in changes:
        if change_id in commits:
            if project == 'MN/5G/COMMON/integration':
                print("Get integration change {}: {}".format(change_id, project))
                integration_change = change_id
            if project == 'MN/5G/COMMON/env':
                print("Get env change {}: {}".format(change_id, project))
                env_change = change_id
    if env_change:
        return env_change
    if integration_change:
        return integration_change
    raise Exception("Can't get env ticket!")


if __name__ == '__main__':
    fire.Fire()
