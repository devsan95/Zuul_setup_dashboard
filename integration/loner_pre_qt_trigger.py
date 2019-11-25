import re
import fire
import json
from copy import deepcopy
from xml.etree import ElementTree

from scm_tools.wft.api import WftAPI
from scm_tools.wft import json_releasenote

from operate_commit_message import OperateCommitMessage
from api import mysql_api, gerrit_rest, jira_api
from mod import wft_tools


def get_loner_from_wft(loner_prefix, status):
    wft = WftAPI()
    custom_filter = "custom_filter[baseline_regexp]=1"\
                    "&custom_filter[baseline]=^{loner_prefix}" \
                    "&custom_filter[sorting_field]=date" \
                    "&custom_filter[sorting_direction]=desc" \
                    "&custom_filter[state][]={status}" \
                    "&custom_filter[items]=1"
    latest_loner_release = wft.get_build_list_from_custom_filter(custom_filter.format(
        loner_prefix=loner_prefix,
        status=status
    ))
    et = ElementTree.fromstring(latest_loner_release)
    return et.find('build/baseline').text


def get_loner_topic_from_skytrack(mysql, stream):
    print('Getting loner topic from skytrack')
    regex = re.compile(r'Loner pre-QT on (.*)-(L.*) Integration')
    sql = "SELECT * FROM t_issue WHERE status = " \
          "'Open' AND summary LIKE '%Loner Pre-QT%'"
    search_result = mysql.executor(sql, output=True)
    return {regex.match(topic[3]).group(2): {"issue_key": topic[1],
                                             "stream": regex.match(topic[3]).group(1)}
            for topic in search_result if stream in regex.match(topic[3]).group(1)}


def get_loner_artifactory_link(loner_version):
    print('Getting {0} artifactory link from WFT'.format(loner_version))
    release_note = json_releasenote.Releasenote.get(loner_version, project='Common',
                                                    name=loner_version.split('_')[0])
    download = release_note.rn_instance.json_dict['download']
    return download[0]['path']


def get_loner_ticket(mysql, component, topic_info):
    print('Getting {0} ticket from skytrack'.format(component))
    sql = "SELECT * FROM t_commit_component WHERE issue_key = '{issue_key}' AND component = '{component_name}'".format(
        issue_key=topic_info['issue_key'],
        component_name=component.lower()
    )
    search_result = mysql.executor(sql, output=True)
    if not search_result:
        raise Exception("Can not find loner change in {0}".format(topic_info['issue_key']))
    return search_result[0][1]


def update_loner_topic(loner_version, sql_yaml, gerrit_yaml, stream, topic_info=None):
    print('Will update {0} in skytrack'.format(loner_version))
    mysql = mysql_api.init_from_yaml(sql_yaml, server_name='skytrack')
    mysql.init_database('skytrack')
    rest = gerrit_rest.init_from_yaml(gerrit_yaml)

    # Update topic info in all tickets and JIRA
    root_ticket = get_loner_ticket(mysql, component='root_monitor', topic_info=topic_info)
    msg_obj = OperateCommitMessage(gerrit_info_path=gerrit_yaml, root_change=root_ticket)
    old_topic, new_topic = msg_obj.update_topic(loner_version)
    jira_op = jira_api.JIRAPI("autobuild_c_ou", "a4112fc4")
    jira_op.replace_issue_title(topic_info['issue_key'], old_topic, new_topic)

    # Update base build in integration change
    integration_ticket = get_loner_ticket(mysql, component='integration', topic_info=topic_info)
    print('Integration ticket: {0}'.format(integration_ticket))
    latest_l3_call_build = wft_tools.get_latest_qt_passed_build(stream, status='released')
    rest.review_ticket(integration_ticket, message='update_base:{0},{1}'.format(
        latest_l3_call_build[0].split('_')[-1].rsplit('.', 1)[0],
        latest_l3_call_build[0].split('_')[-1]
    ))
    print('Updated {0} as new base in {1}'.format(latest_l3_call_build[0], integration_ticket))
    topic_info_content = deepcopy(topic_info)
    topic_info_content['loner_version'] = loner_version
    topic_info_content['integration_ticket'] = integration_ticket
    with open('topic_info.json') as json_file:
        json.dump(topic_info_content, json_file)
    update_loner_info(sql_yaml, gerrit_yaml, 'topic_info.json')


def update_loner_info(sql_yaml, gerrit_yaml, topic_info_file):
    topic_info = json.load(open(topic_info_file))
    loner_version = topic_info['loner_version']
    integration_ticket = topic_info['integration_ticket']
    mysql = mysql_api.init_from_yaml(sql_yaml, server_name='skytrack')
    mysql.init_database('skytrack')
    rest = gerrit_rest.init_from_yaml(gerrit_yaml)
    # update loner version in fake loner change
    loner_ticket = get_loner_ticket(mysql,
                                    component=loner_version.split('_')[0],
                                    topic_info=topic_info)
    print('Loner ticket: {0}'.format(loner_ticket))
    loner_artifactory_link = get_loner_artifactory_link(loner_version)
    print('Loner artifactory link: {0}'.format(loner_artifactory_link))
    src_uri = loner_artifactory_link + '/' + 'L1SW-{0}.tgz'.format(loner_version)
    rest.review_ticket(loner_ticket, message='update_component:{loner},SRC_URI,{src_uri}'.format(
        loner=loner_version.split('_')[0].lower(),
        src_uri=src_uri
    ), labels={'Code-Review': 1})
    print('Updated {0} in {1}'.format(loner_version, loner_ticket))

    # Retrigger integration build
    rest.review_ticket(integration_ticket, message='reexperiment')


def parameter_creator(integration_yaml, loner_version, stream, mode, promoted_user_id):
    latest_l3_call_build = wft_tools.get_latest_qt_passed_build(stream, status='released')
    stream_num = latest_l3_call_build[0].split('_')[-1].rsplit('.', 1)[0]
    with open('create_feature.prop', 'w+') as parameters_file:
        parameters_file.writelines(
            """structure_file={structure_file}
streams={streams}
PROMOTED_USER_ID={promoted_user_id}
integration_mode={integration_mode}
version_name={version_name}""".format(structure_file=integration_yaml,
                                      version_name=loner_version,
                                      streams=stream_num,
                                      integration_mode=mode,
                                      promoted_user_id=promoted_user_id)
        )


def trigger(loner_prefix, stream, integration_yaml, sql_yaml, gerrit_yaml, mode, promoted_user_id,
            status, baseline=None):
    mysql = mysql_api.init_from_yaml(sql_yaml, server_name='skytrack_test')
    mysql.init_database('skytrack')
    loner_version = baseline if baseline else get_loner_from_wft(loner_prefix, status)
    print('Latest Loner Release: {0}'.format(loner_version))
    loner_topics = get_loner_topic_from_skytrack(mysql, stream)
    if not loner_version or loner_version in loner_topics:
        print('No new loner version in WFT')
        return
    loner_handled = False
    for topic, topic_info in loner_topics.items():
        if stream in topic_info['stream']:
            update_loner_topic(loner_version, sql_yaml, gerrit_yaml, stream=stream,
                               topic_info=topic_info)
            loner_handled = True
    if not loner_handled:
        print('Will create {0} in skytrack'.format(loner_version))
        parameter_creator(integration_yaml, loner_version, stream, mode, promoted_user_id)


if __name__ == '__main__':
    fire.Fire()
