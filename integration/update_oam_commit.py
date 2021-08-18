import re
import sys
import traceback

import fire

import api.gerrit_rest
import api.gitlab_api
from generate_bb_json import parse_ric_list, parse_zuul_changes, parse_config, get_description


def get_oam_int_commit(project, branch, gitlab_info_path):
    project_info = project.split('/', 1)
    repo = project_info[0]
    project_name = project_info[-1]
    gitlab_obj = api.gitlab_api.init_from_yaml(gitlab_info_path, repo)
    gitlab_obj.set_project(project_name)
    branch_info = gitlab_obj.project.branches.get(branch)
    commit = branch_info.commit['id']
    print('Last commit for {project} branch {branch}: {commit}'.format(project=project_name,
                                                                       branch=branch,
                                                                       commit=commit))
    return commit


def update_oam_comments(rest, component, oam_change, oam_commit, dry_run):
    message = 'update_bb:{COMPONENT},-,{REPO_VER}'.format(COMPONENT=component, REPO_VER=oam_commit)
    if dry_run:
        print("Dry Run Mode:")
        print("Fake comment {change_id}: {message}".format(change_id=oam_change,
                                                           message=message))
        return
    rest.review_ticket(oam_change, message)


def parse_oam_changes(rest, change_id, gitlab_info_path):
    ticket = rest.get_detailed_ticket(change_id)
    oam_re = re.compile(r'Patch Set .*\n.*\nMR created in (.*)\n.*title:(.*)\n.*branch:(.*)')
    commit_re = re.compile(r'Patch Set .*\n.*\nupdate_bb:.*,.*,(.*).*')
    oam_comments = ''
    last_auto_updated_commit = ''
    oam_frozen = False
    for message in ticket['messages']:
        if 'MR created in' in message['message']:
            oam_comments = message['message']
        commit_matched = commit_re.match(message['message'])
        if commit_matched:
            if message['author']['username'] != 'ca_5gint':
                oam_frozen = True
            else:
                last_auto_updated_commit = commit_matched.group(1)
        if 'use_default_commit' in message['message']:
            oam_frozen = False
    if oam_frozen:
        print ('OAM commit frozen, no need to auto fetch latest OAM commit')
        return None
    if oam_comments:
        print('Parsing oam int change: {}'.format(rest.get_change_address(change_id)))
        m = oam_re.match(oam_comments)
        if m:
            oam_project = m.group(1).strip()
            oam_branch = m.group(3).strip()
            oam_latest_commit = get_oam_int_commit(oam_project, oam_branch, gitlab_info_path)
            if oam_latest_commit == last_auto_updated_commit:
                print ('No need to comment, no update in {0}'.format(oam_project))
                return None
            return oam_latest_commit
    return None


def run(zuul_url, zuul_ref, change_id,
        gerrit_info_path, zuul_changes, gitlab_info_path, dry_run=True):
    rest = api.gerrit_rest.init_from_yaml(gerrit_info_path)
    rest.init_cache(1000)
    project_branch = parse_zuul_changes(zuul_changes)
    description, rest_id = get_description(rest, change_id)
    knife_config = parse_config(rest, change_id)
    ric_dict, ex_dict, abandoned_changes, proj_dict = parse_ric_list(
        rest, description, zuul_url, zuul_ref, project_branch,
        knife_config)
    for change in ex_dict:
        commit = parse_oam_changes(rest, change, gitlab_info_path)
        if commit:
            update_oam_comments(rest, ex_dict[change][0], change, commit, dry_run)


if __name__ == '__main__':
    try:
        fire.Fire(run)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
