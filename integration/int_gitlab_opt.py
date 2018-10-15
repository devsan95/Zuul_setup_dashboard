'''
this is a scripts to create/update manager changes
it is based on a topic name
topic change will attached a change with real modfication
after topic finished, topic change also be merged
topic_change -> pci_change_mgr(repo)
real_chagne -> meta-5g-poc(repo)
functions:
    renew() -> update or create change for <issue_name>
    release() -> merge topoic change for <issue_name>
'''

import re
import sys
import argparse
import traceback
from api import config
from api import gerrit_rest
from mod import gitlab_tools


CONF = config.ConfigTool()
CONF.load('repo')


def get_int_info(ticket, rest_obj):
    """
    get integration info from ticket
    """
    regex_dict = {
        'fifi': r'%FIFI=(.*)$',
        'comp': r'\s+- COMP <(\S+)>'}
    match_dict = {}
    for key, regex_str in regex_dict.items():
        commit_msg = get_int_msg(ticket, rest_obj)
        for line in commit_msg.splitlines():
            m = re.match(regex_str, line)
            if m:
                match_dict[key] = m.group(1)
    mr_title = ticket
    if 'fifi' in match_dict:
        mr_title = '{}_{}'.format(
            mr_title,
            match_dict['fifi'])
    mr_comp = ''
    if 'comp' in match_dict:
        mr_comp = match_dict['comp']
    return mr_title, mr_comp


def get_int_msg(ticket, rest_obj):
    commit = rest_obj.get_commit(ticket)
    if commit and 'message' in commit:
        return commit['message']
    return ''


def get_branch_and_srv(comp, ref):
    brch_dict = CONF.get_dict(comp)
    print('Repo Branch Dict: {}'.format(brch_dict))
    int_brch = 'int_{}'.format(ref).lower()
    print('Int Branch: {}'.format(int_brch))
    if brch_dict and int_brch in brch_dict:
        return brch_dict[int_brch], brch_dict[
            'repo_server'], brch_dict['repo_project']
    print('Error: No {} info in repo config'.format(comp))
    sys.exit(2)


def _main(ticket, conf_path, action, branch):
    rest_obj = gerrit_rest.init_from_yaml(
        conf_path.replace('/ext_gitlab',
                          '/ext_gerrit'))
    mr_title, mr_comp = get_int_info(ticket, rest_obj)
    comp_branch, comp_repo_srv, project = get_branch_and_srv(mr_comp, branch)
    new_branch = 'int_{}'.format(mr_title)
    params = {
        'title': mr_title,
        'project': project,
        'ref': comp_branch,
        'branch': new_branch}
    gitlab_obj = gitlab_tools.Gitlab_Tools(path=conf_path, repo=comp_repo_srv)
    print('Info: set project {}'.format(project))
    gitlab_obj.gitlab_client.set_project(project)
    if hasattr(gitlab_obj, action):
        print('Info: start action {}'.format(action))
        getattr(gitlab_obj, action)(params)
        rest_obj.review_ticket(
            ticket,
            'MR created in {}/{}\n title:{}\n branch:{}\n'.format(
                comp_repo_srv,
                project,
                mr_title,
                new_branch))
    else:
        print('Error action:{} is not supported yet'.format(params['action']))
        sys.exit(2)


def _parse_args():
    parser = argparse.ArgumentParser(
        description="this is the help usage of %(prog)s",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        "--ticket",
        required=True,
        help="gerrit ticket number",
        dest="ticket")

    parser.add_argument(
        "--branch",
        required=True,
        help="gerrit ticket branch",
        dest="branch")

    parser.add_argument(
        "--config",
        required=True,
        help="config path for gitlab",
        dest="conf_path")

    parser.add_argument(
        "--action",
        required=True,
        help="action: create_mr/merge_mr",
        dest="action")

    args = parser.parse_args()
    return vars(args)


if __name__ == '__main__':
    try:
        params = _parse_args()
        _main(
            params['ticket'],
            params['conf_path'],
            params['action'],
            params['branch'])
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
