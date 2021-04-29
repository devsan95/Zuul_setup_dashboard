#! /usr/bin/env python
import argparse
import json
import os
import re
import sys
from api import config
from api import log_api
from api import gerrit_rest
from mod.wft_actions import BuildIncrement, WFTUtils
from mod.integration_change import RootChange, IntegrationChange
from mod import mailGenerator
from switch_with_rebase import get_mail_list

CONF = config.ConfigTool()
CONF.load('mail')

log = log_api.get_console_logger("update_ecl_sack_base")


def send_mail(rest, root_change, status, ecl_sack_base=None):
    op = RootChange(rest, root_change)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    mail_list = get_mail_list(comp_change_list, int_change, root_change, rest)
    int_change_obj = IntegrationChange(rest, int_change)
    topic = '{} of {}'.format(int_change_obj.get_version(),
                              int_change_obj.get_title())
    jira_id = int_change_obj.get_jira_id()
    topic_url = "https://skytrack.dynamic.nsn-net.net/showCompsDetail?issueKey={}".format(jira_id)
    topic_link = '<a href={}>{}</a>'.format(topic_url, topic_url)
    mail_params = {'topic': topic, 'topic_link': topic_link}
    dt = CONF.get_dict('integration_increment_ecl_sack_base')
    dt.update(mail_params)

    increment_result = []
    if status == "success" and ecl_sack_base:
        ecl_sack_base_url = "https://wft.int.net.nokia.com/Common/ECL_SACK_BASE/builds/{}".format(ecl_sack_base)
        print('New ECL SACK BASE created: {}'.format(ecl_sack_base_url))
        ecl_sack_base_link = '<a href={}>{}</a>'.format(ecl_sack_base_url, ecl_sack_base)
        increment_result.append(('New ECL SACK BASE created: ', '{}'.format(ecl_sack_base_link)))
    elif status == "fail":
        print('New ECL SACK BASE increment failed!')
        build_url = os.environ.get('BUILD_URL')
        console_link = '<a href={}>{}</a>'.format(build_url, build_url)
        increment_result.append(('[red]New ECL SACK BASE increment failed! Console log: ', '{}'.format(console_link)))

    dt['increment_result'] = increment_result
    dt['receiver'] = ';'.join(set(mail_list))
    print('Send email to {}'.format(mail_list))
    mail_generator = mailGenerator.MailGenerator(
        'integration_increment_ecl_sack_base',
        dt,
        dt['import_tools'].split(','))
    mail_generator.generate()


def arguments():
    parse = argparse.ArgumentParser()
    parse.add_argument('--gerrit_yaml', '-g', required=True, help="gerrit_yaml")
    parse.add_argument('--root_change', required=True, help="root change of integration topic")
    parse.add_argument('--ecl_branch', required=True, help="ecl branch in WFT")
    parse.add_argument('--changed_content', required=True, help="content change in sub builds")
    parse.add_argument('--base_branch', required=False, help="Base build branch in WFT")
    parse.add_argument('--base_load', required=False, help="Base build of increment")
    parse.add_argument('--PSINT_cycle', required=False, help="cycle for PS integration")
    return parse.parse_args()


def main():
    args = arguments()
    root_change = args.root_change
    rest = gerrit_rest.init_from_yaml(args.gerrit_yaml)
    changed = json.loads(args.changed_content)
    ecl_base_load = ''
    if args.base_load and args.base_branch and args.ecl_branch:
        cb_incrementer = BuildIncrement(args.base_branch, base_build=args.base_load)
        cb_incrementer.run(args.PSINT_cycle)
        ecl_base_load = WFTUtils.get_build_detail(args.base_load)['ecl_sack_base']

    ecl_incrementer = BuildIncrement(args.ecl_branch, changed, ecl_base_load)
    try:
        if not re.match(r'\d{6}$', args.PSINT_cycle.strip()):
            new_ecl_sack_base = ecl_incrementer.run()
        else:
            new_ecl_sack_base = ecl_incrementer.run(int(args.PSINT_cycle) + 1)
        send_mail(rest, root_change, status="success", ecl_sack_base=new_ecl_sack_base)
    except Exception as e:
        print('Increment ECL_SACK_BASE in WFT failed, reason:')
        print(str(e))
        send_mail(rest, root_change, status="fail")
        sys.exit(2)


if __name__ == "__main__":
    main()
