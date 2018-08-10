from api.jira_api import JIRAPI
import fire
import yaml
import datetime
import copy
import os
import arrow


def generate_due_time(peroid, timezone=None):
    now = arrow.now()
    if timezone:
        now = now.to(timezone)
    # if peroid == 'minute':
    #     due = datetime.datetime(year=now.year, month=now.month,
    #                             day=now.day, hour=now.hour, minute=now.minute,
    #                             second=0)
    #     period_time = due.strftime('%Y-%m-%d %H:%M')
    # elif peroid == 'hour':
    #     due = datetime.datetime(year=now.year, month=now.month,
    #                             day=now.day, hour=now.hour, minute=0,
    #                             second=0)
    #     period_time = due.strftime('%Y-%m-%d %-H o\'clock')
    if peroid == 'day':
        due = datetime.datetime(year=now.year, month=now.month,
                                day=now.day, hour=0, minute=0,
                                second=0)
        period_time = due.strftime('%Y-%m-%d')
    elif peroid == 'month':
        due = datetime.datetime(year=now.year, month=now.month,
                                day=1, hour=0, minute=0,
                                second=0)
        period_time = due.strftime('%Y-%m')
    elif peroid == 'year':
        due = datetime.datetime(year=now.year, month=1,
                                day=1, hour=0, minute=0,
                                second=0)
        period_time = due.strftime('%Y')
    elif peroid == 'week':
        today = datetime.date.today()
        last_sunday = today - datetime.timedelta(days=(today.weekday() + 1))
        due = datetime.datetime(year=last_sunday.year, month=last_sunday.month,
                                day=last_sunday.day, hour=0, minute=0,
                                second=0)
        wk = now.isocalendar()[1]
        period_time = 'Week {}'.format(wk)
    else:
        raise Exception('Not supported peroid')

    return due, period_time


def generate_jql(ticket, meta, due, search_new=False):
    # project = HZSCMWORK
    # AND
    # issuetype = Task
    # AND
    # labels = "Type:Meeting"
    # AND
    # component = "Project: Zuul"
    # AND
    # assignee = zhxie
    # AND
    # createdDate < "2018-8-9 10:00"
    jqls = []
    jqls.append('project = "{}"'.format(ticket['project']['key']))
    jqls.append('issuetype = "{}"'.format(ticket['issuetype']['name']))
    for component in ticket['components']:
        jqls.append('component = "{}"'.format(component['name']))
    for label in ticket['labels']:
        jqls.append('labels = "{}"'.format(label))
    jqls.append('assignee = "{}"'.format(ticket['assignee']['name']))
    if search_new:
        jqls.append('"Created" >= "{}"'.format(due.strftime('%Y-%m-%d')))
        done_jqls = []
        for status in meta['close_status']:
            done_jqls.append('status != "{}"'.format(status))
        jqls.append(' AND '.join(done_jqls))
    else:
        jqls.append('"Created" < "{}"'.format(due.strftime('%Y-%m-%d')))
        done_jqls = []
        for status in meta['close_status']:
            done_jqls.append('status = "{}"'.format(status))
        jqls.append('({})'.format(' OR '.join(done_jqls)))
    jql = ' AND '.join(jqls)
    print('JQL is {}'.format(jql))
    return jql


def get_default_path():
    path_list = [
        'jira.yml',
        'jira.yml',
        'example.yml',
        'example.yml',
    ]
    for path in path_list:
        if os.path.exists(path):
            return path
    raise Exception('No usable yaml file.')


def run(yml_path=None):
    if not yml_path:
        yml_path = get_default_path()
    with open(yml_path) as f:
        yobj = yaml.load(f)
    meta = yobj['meta']
    tickets = yobj['tickets']
    jira = JIRAPI(meta['user'], meta['pwd'], server=meta['url'])
    for ticket in tickets:
        period = meta['period']
        due, period_time = generate_due_time(period, meta['timezone'])
        # search outdated tickets and close
        jql = generate_jql(ticket, meta, due)
        old_issues = jira.search_issue(jql)
        for issue in old_issues:
            print('Issue [{}] is not done, close it'.format(issue))
            jira.transition_issue(issue.key, 'Done')
        # create new tickets
        new_jql = generate_jql(ticket, meta, due, True)
        new_issues = jira.search_issue(new_jql)
        if not new_issues:
            print('No issue find, create')
            fields = copy.deepcopy(ticket)
            fields['description'] = fields['description'].format(period_time=period_time)
            fields['summary'] = fields['summary'].format(period_time=period_time)
            jnew = jira.create_issue(fields)
            jira.transition_issue(jnew.key, 'In Progress')
            print('Issue [{}] is created'.format(jnew))
        else:
            print('Existing issue(s):')
            for issue in new_issues:
                print(issue)


if __name__ == '__main__':
    fire.Fire(run)
