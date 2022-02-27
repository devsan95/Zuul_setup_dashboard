import fire
import datetime

import skytrack_database_handler

from api import mysql_api
from api import gerrit_rest


def get_topic_open_changes(topic, mysql, rest):
    open_changes = list()
    sql = "SELECT `change` FROM t_commit_component WHERE issue_key='{0}'".format(topic)
    changes = mysql.executor(sql, output=True)
    for change in changes:
        try:
            change_status = rest.get_change(change[0])['status']
        except Exception as e:
            print("Can't get change info: {0} because of {1}".format(change_status, e))
            continue
        if change_status in ['ABANDONED', 'MERGED']:
            continue
        open_changes.append(change[0])
    return open_changes


def get_old_topics(timeline, start_timeline, mysql):
    sql = "SELECT issue_key, summary, status FROM t_issue WHERE create_time < '{0}' AND create_time > '{1}'"\
        .format(timeline, start_timeline)
    return mysql.executor(sql, output=True)


def run(days, gerrit_yaml, mysql_yaml, interval=30, dry_run=True, skip_doubt=True):
    open_status = ['Open', 'Backlog']
    timeline = datetime.datetime.now() - datetime.timedelta(days=days)
    start_timeline = datetime.datetime.now() - datetime.timedelta(days=int(days) + int(interval))
    mysql = mysql_api.init_from_yaml(mysql_yaml, 'skytrack')
    mysql.init_database('skytrack')
    rest = gerrit_rest.init_from_yaml(gerrit_yaml)
    old_topics = get_old_topics(timeline, start_timeline, mysql)
    doubtable_topics = list()
    for topic in old_topics:
        if 'dev/test' not in topic[1] and topic[2] in open_status and skip_doubt:
            doubtable_topics.append(topic)
            continue
        print('Handling Integration Topic: {0}'.format(topic[0]))
        for change in get_topic_open_changes(topic[0], mysql, rest):
            if dry_run:
                print('DRY-RUN: abandoning change: {0}'.format(change))
            else:
                try:
                    rest.abandon_change(change)
                    print('change {0} abandoned'.format(change))
                except Exception as e:
                    print('Abandon change {0} failed, because {1}'.format(change, e))
        if topic[2] in open_status:
            if dry_run:
                print('DRY-RUN: Closing JIRA: {0}'.format(topic[0]))
            else:
                try:
                    skytrack_database_handler.update_ticket_status(topic[0], 'Closed', mysql_yaml)
                    print('Topic {0} closed'.format(topic[0]))
                except Exception as e:
                    print('Close topic {0} failed, because {1}'.format(topic[0], e))

    for doubtable_topic in doubtable_topics:
        print("Below doutable topices need to be handled manually")
        print('{0}: {1}'.format(doubtable_topic[0], doubtable_topic[1]))


if __name__ == '__main__':
    fire.Fire(run)
