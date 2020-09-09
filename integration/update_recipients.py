#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import fire
import re
from api import gerrit_rest
from api import skytrack_log

COMMON_REVIEWER = ['gitCMBot', 'ca_5gint', 'scmtaci']
MAIL_REGEX = r'^[^@]+@(nokia|nokia-sbell|internal\.nsn|groups\.nokia)\.com'


def add_reviewers(rest, rest_id, reviewers):
    for reviewer in reviewers:
        rest.add_reviewer(rest_id, reviewer)
        print('[Info] successfully added reviewer {}'.format(reviewer))


def delete_reviewers(rest, rest_id, reviewers):
    old_reviewers_json = rest.get_reviewer(rest_id)
    reviewers_mail_list = [x['email'] for x in old_reviewers_json if 'email' in x]
    for reviewer in reviewers:
        if reviewer in reviewers_mail_list:
            rest.delete_reviewer(rest_id, reviewer)
            print('[Info] successfully deleted reviewer {}'.format(reviewer))


def reset_reviewers(rest, rest_id, reviewers):
    print('[Info]Reset reviewers, delete old reviewers first .....')
    old_reviewers_json = rest.get_reviewer(rest_id)
    reviewers_username_list = [x['username'] for x in old_reviewers_json if 'username' in x and
                               x['username'] not in COMMON_REVIEWER]
    delete_reviewers(rest, rest_id, reviewers_username_list)
    print('[Info]Reset reviewers, now add new reviewers .....')
    add_reviewers(rest, rest_id, reviewers)


def check_input_reviewers(reviewers):
    if not reviewers.strip():
        msg = '[Error]: Input reviewers list is empty! Please input valid reviewers!'
        skytrack_log.skytrack_output(msg)
        raise Exception(msg)
    reviewer_list = reviewers.strip().split(';')
    new_reviewer_list = []
    warn_msg = []
    for r in reviewer_list:
        m = re.match(MAIL_REGEX, r)
        if m:
            new_reviewer_list.append(r)
        else:
            warn_msg.append('[Warn] Reviewer {} is not a valid mail !'.format(r))
    if warn_msg:
        skytrack_log.skytrack_output(warn_msg)
    return new_reviewer_list


def main(change_id, gerrit_info_path, operation, reviewers=None):
    reviewer_list = check_input_reviewers(reviewers)
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    # rest_id = rest.get_ticket(change_id)['id']
    if operation == 'add':
        add_reviewers(rest, change_id, reviewer_list)
    elif operation == 'remove':
        delete_reviewers(rest, change_id, reviewer_list)
    elif operation == 'reset':
        reset_reviewers(rest, change_id, reviewer_list)
    else:
        raise Exception('[Error]: unrecognized operation!')


if __name__ == '__main__':
    fire.Fire(main)
