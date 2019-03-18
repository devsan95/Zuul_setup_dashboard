#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import argparse
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
    new_mes = ""
    if "with-zuul-rebase" in with_zuul_rebase:
        if "<with-zuul-rebase>" in message:
            if "<without-zuul-rebase>" not in message:
                print "Already in with-zuul-rebase mode, no need to update."
                return message
            else:
                new_mes = message.replace("<without-zuul-rebase>", "")
        elif "<without-zuul-rebase>" in message:
            new_mes = message.replace("<without-zuul-rebase>", "<with-zuul-rebase>")
        else:
            if "Remarks:" in message:
                new_mes = message.replace("Remarks:", "<with-zuul-rebase>\nRemarks:")
            else:
                new_mes = message.replace("Change-Id:", "<with-zuul-rebase>\nChange-Id:")
    if "without-zuul-rebase" in with_zuul_rebase:
        if "<without-zuul-rebase>" in message:
            if "<with-zuul-rebase>" not in message:
                print "Already in without-zuul-rebase mode, no need to update."
                return message
            else:
                new_mes = message.replace("<with-zuul-rebase>", "")
        elif "<with-zuul-rebase>" in message:
            new_mes = message.replace("<with-zuul-rebase>", "<without-zuul-rebase>")
        else:
            if "Remarks:" in message:
                new_mes = message.replace("Remarks:", "<without-zuul-rebase>\nRemarks:")
            else:
                new_mes = message.replace("Change-Id:", "<without-zuul-rebase>\nChange-Id:")
    return new_mes


def update_message_title(message, with_zuul_rebase):
    mes = ""
    if "with-zuul-rebase" in with_zuul_rebase:
        if "[NOREBASE]" in message:
            mes = message.replace("[NOREBASE]", "")
        else:
            print "[NOREBASE] not exist, no need to update."
            return message
    if "without-zuul-rebase" in with_zuul_rebase:
        if "[NOREBASE]" in message:
            print "[NOREBASE] exist, no need to update."
            return message
        else:
            mes = message.replace("[none]", "[none] [NOREBASE]")
    return mes


def _main(change_id, with_zuul_rebase, rest_url, rest_user, rest_pwd, auth_type):
    rest = api.gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()
    update_with_rebase_info(rest, change_id, with_zuul_rebase)


def update_with_rebase_info(rest, change_id, with_zuul_rebase):
    changes = parse_comments(change_id, rest)

    exception_list = []
    for change in changes:
        print('Updating {}'.format(change))
        try:
            mess = retry.retry_func(
                retry.cfn(rest.get_commit, change),
                max_retry=10, interval=3
            )
            message = update_message(mess['message'], with_zuul_rebase)
            new_message = update_message_title(message, with_zuul_rebase)
            if mess['message'] == new_message:
                continue
            rest.change_commit_msg_to_edit(change, new_message)
            rest.publish_edit(change)
        except Exception as err:
            exception_list.append(err)
            print(err)

    if exception_list:
        raise Exception("[Error] some tickets update failed, reasons as below: {}".format(exception_list))
    else:
        print("[Info] all tickets updated successfully!")


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
