#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import fire
import urllib3
import skytrack_database_handler
from api import gerrit_rest, jira_api
from api import config
from mod import integration_change as inte_change
from mod import common_regex

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


CONF = config.ConfigTool()
CONF.load('jira')
JIRA_DICT = CONF.get_dict('jira3')

DEFAULT_JIRA_URL = JIRA_DICT['server']
DEFAULT_USER = JIRA_DICT['user']
DEFAULT_PASSWD = JIRA_DICT['password']


def publish_change(rest, change_number, commit_msg):
    try:
        rest.delete_edit(change_number)
    except Exception as e:
        print(e)
    try:
        rest.change_commit_msg_to_edit(change_number, commit_msg)
    except Exception as e:
        if "New commit message cannot be same as existing commit message" in str(e):
            pass
        else:
            raise Exception(e)
    rest.publish_edit(change_number)


def update_topic_name(rest, change_number, topic_name):
    change_obj = inte_change.IntegrationChange(rest, change_number)
    commit_msg_obj = inte_change.IntegrationCommitMessage(change_obj)
    old_msg = commit_msg_obj.get_msg()
    commit_msg_obj.update_topic(topic_name)
    new_msg = commit_msg_obj.get_msg()

    need_publish = True
    if old_msg == new_msg:
        need_publish = False

    if need_publish:
        print('[Info] Commit message need to be updated for {}'.format(change_number))
        publish_change(rest, change_number, new_msg)
    else:
        print('[Info] No need to update commit message for {}'.format(change_number))


def update_topic_in_jira(jira_id, old_topic_name, new_topic_name):
    try:
        jira_op = jira_api.JIRAPI(user=DEFAULT_USER, passwd=DEFAULT_PASSWD,
                                  server=DEFAULT_JIRA_URL)
        jira_title = jira_op.get_issue_title(jira_id)
        if old_topic_name and old_topic_name in jira_title:
            jira_op.replace_issue_title(jira_id, old_topic_name, new_topic_name)
        else:
            jira_title_re = common_regex.jira_title_reg.search(jira_title)
            if jira_title_re:
                jira_op.replace_issue_title(jira_id, jira_title_re.groups()[4], new_topic_name)
    except Exception as e:
        print e
        print('Jira update error')


def main(root_change, new_topic_name, gerrit_info_path, database_info_path=None):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    root_obj = inte_change.RootChange(rest, root_change)
    component_list = root_obj.get_all_changes_by_comments(with_root=True)
    print("[Info] All the components change including root and manager change:\n{}".format(component_list))

    for comp in component_list:
        update_topic_name(rest, comp, new_topic_name)

    jira_id = root_obj.get_jira_id()
    old_topic_name = None
    if root_obj.get_feature_id():
        old_topic_name = root_obj.get_feature_id()
    elif root_obj.get_version():
        old_topic_name = root_obj.get_version()
    update_topic_in_jira(jira_id, old_topic_name, new_topic_name)

    if database_info_path:
        skytrack_database_handler.update_events(
            database_info_path=database_info_path,
            integration_name=jira_id,
            description="Integration Topic Change To {0}".format(new_topic_name),
            highlight=True
        )


if __name__ == '__main__':
    fire.Fire(main)
