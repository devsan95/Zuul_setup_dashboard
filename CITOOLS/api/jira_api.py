#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date    : 2018-07-04 15:34:05
# @Author  : robzhu (Robin.zhu@nokia-sbell.com)
# @Site    : HangZhou
# @Desc :

from jira import JIRA


class JIRAPI(object):
    """docstring for JIRAPI."""

    def __init__(self, user, passwd, server=None):
        if server is None:
            server = "https://jira3.int.net.nokia.com"
        self.jira = JIRA(
            server=server,
            basic_auth=(user, passwd)
        )

    def get_issue_title(self, issue_name):
        issue = self.jira.issue(issue_name)
        title = issue.raw["fields"]["summary"].encode('utf-8')
        return title

    def update_issue_title(self, issue_name, new_title):
        issue = self.jira.issue(issue_name)
        issue.update(fields=dict(summary=new_title))

    def replace_issue_title(self, issue_name, old_str, new_str):
        issue = self.jira.issue(issue_name)
        title = issue.raw["fields"]["summary"].encode('utf-8')
        # print issue.raw["fields"]["status"]
        new_title = title.replace(old_str, new_str)
        if new_title == title:
            raise Exception("title has not change,replace failed.")
        issue.update(fields=dict(summary=new_title))

    def get_issue_assignee(self, issue_name):
        issue = self.jira.issue(issue_name)
        assignee = issue.fields.assignee
        return assignee

    def close_issue(self, issue_name):
        transitions = self.jira.transitions(issue_name)
        print("-------------transition value------------")
        print(transitions)
        status_with_ids = [(t["name"], t["id"]) for t in transitions]
        transition_id = [one[1] for one in status_with_ids if one[0] == u'Close Issue']
        if transition_id:
            transition_id = transition_id[0]
            self.jira.transition_issue(issue_name, transition_id)
        else:
            # current status has no close issue options,open it first.
            transition_id = [one[1] for one in status_with_ids if one[0] == u'Open Issue'][0]
            self.jira.transition_issue(issue_name, transition_id)
            self.close_issue(issue_name)

    def transition_issue(self, issue_name, transition):
        transitions = self.jira.transitions(issue_name)
        status_with_ids = [(t["name"], t["id"]) for t in transitions]
        transition_id = \
            [one[1] for one in status_with_ids if one[0] == transition]
        if transition_id:
            transition_id = transition_id[0]
            self.jira.transition_issue(issue_name, transition_id)
        else:
            raise Exception('No transition')

    def create_issue(self, fields):
        return self.jira.create_issue(fields=fields)

    def search_issue(self, jql):
        return self.jira.search_issues(jql)

    def open_issue(self, jira_id):
        transitions = self.jira.transitions(jira_id)
        status_with_ids = [(t["name"], t["id"]) for t in transitions]
        transition_id = [one[1] for one in status_with_ids if one[0] == u'Open Issue']
        if transition_id:
            transition_id = transition_id[0]
            self.jira.transition_issue(jira_id, transition_id)
        else:
            raise Exception('Can not find open transition of {}'.format(jira_id))

    def api(self):
        return self.jira


if __name__ == '__main__':
    jira_op = JIRAPI("autobuild_c_ou", "a4112fc4")
    # jira_op.replace_issue_title("SCMHGH-6054", "RCP2.0_5GRAC_18.666", "RCP2.0_5GRAC_18.777")
    jira_op.close_issue("SCMHGH-6054")
