import re

import fire

from api import gerrit_rest
from api import mysql_api
from generate_bb_json import get_description


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


def update_build_info(integration_change,
                      pkg_info_file,
                      gerrit_info_path,
                      database_info_path,
                      dry_run=False):
    jira_key = get_jira_id(integration_change, gerrit_info_path)
    mydb = mysql_api.init_from_yaml(database_info_path, server_name='skytrack')
    mydb.init_database('skytrack')
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
        return
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


def clean_build_info(integration_change, gerrit_info_path, database_info_path, dry_run=False):
    jira_key = get_jira_id(integration_change, gerrit_info_path)
    mydb = mysql_api.init_from_yaml(database_info_path, server_name='skytrack')
    mydb.init_database('skytrack')
    print('Clean up {0} entity build info'.format(jira_key))
    if dry_run:
        print('DRY-RUN MODE:')
        print('entity_build, entity_build_status and entity_test_status will be cleanup')
        return
    mydb.update_info(
        table='t_issue',
        replacements={
            'entity_build': None,
            'entity_test_status': 0
        },
        conditions={
            'issue_key': jira_key
        }
    )


if __name__ == '__main__':
    fire.Fire()
