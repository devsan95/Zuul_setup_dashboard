import re

import fire
import git

from api import gerrit_rest

submodule_re = re.compile('  - SUBMODULEROOT <(.*)> <(.*)> <(.*)>')


def get_submodule_info(change_no, commit):
    commit_msg = commit['message']
    commit_lines = commit_msg.split('\n')
    for line_ in commit_lines:
        m = submodule_re.match(line_)
        if m:
            return m.group(1), m.group(2), m.group(3)
    else:
        return None, None, None


def run(change_no, gerrit_info_path, repo_path, test_run=False, test_change=None):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    change_info = rest.get_change(change_no)
    commit_info = rest.get_commit(change_no)
    proj, branch, path = get_submodule_info(change_no, commit_info)
    if not proj:
        print('No need to update')
        return
    # get change commit
    change_commit = commit_info['commit']
    if change_info['status'] != 'MERGED' and not test_run:
        raise Exception('Change {} is not merged'.format(change_no))
    # create change
    if not test_change:
        new_gerrit_change_id, new_change_id, new_rest_id = \
            rest.create_ticket(
                proj, None, branch,
                'Update env submodule caused by {}'.format(change_no), has_review_started=True)
    else:
        new_change_id = test_change
    # get current commit
    current_commit = rest.get_file_content(path, new_change_id)
    # compare if need to update
    gm = git.Git(repo_path)
    need_update = False
    try:
        print(gm.merge_base('--is-ancestor', current_commit, change_commit))
    except git.exc.GitCommandError as e:
        print(e)
        need_update = True

    if need_update:
        print('Going to update submodule')
        try:
            rest.delete_edit(new_change_id)
        except Exception as e:
            print(e)
        rest.add_file_to_change(new_change_id, path, change_commit)
        rest.publish_edit(new_change_id)
        if not test_run:
            rest.review_ticket(new_change_id, 'merge', {'Code-Review': 2})


if __name__ == '__main__':
    fire.Fire(run)
