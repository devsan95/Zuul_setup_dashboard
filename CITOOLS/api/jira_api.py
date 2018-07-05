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

    def close_issue(self, issue_name):
        transitions = self.jira.transitions(issue_name)
        transition_id = [t['id'] for t in transitions if t['name'] == u'Close Issue'][0]
        self.jira.transition_issue(issue_name, transition_id)


if __name__ == '__main__':
    jira_op = JIRAPI("autobuild_c_ou", "*****")
    jira_op.replace_issue_title("SCMHGH-5999", "RCP2.0_5GRAC_18.666", "RCP2.0_5GRAC_18.777")
    jira_op.close_issue("SCMHGH-5999")
