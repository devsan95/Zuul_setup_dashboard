'''
This is an scripts to trigger integration process
automatically based on give bb file.
this bb file indicate an component
which is depended by other components.
there is two situation:
    1. integratoin process exists:
        - rebase interface
          (trigger rebase job)
    2. not exists:
        - create interation
          (trigger create job with interface param)
'''

import os
import re
import fire
import json
import urllib2
import ruamel.yaml as yaml

from api import job_tool
from api import gerrit_rest
from mod import utils


INTEGRTION_URL = 'ssh://gerrit.ext.net.nokia.com' \
                 ':29418/MN/5G/COMMON/integration'
INTEGRATION_LIST_REST = 'https://skytrack.dynamic.nsn-net.net/Feature' \
                        '/getIssueListContainsAllComponents'
INTEGRAION_TRIGGER_REST = 'https://testscirtem.int.net.nokia.com/Feature' \
                          '/getIssueList?page=1&status=open&hideTestTopic=true'
EXTERNAL_REPO = 'MN/SCMTA/zuul/inte_ric'
ROOT_FILE_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META_TEMPLATE = os.path.join(
    ROOT_FILE_FOLDER, 'CICONF/template/integration_meta.json')
MAIN_TEMPLATE = os.path.join(
    ROOT_FILE_FOLDER, 'CICONF/template/integration_main.json')
COMP_TEMPLATE = os.path.join(
    ROOT_FILE_FOLDER, 'CICONF/template/integration_component.json')
SRC_URI_REV_REGEX = r'SRC_URI\s*=\s*".*;rev=\$\{([^}]+)\}'
REV_REGEX = r'^(REVISION|SVNTAG|SVNREV|SRCREV)\s*=\s*"([^"]+)"'
ALTER_COMP_DICT = {'interfaces': 'interfaces-internal'}
INTERFACE_COMPONENTS = ['interfaces-cpnrtcm', 'interfaces-cpnbcm',
                        'interfaces-cprtcm', 'interfaces']


def generate_int_json(comp_name, branch, comp_config):
    component = get_comp_obj(comp_name, comp_config)
    ric_name = component['ric']
    if ric_name in ALTER_COMP_DICT:
        ric_name = ALTER_COMP_DICT[ric_name]
    comp_sets = comp_config['component_sets']
    print('ric_name: {}'.format(ric_name))
    print('component_sets: {}'.format(comp_sets))
    int_dict = {}
    with open(MAIN_TEMPLATE, 'r') as fr:
        main_list = json.loads(fr.read().replace(r'{{branch}}', branch))
        int_dict['structure'] = main_list
    with open(META_TEMPLATE, 'r') as fr:
        meta_content = fr.read().replace(r'{{branch}}', branch)
        int_dict['meta'] = json.loads(meta_content)
    if ric_name in comp_sets:
        for sub_comp in comp_sets[ric_name]:
            if sub_comp != comp_name and sub_comp != ric_name:
                print('Add {} info to yaml'.format(sub_comp))
                int_dict['structure'].append(
                    generate_comp_json(sub_comp, branch, comp_config))
    else:
        raise Exception('Cannot find {} in components sets'.format(ric_name))
    return json.dumps(int_dict)


def get_comp_obj(comp_name, comp_config):
    for component in comp_config['components']:
        if component['name'] == comp_name \
                or 'ric' in component \
                and component['ric'] == comp_name:
            return component
    raise Exception(
        'Cannot get info for {} from {}'.format(comp_name, comp_config))


def generate_comp_json(comp_name, branch, comp_config):
    repo = ''
    component = get_comp_obj(comp_name, comp_config)
    print('Get component: {}'.format(component))
    if 'repo' in component:
        repo = component['repo']
    else:
        repo = EXTERNAL_REPO
    with open(COMP_TEMPLATE, 'r') as fr:
        comp_content = fr.read().replace(r'{{repo}}', repo)
        comp_content = comp_content.replace(r'{{branch}}', branch)
        comp_content = comp_content.replace(r'{{comp_name}}', comp_name)
        comp_dict = json.loads(comp_content)
        if 'files' in component:
            comp_dict['files'] = [component['files']]
        if 'path' in component:
            comp_dict['paths'] = [component['path']]
        return comp_dict
    raise Exception(
        'Cannot get info for {} from {}'.format(comp_name, COMP_TEMPLATE))


def get_version_from_bb(bb_file):
    with open(bb_file, 'r') as fr:
        file_content = fr.read()
        revision_regex = REV_REGEX
        m_uri_rev = re.search(SRC_URI_REV_REGEX, file_content)
        if m_uri_rev:
            revision_regex = r'^({})\s*=\s*"([^"]+)"'.format(m_uri_rev.group(1))
        m_rev = re.search(revision_regex, file_content, re.MULTILINE)
        if m_rev:
            return m_rev.group(2)
        raise Exception('Cannot find revision in {}'.format(bb_file))
    raise Exception('Cannot open file {}'.format(bb_file))


def run(gerrit_info_path, component_yaml_path, meta_5g_path,
        meta_bb='', branch='', zuul_change='', zuul_branch=''):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    if zuul_change and zuul_branch:
        branch = zuul_branch
        meta_files = rest.get_file_list(zuul_change)
        for meta_file in meta_files:
            print('meta_file {}'.format(meta_file))
            meta_file = meta_file.split('\n', 2)[0]
            for interfaces_comp in INTERFACE_COMPONENTS:
                m = re.match(
                    r'.*[/]?{}_[a-zA-Z0-9\.\-_]+\.bb'.format(interfaces_comp), meta_file)
                if m:
                    meta_bb = os.path.basename(meta_file).split('.bb')[0]
                    print('meta_bb {}'.format(meta_bb))
                    break
    if meta_bb and branch:
        print('Trigger meta_bb: {} , branch: {}'.format(meta_bb, branch))
        trigger(meta_bb, branch, rest, component_yaml_path, meta_5g_path)
    else:
        if zuul_change:
            print('Meta or branch not found')
        else:
            raise Exception('Meta or Branch is not set')


def trigger(meta_bb, branch, rest,
            component_yaml_path, meta_5g_path):
    comp_config = {}
    with open(component_yaml_path, 'r') as fr:
        comp_config = yaml.load(fr.read(), Loader=yaml.Loader)
    bb_file_name = os.path.join('{}.bb'.format(meta_bb))
    bb_files = utils.find_files(meta_5g_path, bb_file_name)
    if len(bb_files) != 1:
        raise Exception('Find {} not one bb_file'.format(bb_files))
    bb_file = bb_files[0]
    comp_name = meta_bb.split('_', 1)[0]
    bb_ver = meta_bb.split('_', 1)[1]
    repo_ver = get_version_from_bb(bb_file)
    print('{} version: {}'.format(comp_name, repo_ver))
    change_objs = rest.query_ticket('commit:{}'.format(repo_ver))
    print('Inteface changes: {}'.format(change_objs))
    if len(change_objs) != 1:
        raise Exception('Get multi chagne for commit:{}'.format(repo_ver))
    change_obj = change_objs[0]
    interface_change = change_obj['_number']
    jr_regex = r'%JR=(\S+)'
    commit_msg = rest.get_commit(interface_change)['message']
    jira_id = ''
    m_jr = re.search(jr_regex, commit_msg)
    if m_jr:
        jira_id = m_jr.group(1)
    response = urllib2.urlopen(INTEGRATION_LIST_REST)
    integration_list = json.loads(response.read())['result']['integrationList']
    integration_match = ''
    int_change = ''
    root_change = ''
    subject = '{}-{} Integration'.format(branch, interface_change)
    print('Find subject: {}'.format(subject))
    for integration_obj in integration_list:
        if (jira_id and jira_id == integration_obj['issueKey']) \
                or integration_obj['subject'] == subject:
            integration_match = integration_obj
            print('Integration Obj: {}'.format(integration_obj))
            for comp_obj in integration_match['componentVOList']:
                if comp_obj['component'] == 'integration':
                    int_change = comp_obj['change']
                if comp_obj['component'] == 'root_monitor':
                    root_change = comp_obj['change']
            break
    print('Jira id: {}, int_change: {}'.format(jira_id, int_change))
    if not jira_id and int_change:
        print('Find Jira id from int int_change: {}'.format(int_change))
        int_commit_msg = rest.get_commit(int_change)['message']
        interface_change_status = rest.get_change(interface_change)['status']
        m_jr = re.search(jr_regex, int_commit_msg)
        if m_jr and interface_change_status == 'NEW':
            print('Find Jira id: {} int int_change'.format(m_jr.group(0)))
            commit_msg += '\n{}'.format(m_jr.group(0))
            try:
                rest.delete_edit(interface_change)
            except Exception as e:
                print(e)
            rest.change_commit_msg_to_edit(interface_change, commit_msg)
            rest.publish_edit(interface_change)
    if not integration_match:
        params_int = {}
        params_int['jira_key'] = interface_change
        params_int['gerrit_info'] = 'ext_gerrit.yaml'
        params_int['yaml'] = generate_int_json(comp_name, branch, comp_config)
        params_int['interface_version'] = meta_bb
        print('create_integration: {},{}'.format(comp_name, bb_ver))
        job_tool.write_dict_to_properties(
            params_int, 'create_integration.prop', with_quotes=False)
    else:
        # update interface, parameter to trigger rebase_env
        print('update_exists: {},{},{}'.format(int_change, comp_name, bb_ver))
        env_change = r'comp_name={}\n'.format(comp_name)
        env_change += r'bb_version={}\n'.format(
            '{}_{}'.format(comp_name, bb_ver))
        env_change += r'commit_id={}'.format(repo_ver)
        rebase_job_param = {'root_change': root_change,
                            'env_change': env_change}
        job_tool.write_dict_to_properties(
            rebase_job_param, 'rebase_env.prop', with_quotes=False)


if __name__ == '__main__':
    fire.Fire()
