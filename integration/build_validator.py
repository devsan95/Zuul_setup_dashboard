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
    for component in components:
        if component[2] in merge_conficts:
            continue
        if not rest.get_change(component[2])['mergeable']:
            merge_conficts.append(component[2])
    gerrit_url = 'https://gerrit.ext.net.nokia.com/gerrit/#/c/{change}/'
    if merge_conficts:
        messages.append('Build Pre-check Failed')
        messages.append('Below changes have merge conflicts need to be solved by developers')
    for change in merge_conficts:
        messages.append(gerrit_url.format(change=change))
    return messages


def build_info_post():
    pass


def run(gerrit_info_path, change_no):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    inte_change = integration_change.ManageChange(rest, change_no)
    component_list = inte_change.get_all_components()
    if inte_change.get_with_without() == '<without-zuul-rebase>':
        messages = fixed_base_validator(rest, component_list)
    else:
        messages = head_mode_validator(rest, component_list)
    if len(messages) > 1:
        skytrack_log.skytrack_output(messages)
        sys.exit(1)
    print('Build Pre-check Succeed')
    build_info_post()


if __name__ == '__main__':
    fire.Fire(run)
