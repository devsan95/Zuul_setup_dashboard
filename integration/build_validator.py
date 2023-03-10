import os
import sys
import json
import traceback
import fire
import yaml
import git
import re

import update_oam_commit
import generate_bb_json
from mod import get_component_info
from api import gerrit_rest
from api import skytrack_log
from mod import wft_tools
from mod import integration_change
from mod import env_changes


def get_base_parent(base_obj_list, comp, project_name):
    base_parent = list()
    find_none = False
    for base_obj in base_obj_list:
        comp_hash = ''
        if comp == 'integration':
            base_repo_info = wft_tools.get_repository_info(base_obj.base_pkg)
            comp_hash = base_repo_info['revision']
        else:
            comp_hash = base_obj.get_comp_hash(comp)
        if comp_hash:
            if '=' in comp_hash:
                comp_hash = comp_hash.split('=')[1]
            if not re.match('[0-9a-f]{5,40}', comp_hash):
                repo_url = 'ssh://gerrit.ext.net.nokia.com:29418/{}'.format(project_name)
                g = git.cmd.Git()
                tag_hash = g.ls_remote("--tags", repo_url, comp_hash)
                comp_hash = tag_hash.split('\t')[0]
            base_parent.append(comp_hash)
        if comp_hash is None:
            find_none = True
    print("{}'s base parent hash: {}".format(comp, base_parent))
    if not base_parent and find_none:
        return None
    return base_parent


def fixed_base_validator(rest, components, base_dict):
    messages = ['Integration working on fixed base mode']
    print(messages[0])
    if not base_dict:
        print('No base package is identied, not able to validator fixed base')
        messages.append('No base package is identied, not able to validator fixed base')
        return messages
    print('Start to check components parents')
    base_obj_list = list()
    base_list = list()
    for base in base_dict:
        base_obj = None
        try:
            base_obj = get_component_info.GET_COMPONENT_INFO(base_dict[base])
            base_obj_list.append(base_obj)
        except Exception:
            print("get {} base object failed".format(base_dict[base]))
        base_list.append(base_dict[base])
    repo_dict = dict()
    parent_hash_mismatch = list()
    error_info = "Parent commit in change {} of {} is {}, the version in base build is {}"
    mismatch_dict = {}
    match_change_list = []
    for component in components:
        parent = rest.get_parent(component[2])
        print('mismatch_dict: {}'.format(mismatch_dict))
        print('match_change_list: {}'.format(match_change_list))
        if component[2] in match_change_list:
            continue
        if component[3] == 'component' and base_obj_list:
            base_parent_list = get_base_parent(base_obj_list, component[0], component[1])
            if base_parent_list is None:
                print("change {}[{}] not in base packages {}".format(component[2], component[0], base_list))
                continue
            if parent not in base_parent_list:
                mismatch_dict[component[2]] = (component, parent, base_parent_list)
            else:
                match_change_list.append(component[2])
                print("remove change {} from parent_hash_mismatch".format(component[2]))
                if component[2] in mismatch_dict:
                    del mismatch_dict[component[2]]

        if component[1] not in repo_dict:
            repo_dict[component[1]] = dict()
        if parent not in repo_dict[component[1]]:
            repo_dict[component[1]][parent] = [component]
        else:
            repo_dict[component[1]][parent].append(component)
    for mismatch_component in mismatch_dict.values():
        parent_hash_mismatch.append(
            error_info.format(
                mismatch_component[0][2],
                mismatch_component[0][0],
                mismatch_component[1],
                ", ".join(mismatch_component[2])
            )
        )

    parent_mismatch = dict()
    for repo, parents in repo_dict.items():
        if len(parents) > 1 and repo != 'MN/SCMTA/zuul/inte_ric':
            parent_mismatch[repo] = repo_dict[repo]
    if parent_mismatch or parent_hash_mismatch:
        messages.append('Build Pre-check Failed')
    else:
        print('Components parents check passed')
    if parent_mismatch:
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
    if parent_hash_mismatch:
        messages.append("Integration build based on {}".format(",".join(base_list)))
        for mismatch_hash in parent_hash_mismatch:
            print(mismatch_hash)
            messages.append(mismatch_hash)
    if parent_mismatch or parent_hash_mismatch:
        messages.append('Please contact the "Uploader" in above changes to solve it')

    return messages


def head_mode_validator(rest, components, config_yaml_dict):
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
            if component[1] == 'MN/5G/COMMON/integration':
                env_changes.rebase_integration_change(rest, component[2])
            if not rest.get_change(component[2])['mergeable']:
                merge_conficts.append(component[2])
        if component[1] == 'MN/5G/COMMON/integration':
            env_changes.rebase_component_config_yaml(rest, component[2], config_yaml_dict)

    for component_un_mergeable in merge_conficts:
        if rest.get_change(component_un_mergeable)['mergeable']:
            merge_conficts.remove(component_un_mergeable)
    gerrit_url = 'https://gerrit.ext.net.nokia.com/gerrit/#/c/{change}/'
    if merge_conficts:
        messages.append('Build Pre-check Failed')
        messages.append('Below changes have merge conflicts need to be solved by developers')
    else:
        print('Components mergeable status check passed')
    for change in merge_conficts:
        messages.append(gerrit_url.format(change=change))
    return messages, closed


def get_component_change_info(ex_dict, component):
    for change_no, components in ex_dict.items():
        for component_name in components:
            if component == component_name:
                return 'https://gerrit.ext.net.nokia.com/gerrit/#/c/{change}/'.format(
                    change=change_no)
    return None


def get_build_content(knife_json_path, base_info_path, ex_dict, build_streams,
                      integration_mode, compare=True):
    with open(knife_json_path, 'r') as knife_json:
        build_info_dict = json.load(knife_json)
    with open(base_info_path, 'r') as base_info:
        base_build_dict = json.load(base_info)
    messages = ['Integration Build Will Be Based On Bellow Base Load:']
    for stream in build_streams:
        stream_name = wft_tools.get_stream_name(stream)
        last_success_build, last_success_build_date = \
            wft_tools.get_lasted_success_build(stream_name)
        if stream in base_build_dict:
            wft_name = wft_tools.get_wft_release_name(base_build_dict[stream])
            delivery_date = wft_tools.get_planed_delivery_date(wft_name)
            messages.append('Stream: {0} Base_build: {1} Release Date: {2}'.format(
                stream,
                base_build_dict[stream],
                delivery_date))
        else:
            base_load = last_success_build
            release_date = last_success_build_date
            if integration_mode == 'FIXED_BASE':
                base_load, release_date = wft_tools.get_latest_qt_passed_build(stream_name)
            messages.append('Stream: {0} Base_build: {1} Release Date: {2}'.format(stream,
                                                                                   base_load,
                                                                                   release_date))
    messages.append('Integration Build Content:')
    handled_component = list()
    if compare:
        print('Compare Function need to be done')
    for stream, content in build_info_dict.items():
        for component, component_content in content.items():
            if component in handled_component or not isinstance(component_content, dict):
                continue
            if 'repo_ver' in component_content and not component_content['repo_ver']:
                change_info = get_component_change_info(ex_dict, component)
                handled_component.append(component)
                if not change_info:
                    continue
                messages.append('{0} change: {1}'.format(component, change_info))
                continue
            message_temp = '{0}: '.format(component)
            for key, change in component_content.items():
                message_temp += ' {0}-->{1} '.format(key, change)
            handled_component.append(component)
            messages.append(message_temp)
    return messages


def get_build_information(change_id, gerrit_info_path, gitlab_info_path, output_path,
                          gnb_list_path, db_info_path, build_streams, integration_mode,
                          comp_config, compare=False):
    print('Update MZOAM commit info')
    update_oam_commit.run(
        zuul_changes='',
        zuul_ref='',
        zuul_url='',
        change_id=change_id,
        gerrit_info_path=gerrit_info_path,
        gitlab_info_path=gitlab_info_path,
        dry_run=False
    )
    generate_bb_json.run(
        zuul_url='',
        zuul_ref='',
        output_path=output_path,
        change_id=change_id,
        gerrit_info_path=gerrit_info_path,
        zuul_changes='',
        gnb_list_path=gnb_list_path,
        db_info_path=db_info_path,
        comp_config=comp_config,
        only_knife_json=True
    )
    knife_path = os.path.join(output_path, 'knife.json')
    base_path = os.path.join(output_path, 'base.json')
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    rest.init_cache(1000)
    description, rest_id = generate_bb_json.get_description(rest, change_id)
    knife_config = generate_bb_json.parse_config(rest, change_id)
    ric_dict, ex_dict, abandoned_changes, proj_dict = generate_bb_json.parse_ric_list(
        rest, description, zuul_url='', zuul_ref='', project_branch={}, config=knife_config)
    messages = get_build_content(knife_path, base_path, ex_dict, build_streams,
                                 integration_mode, compare=compare)
    return messages


def build_info_post(change_id, gerrit_info_path, gitlab_info_path, output_path,
                    db_info_path, build_streams, integration_mode, comp_config,
                    compare=False, closed_changes=None):
    message = list()
    if closed_changes:
        message.append("Build Pre-check Succeed")
        message.append("But below changes are closed, are you sure to continue?")
        for change in closed_changes:
            message.append('https://gerrit.ext.net.nokia.com/gerrit/#/c/{change}/'.format(
                change=change
            ))
    try:
        message.extend(get_build_information(
            change_id=change_id,
            gerrit_info_path=gerrit_info_path,
            gitlab_info_path=gitlab_info_path,
            output_path=output_path,
            gnb_list_path='',
            db_info_path=db_info_path,
            build_streams=build_streams,
            integration_mode=integration_mode,
            comp_config=comp_config,
            compare=compare
        ))
    except Exception:
        print('Failed to get build information')
        traceback.print_exc()
        message.extend(['WARNING: Fail to get build content',
                        'You can click confirm to continue',
                        'And also contact CB for help',
                        'Email: I_5G_CB_SCM@internal.nsn.com'])
    skytrack_log.skytrack_output(
        message
    )


def validator(gerrit_info_path, gitlab_info_path, change_no, output_path,
              db_info_path, comp_config, compare=False):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    inte_change = integration_change.ManageChange(rest, change_no)
    component_list = inte_change.get_all_components()
    print(component_list)
    config_yaml_dict = {}
    if comp_config:
        comp_config_dict = {}
        with open(comp_config, 'r') as fr:
            comp_config_dict = yaml.load(fr.read(), Loader=yaml.Loader)
        if 'config_yaml' in comp_config_dict:
            config_yaml_dict = comp_config_dict['config_yaml']
    if not integration_verification_check(rest, component_list):
        skytrack_log.skytrack_output("ERROR: Verified+1 missing for repository MN/5G/COMMON/integration")
        sys.exit(213)
    closed_dict = dict()
    if inte_change.get_with_without() == '<without-zuul-rebase>':
        integration_mode = 'FIXED_BASE'
        base_dict = generate_bb_json.parse_comments_base(change_no, rest, using_cache=False)
        build_streams = inte_change.get_build_streams(with_sbts=True)
        del_list = []
        for base_stream in base_dict:
            if base_stream not in build_streams:
                del_list.append(base_stream)
        for del_stream in del_list:
            print('stream {} do not need to be checked'.format(del_stream))
            del base_dict[del_stream]
        messages = fixed_base_validator(rest, component_list, base_dict)
    else:
        integration_mode = 'HEAD'
        messages, closed_dict = head_mode_validator(rest, component_list, config_yaml_dict)
    # TO DO: test if with_sbts=True
    build_streams = inte_change.get_build_streams(with_sbts=True)
    if not build_streams:
        messages.append('Build Pre-check Failed')
        messages.append('No integration streams configured')
        messages.append('You can add streams via: http://production-5g.cb.scm.nsn-rdnet.net/view/008_Integration/job/integration_framework.UPDATE_KNIFE_STREAM/')
    if len(messages) > 1:
        skytrack_log.skytrack_output(messages)
        sys.exit(213)
    print('Build Pre-check Succeed')
    build_info_post(
        change_id=change_no,
        gerrit_info_path=gerrit_info_path,
        gitlab_info_path=gitlab_info_path,
        output_path=output_path,
        db_info_path=db_info_path,
        build_streams=build_streams,
        integration_mode=integration_mode,
        closed_changes=closed_dict,
        comp_config=comp_config,
        compare=compare
    )


def integration_verification_check(rest, component_list):
    check_result = False
    for component in component_list:
        if component[0] == "integration":
            component_change = integration_change.ManageChange(rest, component[2])
            if component_change.get_label_status("Verified") == "approved":
                check_result = True
            break
    return check_result


@skytrack_log.skytrack_log
def build_trigger(gerrit_info_path, change_no):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    rest.review_ticket(change_no, 'reexperiment')
    rest.review_ticket(change_no, 'reintegrate')


if __name__ == '__main__':
    fire.Fire()
