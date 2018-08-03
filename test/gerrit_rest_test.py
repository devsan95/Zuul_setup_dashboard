#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import argparse
import sys
import traceback

from api import gerrit_rest


def strip_end(text, suffix):
    if not text.endswith(suffix):
        return text
    return text[:len(text) - len(suffix)]


def strip_begin(text, prefix):
    if not text.startswith(prefix):
        return text
    return text[len(prefix):]


def _parse_args():
    parser = argparse.ArgumentParser(description='Update Submodule')
    parser.add_argument('rest_url', type=str,
                        help='')
    parser.add_argument('rest_user', type=str,
                        help='')
    parser.add_argument('rest_pwd', type=str,
                        help='')
    parser.add_argument('auth_type', type=str, default='digest',
                        help='')
    args = parser.parse_args()
    return vars(args)


def rebase_change(rest, change_id):
    rest_id = rest.get_ticket(change_id)['id']
    list = rest.get_file_list(rest_id)
    file_content = {}
    for file in list:
        file = file.split('\n', 2)[0]
        if file != '/COMMIT_MSG':
            changeset = rest.get_file_change(file, rest_id)
            if 'new' in changeset \
                    and 'old' in changeset \
                    and changeset['new'] != changeset['old']:
                file_content[file] = strip_begin(changeset['new'],
                                                 'Subproject commit ')
                rest.restore_file_to_change(rest_id, file)
    rest.publish_edit(rest_id)
    print(rest.rebase(rest_id))
    for file, content in file_content.items():
        rest.add_file_to_change(rest_id, file, content)
    rest.publish_edit(rest_id)


def merge_change(rest, change_id_dst, change_id_src):
    rest_id_dst = rest.get_ticket(change_id_dst)['id']
    rest_id_src = rest.get_ticket(change_id_src)['id']
    list = rest.get_file_list(rest_id_src)
    file_content = {}
    for file in list:
        file = file.split('\n', 2)[0]
        if file != '/COMMIT_MSG':
            changeset = rest.get_file_change(file, rest_id_src)
            if 'new' in changeset \
                    and 'old' in changeset \
                    and changeset['new'] != changeset['old']:
                file_content[file] = strip_begin(changeset['new'],
                                                 'Subproject commit ')

    for file, content in file_content.items():
        rest.add_file_to_change(rest_id_dst, file, content)
    rest.publish_edit(rest_id_dst)


def change_commit_msg(rest, change_id, msg):
    info = rest.get_ticket(change_id)
    message = msg + '\n' + info['subject']
    rest.set_commit_message(info['id'], message)


def _main(rest_url, rest_user, rest_pwd, auth_type):
    rest = gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()

    print(rest.list_account_emails())

    # rebase_change(rest, '184710')
    # merge_change(rest, '179723', '179166')
    # change_commit_msg(rest, 181483, 'hello world')
    print rest.get_file_content('env-config.d/ENV', '201443')


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
