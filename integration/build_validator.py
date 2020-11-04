import os
import sys
import json
import traceback
import fire

import update_oam_commit
import generate_bb_json
from mod import get_component_info
from api import gerrit_rest
from api import skytrack_log
from mod import wft_tools
from mod import integration_change


def get_base_parent(rest, base_obj_list, comp):
    base_parent = list()
    for base_obj in base_obj_list:
        comp_hash = ''
        if comp == 'integration':
            comp_hash = rest.get_tag('MN/5G/COMMON/integration', base_obj.base_pkg)['object']
        else:
            comp_hash = base_obj.get_comp_hash_from_mapping_file(comp)
        if comp_hash:
            if '=' in comp_hash:
                comp_hash = comp_hash.split('=')[1]
            base_parent.append(comp_hash)
    print("{}'s base parent hash: {}".format(comp, base_parent))
    return base_parent


def fixed_base_validator(rest, components, base_dict):
    messages = ['Integration working on fixed base mode']
    print(messages[0])
    print('Start to check components parents')
    base_obj_list = list()
    base_list = list()
    for base in base_dict:
        try:
            base_obj_list.append(get_component_info.GET_COMPONENT_INFO(base_dict[base]))
        except Exception:
            print("get {} base object failed".format(base_dict[base]))
        base_list.append(base_dict[base])
    repo_dict = dict()
    parent_hash_mismatch = list()
    error_info = "Parent commit in change {} of {} is {}, the version in base build is {}"
    for component in components:
        parent = rest.get_parent(component[2])
        if component[3] == 'component' or component[0] == 'integration' and base_obj_list:
            base_parent_list = get_base_parent(rest, base_obj_list, component[0])
            if parent not in base_parent_list:
                parent_hash_mismatch.append(
                    error_info.format(
                        component[2],
                        component[0],
                        parent,
                        ", ".join(base_parent_list)
                    )
                )
        if component[1] not in repo_dict:
            repo_dict[component[1]] = dict()
        if parent not in repo_dict[component[1]]:
            repo_dict[component[1]][parent] = [component]
        else:
            repo_dict[component[1]][parent].append(component)
    parent_mismatch = dict()
    for repo, parents in repo_dict.items():
        if len(parents) > 1:
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
        stream_name_prefix = last_success_build.split('_')[0]
        if stream in base_build_dict:
            delivery_date = wft_tools.get_planed_delivery_date('{0}_{1}'.format(
                stream_name_prefix,
                base_build_dict[stream]
            ))
            messages.append('Stream: {0} Base_build: {1} Release Date: {2}'
                            .format(stream,
                                    base_build_dict[stream],
                                    delivery_date))
        else:
            base_load, release_date = wft_tools.get_latest_qt_passed_build(
                stream_name
            ) if integration_mode == 'FIXED_BASE' \
                else last_success_build, last_success_build_date
            messages.append('Stream: {0} Base_build: {1} Release Date: {2}'.format(stream,
                                                                                   base_load,
                                                                                   release_date))
    messages.append('Integration Build Content:')
    handled_component = list()
    if compare:
        print('Compare Function need to be done')
    for stream, content in build_info_dict.items():
        for component, component_content in content.items():
            if component in handled_component:
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
                          gnb_list_path, db_info_path, build_streams, integration_mode, compare=False):
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
        db_info_path=db_info_path

    )
    knife_path = os.path.join(output_path, 'knife.json')
    base_path = os.path.join(output_path, 'base.json')
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    rest.init_cache(1000)
    description, rest_id = generate_bb_json.get_description(rest, change_id)
    knife_config = generate_bb_json.parse_config(rest, change_id)
    ric_dict, ex_dict, abandoned_changes = generate_bb_json.parse_ric_list(
        rest, description, zuul_url='', zuul_ref='', project_branch={}, config=knife_config)
    messages = get_build_content(knife_path, base_path, ex_dict, build_streams,
                                 integration_mode, compare=compare)
    return messages


def build_info_post(change_id, gerrit_info_path, gitlab_info_path, output_path,
                    db_info_path, build_streams, integration_mode, compare=False, closed_changes=None):
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
            compare=compare
        ))
    except Exception:
        print('Failed to get build information')
        traceback.print_exc()
        message.extend(['WARNING: Fail to get build content',
                        'You can click confirm to continue',
                        'And also contact CB for help',
                        'Email: 5g_cb.scm@nokia.com'])
    skytrack_log.skytrack_output(
        message
    )


def validator(gerrit_info_path, gitlab_info_path, change_no, output_path,
              db_info_path, compare=False):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    inte_change = integration_change.ManageChange(rest, change_no)
    component_list = inte_change.get_all_components()
    print(component_list)
    if not integration_verification_check(rest, component_list):
        skytrack_log.skytrack_output("ERROR: Verified+1 missing for repository MN/5G/COMMON/integration")
        sys.exit(1)
    closed_dict = dict()
    if inte_change.get_with_without() == '<without-zuul-rebase>':
        integration_mode = 'FIXED_BASE'
        base_dict = generate_bb_json.parse_comments_base(change_no, rest, using_cache=False)
        messages = fixed_base_validator(rest, component_list, base_dict)
    else:
        integration_mode = 'HEAD'
        messages, closed_dict = head_mode_validator(rest, component_list)
    build_streams = inte_change.get_build_streams()
    if not build_streams:
        messages.append('Build Pre-check Failed')
        messages.append('No integration streams configured')
        messages.append('You can add streams via: http://wrlinb147.emea.nsn-net.net:9090/view/008_Integration/job/integration_framework.UPDATE_KNIFE_STREAM/')
    if len(messages) > 1:
        skytrack_log.skytrack_output(messages)
        sys.exit(1)
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


if __name__ == '__main__':
    fire.Fire()
