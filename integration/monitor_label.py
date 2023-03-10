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
import ruamel.yaml as yaml
from mod import integration_change as inte_change

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
    parser.add_argument('comp_config', type=str,
                        help='')
    args = parser.parse_args()
    return vars(args)


def _if_checklist_all_pass(checklist, skytrack_log_collector, comp_config):
    print('\nCheck if all changes are passed...')
    for item in checklist:
        if not item['status'] and item['attached']:
            if not if_check_verified(item['comp_name'], comp_config):
                continue
            if not item['verified']:
                skytrack_log_collector.append("{0} change {1} haven't got verified label".format(
                    item['comp_name'],
                    item['ticket']
                ))
            else:
                if item['external']:
                    skytrack_log_collector.append("{0} change {1} haven't got Code-review +1/2".format(
                        item['comp_name'],
                        item['ticket']
                    ))
                else:
                    skytrack_log_collector.append("{0} change {1} haven't got Code-review +2".format(
                        item['comp_name'],
                        item['ticket']
                    ))
            print('Change {} does not meet the requirement.'.format(item['ticket']))
    return True if not skytrack_log_collector else False


def _check_ticket_ok(ssh_server, ssh_port, ssh_user, ssh_key, ticket, project):
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
        elif project == 'MN/SCMTA/zuul/inte_ric' and api.gerrit_api.does_patch_set_match_condition(
                ssh_user, ssh_server, ticket,
                ['label:Verified=+1', 'label:Integrated=0',
                 'label:Code-Review=+1'],
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


def get_ticket_list_from_comments(info):
    json_re = re.compile(r'Tickets-List: ({.*})')
    for item in reversed(info['comments']):
        result_list = json_re.findall(item['message'])
        if len(result_list) > 0:
            return json.loads(result_list[0])
    return None


def update_depends_list(rest, change):
    commit = rest.get_commit(change)
    message = commit.get('message')
    m_list = message.split('\n')
    d_list = []
    depends_list = []
    for line in m_list:
        if 'Depends-on: ' in line:
            d_list.append(line.split('Depends-on: ')[1].strip())
    for did in d_list:
        info = rest.get_change(did, using_cache=True)
        depends_list.append(info['_number'])
    return depends_list


def _check_if_external(rest, ticket_id):
    if_external = False
    result = rest.get_ticket(ticket_id)
    project = result['project']
    if project == 'MN/SCMTA/zuul/inte_ric':
        if_external = True
    return if_external


def check_interface(rest, tickets_dict, skytrack_log):
    ticket_interface = dict()
    interface_ci = dict()
    interface = ['cpnbcm', 'cpnrtcm', 'cprtcm', 'internal']
    has_interface = False
    for ticket in tickets_dict['tickets']:
        sc = rest.get_ticket(ticket)['project'].split('/')[-1]
        if sc in interface:
            has_interface = True
            commit_hash = rest.get_commit(ticket)['commit']
            parent_ci = rest.get_commit(ticket)['parents'][0]['commit']
            ticket_info = rest.get_ticket(ticket)
            project = ticket_info['project']
            if sc == 'internal':
                interface_ci['interfaces'] = commit_hash
            else:
                interface_ci[sc] = commit_hash
            branch = ticket_info['branch']
            head_hash = rest.get_latest_commit_from_branch(project, branch)['revision']
            if head_hash != parent_ci:
                skytrack_log.append(str(ticket) + "'s parent commit is out of date!")
                skytrack_log.append('head_hash:{} != parent_hash:{}'.format(head_hash, parent_ci))
                return False
        else:
            ticket_interface_ci = dict()
            start = False
            comp_name = None
            complete = True
            for line in rest.get_commit(ticket)['message'].split('\n'):
                if start:
                    if comp_name:
                        if 'commit-ID:' in line:
                            ticket_interface_ci[comp_name] = line.split(':')[-1].strip()
                            comp_name = None
                            complete = True
                    else:
                        if 'comp_name' in line:
                            comp_name = re.split('[:-]', line)[-1].strip()
                            complete = False
                else:
                    if line == 'interface info:':
                        start = True
            if start:
                if not complete:
                    skytrack_log.append(str(ticket) + "'s interface info is incomplete!")
                    return False
                elif ticket_interface_ci:
                    ticket_interface[ticket] = ticket_interface_ci
    print(ticket_interface)
    if has_interface:
        for ticket in ticket_interface:
            if set(ticket_interface[ticket].keys()) ^ set(interface_ci.keys()):
                skytrack_log.append(str(ticket) + "'s interface info error!")
                skytrack_log.append(set(ticket_interface[ticket].keys()) ^ set(interface_ci.keys()))
                return False
            else:
                for item in ticket_interface[ticket]:
                    if ticket_interface[ticket][item] != interface_ci[item]:
                        skytrack_log.append(str(ticket) + "'s interface version mismatch!")
                        skytrack_log.append("{} {}'s version:{}".format(ticket, item, ticket_interface[ticket][item]))
                        skytrack_log.append("{}'s true version:{}".format(item, interface_ci[item]))
                        return False
    return True


def if_check_verified(change_name, comp_config):
    comp_config = yaml.load(open(comp_config), Loader=yaml.Loader, version='1.1')
    for comps_list in comp_config['components'].values():
        for comps in comps_list:
            if change_name == comps['name'] and 'check_verified' in comps and not comps['check_verified']:
                return False
    return True


def _main(ssh_server, ssh_port, ssh_user, ssh_key, change_id,
          rest_url, rest_user, rest_pwd, auth_type, comp_config):
    rest = api.gerrit_rest.GerritRestClient(rest_url, rest_user, rest_pwd)
    if auth_type == 'basic':
        rest.change_to_basic_auth()
    elif auth_type == 'digest':
        rest.change_to_digest_auth()
    rest.init_cache()
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
                'attached': True,
                'need_backup': False,
                'external': False,
                'comp_name': '',
            }
        )
    print('Starting check if all tickets are done...')
    skytrack_log_collector = []
    try:
        # update depends list
        depends_list = targets['tickets']
        for item in pass_list:
            change_obj = inte_change.IntegrationChange(rest, item['ticket'])
            comp_name = change_obj.get_change_name()
            item['comp_name'] = comp_name
            if not if_check_verified(item['comp_name'], comp_config):
                print('\nSkip check verified label for {} change {}'.format(item['comp_name'], item['ticket']))
                continue
            print('\nCheck status of [{}]:'.format(item['ticket']))
            # update attached:
            try:
                if item['ticket'] not in depends_list:
                    item['attached'] = False
                    print('Change {} is a detatched change.'.format(item['ticket']))
                else:
                    item['attached'] = True
            except Exception as e:
                print('Check Attached status failed.')
                print('Because [{}]'.format(e))
                traceback.print_exc()
            # update verified
            verified_new = _check_ticket_checked(
                ssh_server, ssh_port, ssh_user, ssh_key, item['ticket'])
            print('Verified is {}'.format(verified_new))
            if verified_new != item['verified']:
                print('Change {} verified status changed!'.format(
                    item['ticket']))
            # check if external component
            item['external'] = _check_if_external(rest, item['ticket'])
            if item['external']:
                item['need_backup'] = False
                print('Ticket {} is external component, no need to backup'.format(item['ticket']))
            # update status
            item['verified'] = verified_new
            ticket_result = rest.get_ticket(item['ticket'])
            ticket_project = ticket_result['project']
            item['status'] = _check_ticket_ok(ssh_server, ssh_port,
                                              ssh_user,
                                              ssh_key, item['ticket'], ticket_project)
            print('Ticket {} pass status: {}'.format(
                item['ticket'], item['status']))
    except Exception as ex:
        print('check changes met an exception [{}]'.format(str(ex)))
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    check_result = True
    if _if_checklist_all_pass(pass_list, skytrack_log_collector, comp_config) and check_interface(rest, targets, skytrack_log_collector):
        print('All component changes match the verified+1 and code review+1/+2 requirement.')
        skytrack_log_collector.append('Validation succeed! Ready to merge to production now.')
    else:
        print('please check the tickets listed above, make sure the requirement achieved, then retry')
        check_result = False
    if len(skytrack_log_collector) > 0:
        print('integration framework web output start')
        for log in skytrack_log_collector:
            print(log)
        print('integration framework web output end')
    if not check_result:
        sys.exit(213)


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
