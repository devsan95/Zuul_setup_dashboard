#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import traceback
import sys
import argparse
import json
import time
import api.gerrit_api
import re


def _parse_args():
    parser = argparse.ArgumentParser(description='Monitor ticket status')
    parser.add_argument('ssh_server', type=str,
                        help='server url of gerrit')
    parser.add_argument('ssh_user', type=str,
                        help='user of gerrit')
    parser.add_argument('ssh_key', type=str,
                        help='private key of the user')
    parser.add_argument('change_id', type=str,
                        help='private key of the user')
    args = parser.parse_args()
    return vars(args)


def _if_checklist_all_pass(checklist):
    for item in checklist:
        if not item['status']:
            return False
    return True


def _check_ticket_ok(ssh_server, ssh_user, ssh_key, ticket):
    return api.gerrit_api.does_patch_set_match_condition(
        ssh_user, ssh_server, ticket,
        ['Verified=+1', 'Integrated=+2', 'Code-Review=+2'],
        ssh_key)


def _check_manager_ticket_ok(ssh_server, ssh_user, ssh_key, ticket):
    if api.gerrit_api.does_patch_set_match_condition(
            ssh_user, ssh_server, ticket, ['Integrated=-2'], ssh_key):
        raise Exception(
            'Manager ticket [{}] integration failed'.format(ticket))
    return api.gerrit_api.does_patch_set_match_condition(
        ssh_user, ssh_server, ticket,
        ['Verified=+1', 'Integrated=+2'],
        ssh_key)


def get_ticket_list_from_comments(info):
    json_re = re.compile(r'Tickets-List: ({.*})')
    for item in reversed(info['comments']):
        result_list = json_re.findall(item['message'])
        if len(result_list) > 0:
            return json.loads(result_list[0])
    return None


def _main(ssh_server, ssh_user, ssh_key, change_id):
    targets = None
    while not targets:
        info = api.gerrit_api.get_ticket_info(ssh_user, ssh_server,
                                              change_id, ssh_key)
        targets = get_ticket_list_from_comments(info)
        sys.stdout.flush()
        time.sleep(30)

    checklist = []
    for item in targets['tickets']:
        checklist.append(
            {
                'ticket': item,
                'status': False
            }
        )
    print('Starting check if all tickets are done...')
    while not _if_checklist_all_pass(checklist):
        print('Starting a new checking cycle...')
        for item in checklist:
            if not item['status']:
                item['status'] = _check_ticket_ok(ssh_server, ssh_user,
                                                  ssh_key, item['ticket'])
                print('Ticket {} pass status: {}'.format(
                    item['ticket'], item['status']))
        sys.stdout.flush()
        if _if_checklist_all_pass(checklist):
            break
        time.sleep(30)

    print('All ticket are done. Labeling manager ticket...')
    api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['manager'],
                                    ['Verified=+1', 'Integrated=-1'],
                                    'Set labels for integration', ssh_key)
    api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['manager'],
                                    [], 'reintegrate', ssh_key)
    print('Check if manager ticket is done with integration...')
    while not _check_manager_ticket_ok(
            ssh_server, ssh_user, ssh_key, targets['manager']):
        sys.stdout.flush()
        time.sleep(30)
    print('Integration test done, make root and manager ticket into gating...')
    api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['manager'],
                                    ['Code-Review=+2'], None,
                                    ssh_key)
    api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['root'],
                                    ['Verified=+1', 'Integrated=+2',
                                     'Code-Review=+2'], None,
                                    ssh_key)


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
