#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import argparse
import re
import sys
import traceback

import api.file_api
import api.gerrit_api
import api.gerrit_rest
from api import retry
from abandon_changes import parse_comments


def _parse_args():
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('change_id', type=str, help='change id')
    parser.add_argument('with_zuul_rebase', type=str, help='with or without zuul rebase')
    parser.add_argument('rest_url', type=str, help='')
    parser.add_argument('rest_user', type=str, help='')
    parser.add_argument('rest_pwd', type=str, help='')
    parser.add_argument('auth_type', type=str, default='digest', help='')
    args = parser.parse_args()
    return vars(args)


def update_message(message, with_zuul_rebase):
    if "with-zuul-rebase" in with_zuul_rebase:
        if "<with-zuul-rebase>" in message:
            if "<without-zuul-rebase>" not in message:
                print "Already in with-zuul-rebase mode, no need to update."
                return False
            else:
                new_mes = re.sub("<without-zuul-rebase>", "", message)
                return new_mes
        elif "<without-zuul-rebase>" in message:
            new_mes = re.sub("<without-zuul-rebase>", "<with-zuul-rebase>", message)
            return new_mes
        else:
            if "Remarks:" in message:
                new_mes = re.sub("Remarks:", "<with-zuul-rebase>\nRemarks:", message)
                return new_mes
            else:
                new_mes = re.sub("Change-Id:", "<with-zuul-rebase>\nChange-Id:", message)
                return new_mes
    if "without-zuul-rebase" in with_zuul_rebase:
        if "<without-zuul-rebase>" in message:
            if "<with-zuul-rebase>" not in message:
                print "Already in without-zuul-rebase mode, no need to update."
                return False
            else:
                new_mes = re.sub("<with-zuul-rebase>", "", message)
                return new_mes
        elif "<with-zuul-rebase>" in message:
            new_mes = re.sub("<with-zuul-rebase>", "<without-zuul-rebase>", message)
            return new_mes
        else:
            if "Remarks:" in message:
                new_mes = re.sub("Remarks:", "<without-zuul-rebase>\nRemarks:", message)
                return new_mes
            else:
                new_mes = re.sub("Change-Id:", "<without-zuul-rebase>\nChange-Id:", message)
                return new_mes


def _main(change_id, with_zuul_rebase, rest_url, rest_user, rest_pwd, auth_type):
    rest = api.gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()
    changes = parse_comments(change_id, rest)

    for change_id in changes:
        print('Updating {}'.format(change_id))
        try:
            mess = retry.retry_func(
                retry.cfn(rest.get_commit, change_id),
                max_retry=10, interval=3
            )
            new_message = update_message(mess['message'], with_zuul_rebase)
            if not new_message:
                continue
            rest.change_commit_msg_to_edit(change_id, new_message)
            rest.publish_edit(change_id)
        except Exception as e:
            print(e)


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
