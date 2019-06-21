import sys

import fire

from api import gerrit_rest
from api import skytrack_log
from mod import integration_change


def fixed_base_validator(rest, components):
    messages = ['Integration working on fixed base mode']
    print(messages[0])
    print('Start to check components parents')
    repo_dict = dict()
    for component in components:
        if component[1] not in repo_dict:
            repo_dict[component[1]] = dict()
        parent = rest.get_parent(component[2])
        if parent not in repo_dict[component[1]]:
            repo_dict[component[1]][parent] = [component]
        else:
            repo_dict[component[1]][parent].append(component)
    parent_mismatch = dict()
    for repo, parents in repo_dict.items():
        if len(parents) > 1:
            parent_mismatch[repo] = repo_dict[repo]
    if parent_mismatch:
        messages.append('Build Pre-check Failed')
        messages.append('Below changes should have same parent in fixed base mode:')
    for repo in parent_mismatch:
        messages.append('Project: {0}'.format(repo))
        for base in parent_mismatch[repo]:
            for component in parent_mismatch[repo][base]:
                messages.append('{component}: Gerrit change {change} Parent: {parent}'.format(
                    component=component[0],
                    change=component[2],
                    parent=base
                ))
    return messages


def head_mode_validator(rest, components):
    messages = ['Integration working on head mode']
    print(messages[0])
    print('Start to check components mergeable status')
    merge_conficts = list()
    closed = dict()
    for component in components:
        if component[2] in merge_conficts:
            continue
        change_info = rest.get_change(component[2])
        if change_info['status'] in ['ABANDONED', 'MERGED']:
            closed[component[2]] = change_info['status']
            continue
        if not rest.get_change(component[2])['mergeable']:
            merge_conficts.append(component[2])
    gerrit_url = 'https://gerrit.ext.net.nokia.com/gerrit/#/c/{change}/'
    if merge_conficts:
        messages.append('Build Pre-check Failed')
        messages.append('Below changes have merge conflicts need to be solved by developers')
    for change in merge_conficts:
        messages.append(gerrit_url.format(change=change))
    return messages, closed


def build_info_post(closed_changes):
    message = list()
    if closed_changes:
        message.append("Build Pre-check Succeed")
        message.append("But below changes are closed, are you sure to continue?")
        for change in closed_changes:
            message.append('https://gerrit.ext.net.nokia.com/gerrit/#/c/{change}/'.format(
                change=change
            ))
    skytrack_log.skytrack_output(
        [
            "Build Pre-check PASSED",
            "More information will be added in future",
            "You can click confirm button to continue"
        ]
    )


def validator(gerrit_info_path, change_no):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    inte_change = integration_change.ManageChange(rest, change_no)
    component_list = inte_change.get_all_components()
    messages = list()
    closed_dict = dict()
    if inte_change.get_with_without() == '<without-zuul-rebase>':
        messages = fixed_base_validator(rest, component_list)
    else:
        messages, closed_dict = head_mode_validator(rest, component_list)
    if not inte_change.get_build_streams():
        messages.append('Build Pre-check Failed')
        messages.append('No integration streams configured')
        messages.append('You can add streams via: http://wrlinb147.emea.nsn-net.net:9090/view/008_Integration/job/integration_framework.UPDATE_KNIFE_STREAM/')
    if len(messages) > 1:
        skytrack_log.skytrack_output(messages)
        sys.exit(1)
    print('Build Pre-check Succeed')
    build_info_post(closed_dict)


@skytrack_log.skytrack_log
def build_trigger(gerrit_info_path, change_no):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    rest.review_ticket(change_no, 'reexperiment')


if __name__ == '__main__':
    fire.Fire()
