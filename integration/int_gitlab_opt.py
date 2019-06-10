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
from mod import common_regex


CONF = config.ConfigTool()
CONF.load('repo')


def get_mr_from_comments(ticket, rest):
    mr_project = ''
    mr_title = ''
    mr_branch = ''
    mr_id = ''
    mr_re = re.compile(
        r'Patch Set .*\n.*\nMR created in (.*)\n.*title:(.*)\n.*branch:(.*)')
    mr_re_id = re.compile(
        r'Patch Set .*\n.*\nMR created in (.*)\n.*title:(.*)\n.*branch:(.*)\n.*mr_id:(.*)')
    mr_comments = ''
    change_obj = rest.get_detailed_ticket(ticket)
    for message in change_obj['messages']:
        if 'MR created in' in message['message']:
            mr_comments = message['message']
    if mr_comments:
        m = mr_re_id.match(mr_comments)
        if m:
            mr_project = m.group(1).strip()
            mr_title = m.group(2).strip()
            mr_branch = m.group(3).strip()
            mr_id = m.group(4).strip()
        else:
            m = mr_re.match(mr_comments)
            mr_project = m.group(1).strip()
            mr_title = m.group(2).strip()
            mr_branch = m.group(3).strip()
    return mr_project, mr_title, mr_branch, mr_id


def get_int_info(ticket, rest_obj):
    """
    get integration info from ticket
    """
    regex_dict = {
        'version_name': common_regex.int_firstline_reg,
        'fifi': re.compile(r'(%FIFI=.*)$'),
        'comp': re.compile(r'\s+- COMP <(\S+)>'),
        'title_comp': re.compile(r'<(.*)> on .*'),
        'base_commit': re.compile(r'base_commit:(.*)')
    }
    match_dict = {}
    commit_msg = get_int_msg(ticket, rest_obj)
    for key, regex_obj in regex_dict.items():
        m_list = regex_obj.findall(commit_msg)
        if len(m_list) > 0:
            match_dict[key] = m_list[0]
    mr_title = ticket
    if 'fifi' in match_dict:
        mr_title = '{}_{}'.format(
            mr_title,
            match_dict['fifi'])
    elif 'version_name' in match_dict:
        mr_title = '{}_%FIFI={}'.format(
            mr_title,
            match_dict['version_name'][1])
    mr_comp = ''
    if 'comp' in match_dict:
        mr_comp = match_dict['comp']
    if not mr_comp:
        mr_comp = match_dict['title_comp']
    base_commit = match_dict['base_commit'] if 'base_commit' in match_dict else ''
    return mr_title, mr_comp, base_commit


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
    mr_title, mr_comp, base_commit = get_int_info(ticket, rest_obj)
    mr_project_comm, mr_title_comm, mr_branch_comm, mr_id_comm = get_mr_from_comments(
        ticket, rest_obj)
    if mr_title_comm:
        mr_title = mr_title_comm
    mr_id = ''
    if mr_id_comm:
        mr_id = mr_id_comm
    comp_branch, comp_repo_srv, project = get_branch_and_srv(mr_comp, branch)
    new_branch = 'int_{}'.format(mr_title)
    parameters = {
        'title': mr_title,
        'project': project,
        'ref': base_commit if base_commit else comp_branch,
        'target_branch': comp_branch,
        'branch': new_branch,
        'mr_id': mr_id}
    gitlab_obj = gitlab_tools.Gitlab_Tools(path=conf_path, repo=comp_repo_srv)
    print('Info: set project {}'.format(project))
    print('Info: parameters {}'.format(parameters))
    gitlab_obj.gitlab_client.set_project(project)
    if hasattr(gitlab_obj, action):
        print('Info: start action {}'.format(action))
        mr_id = getattr(gitlab_obj, action)(parameters)
        if not mr_title_comm and action == 'create_mr':
            rest_obj.review_ticket(
                ticket,
                'MR created in {}/{}\n title:{}\n branch:{}\n mr_id:{}\n'.format(
                    comp_repo_srv,
                    project,
                    mr_title,
                    new_branch,
                    mr_id))
    else:
        print('Error action:{} is not supported yet'.format(action))
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
