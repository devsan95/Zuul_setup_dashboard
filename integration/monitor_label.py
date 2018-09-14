#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import argparse
import json
import re
import sys
import time
import traceback

import urllib3

import api.gerrit_api
import api.gerrit_rest
import gerrit_int_op

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class FatalException(Exception):
    pass


def _parse_args():
    parser = argparse.ArgumentParser(description='Monitor ticket status')
    parser.add_argument('ssh_server', type=str,
                        help='server url of gerrit')
    parser.add_argument('ssh_port', type=str,
                        help='server port of gerrit')
    parser.add_argument('ssh_user', type=str,
                        help='user of gerrit')
    parser.add_argument('ssh_key', type=str,
                        help='private key of the user')
    parser.add_argument('change_id', type=str,
                        help='change id')
    parser.add_argument('rest_url', type=str,
                        help='')
    parser.add_argument('rest_user', type=str,
                        help='')
    parser.add_argument('rest_pwd', type=str,
                        help='')
    parser.add_argument('auth_type', type=str, default='digest',
                        help='')
    parser.add_argument('--backup-topic', type=str, dest='backup_topic',
                        default=None, help='')
    args = parser.parse_args()
    return vars(args)


def _if_checklist_all_pass(checklist):
    for item in checklist:
        if not item['status'] and item['attached']:
            print('Change {} does not meet the requirement.'.format(item['ticket']))
            return False
    return True


def _check_ticket_ok(ssh_server, ssh_port, ssh_user, ssh_key, ticket):
    try:
        if api.gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, ticket,
                ['label:Verified=+1', 'label:Integrated=+2',
                 'label:Code-Review=+2'],
                ssh_key, port=ssh_port):
            return True
        elif api.gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, ticket,
                ['label:Verified=+1', 'label:Integrated=0',
                 'label:Code-Review=+2'],
                ssh_key, port=ssh_port):
            return True
    except Exception as ex:
        print('check ticket ok met a exception [{}]'.format(str(ex)))
    return False


def _check_ticket_checked(ssh_server, ssh_port, ssh_user, ssh_key, ticket):
    try:
        if api.gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, ticket,
                ['label:Verified=+1'],
                ssh_key, port=ssh_port):
            return True
    except Exception as ex:
        print('check ticket checked met a exception [{}]'.format(str(ex)))
    return False


def _check_manager_ticket_ok(ssh_server, ssh_port, ssh_user, ssh_key, ticket):
    result = False
    try:
        if api.gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, ticket, ['label:Integrated=-2'],
                ssh_key, port=ssh_port):
            raise FatalException(
                'Manager ticket [{}] integration failed'.format(ticket))
        result = api.gerrit_api.does_patch_set_match_condition(
            ssh_user, ssh_server, ticket,
            ['label:Verified=+1', 'label:Integrated=+2'],
            ssh_key, port=ssh_port)
    except FatalException as fe:
        raise fe
    except Exception as ex:
        print('check manager ticket ok met a execption [{}]'.format(str(ex)))
    return result


def get_ticket_list_from_comments(info):
    json_re = re.compile(r'Tickets-List: ({.*})')
    for item in reversed(info['comments']):
        result_list = json_re.findall(item['message'])
        if len(result_list) > 0:
            return json.loads(result_list[0])
    return None


def _main(ssh_server, ssh_port, ssh_user, ssh_key, change_id,
          rest_url, rest_user, rest_pwd, auth_type, backup_topic):
    rest = api.gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()
    gop = gerrit_int_op.IntegrationGerritOperation(rest)
    if not backup_topic:
        name, branch, repo, platform = gop.get_info_from_change(change_id)
        if platform:
            backup_topic = 'integration_{}_backup'.format(platform)
    targets = None
    while not targets:
        try:
            info = api.gerrit_api.get_ticket_info(ssh_user, ssh_server,
                                                  change_id, ssh_key,
                                                  port=ssh_port)
            targets = get_ticket_list_from_comments(info)
            sys.stdout.flush()
            sys.stderr.flush()
            time.sleep(30)
        except Exception as ex:
            print(str(ex))

    pass_list = []
    for item in targets['tickets']:
        pass_list.append(
            {
                'ticket': item,
                'status': False,
                'verified': False,
                'attached': True
            }
        )
    print('Starting check if all tickets are done...')
    while not _if_checklist_all_pass(pass_list):
        print('Starting a new checking cycle...')
        try:
            for item in pass_list:
                # update attached:
                commit = rest.get_commit(item['ticket'])
                message = commit.get('message')
                message = message.replace('\n', ' ')
                if 'This change is an isolated change in this integration.' in message:
                    item['attached'] = False
                    print('Change {} is a detatched change.'.format(item['ticket']))
                else:
                    item['attached'] = True
                # update verified
                verified_new = _check_ticket_checked(
                    ssh_server, ssh_port, ssh_user, ssh_key, item['ticket'])
                if verified_new != item['verified']:
                    print('Change {} verified status changed!'.format(
                        item['ticket']))
                    if verified_new:
                        print('Change {} verified became True'.format(
                            item['ticket']))
                        if backup_topic and verified_new:
                            print('Ticket {} OK, begin to backup to topic {}'.format(
                                item['ticket'], backup_topic))
                            name, branch, repo, platform = gop.get_info_from_change(
                                item['ticket'])
                            backup_id = gop.get_ticket_from_topic(backup_topic, repo,
                                                                  branch, name)
                            if not backup_id:
                                backup_id = gop.create_change_by_topic(
                                    backup_topic, repo, branch, name)

                            if not backup_id:
                                print('Can not create or find change for '
                                      '{} {} {}'.format(backup_topic, branch, name))
                            else:
                                try:
                                    gop.clear_change(backup_id)
                                    gop.copy_change(item['ticket'], backup_id, True)
                                except Exception as ex:
                                    print('Can not copy {} to {}'.format(
                                        item['ticket'], backup_id))
                                    print('Because {}'.format(str(ex)))
                # update status
                item['verified'] = verified_new
                item['status'] = _check_ticket_ok(ssh_server, ssh_port,
                                                  ssh_user,
                                                  ssh_key, item['ticket'])
                print('Ticket {} pass status: {}'.format(
                    item['ticket'], item['status']))
        except Exception as ex:
            print('check changes met an exception [{}]'.format(str(ex)))
        sys.stdout.flush()
        sys.stderr.flush()
        if _if_checklist_all_pass(pass_list):
            break
        time.sleep(30)

    print('All ticket are done. Labeling manager ticket...')
    retry_time = 10
    while retry_time > 0:
        try:
            api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['manager'],
                                            ['Verified=+1', 'Integrated=-1'],
                                            'Set labels for integration', ssh_key,
                                            port=ssh_port)
            api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['manager'],
                                            [], 'reintegrate', ssh_key, port=ssh_port)
            break
        except Exception as ex:
            print('Labeling met an execption [{}]'.format(str(ex)))
            retry_time -= 1
            time.sleep(10)
    print('Check if manager ticket is done with integration...')
    while not _check_manager_ticket_ok(
            ssh_server, ssh_port, ssh_user, ssh_key, targets['manager']):
        sys.stdout.flush()
        sys.stderr.flush()
        time.sleep(30)
    print('Integration test done, make root and manager ticket into gating...')
    # api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['manager'],
    #                                 ['Code-Review=+2'], None,
    #                                 ssh_key, port=ssh_port)
    # api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['root'],
    #                                 ['Verified=+1', 'Integrated=+2',
    #                                  'Code-Review=+2'], None,
    #                                 ssh_key, port=ssh_port)
    retry_time = 10
    while retry_time > 0:
        try:
            api.gerrit_api.review_patch_set(ssh_user, ssh_server, targets['root'],
                                            ['Verified=+1', 'Integrated=+2'], None,
                                            ssh_key, port=ssh_port)

            if auth_type == 'basic':
                rest.change_to_basic_auth()
            elif auth_type == 'digest':
                rest.change_to_digest_auth()

            rest_id = rest.get_ticket(targets['manager'])['id']
            rest.review_ticket(rest_id, 'Make into gate', {'Code-Review': 2})
            break
            # rest_id = rest.get_ticket(targets['root'])['id']
            # rest.review_ticket(rest_id, 'Make into gate', {'Code-Review': 2})
        except Exception as ex:
            print('Labeling met an execption [{}]'.format(str(ex)))
            retry_time -= 1
            time.sleep(10)


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
