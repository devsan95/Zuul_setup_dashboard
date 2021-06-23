import os
import re
import git
import yaml
import shutil
from api import env_repo as get_env_repo
from mod import utils
from mod import config_yaml
from mod.integration_change import RootChange
from mod.integration_change import IntegrationChange


INTEGRATION_URL = 'ssh://gerrit.ext.net.nokia.com:29418/MN/5G/COMMON/integration'


def parse_env_change_split(env_change_split):
    env_change_dict = {}
    for env_line in env_change_split:
        if '=' in env_line:
            key, value = env_line.split('=', 1)
            env_change_dict[key.strip()] = value.strip()
    return env_change_dict


def update_config_yaml_change_dict(rest, change_no, config_yaml_file,
                                   updated_dict, removed_dict):
    if not updated_dict:
        updated_dict = {}
    if not removed_dict:
        removed_dict = {}
    local_updated_dict, local_removed_dict = get_yaml_change_from_change(
        rest, change_no, config_yaml_file=config_yaml_file)
    for local_key, local_section in local_updated_dict.items():
        if local_key not in updated_dict:
            print('Add {} change to updated_dict from {}'.format(local_key, change_no))
            updated_dict[local_key] = local_section
    for local_key, local_remove_section in local_removed_dict.items():
        if local_key not in removed_dict:
            print('Add {} change to removed_dict from {}'.format(local_key, change_no))
            removed_dict[local_key] = local_remove_section


def create_config_yaml_by_env_change(env_change_split, rest,
                                     change_id, config_yaml_file='config.yaml',
                                     config_yaml_updated_dict=None, config_yaml_removed_dict=None):
    change_content = rest.get_file_change(config_yaml_file, change_id)
    old_content = change_content['old']
    if not old_content:
        try:
            print('get content from {} in {}'.format(config_yaml_file, change_id))
            old_content = rest.get_file_content(config_yaml_file, change_id)
        except Exception:
            print('Cannot find {} in {}'.format(config_yaml_file, change_id))
    if not old_content:
        return {}
    config_yaml_obj = config_yaml.ConfigYaml(config_yaml_content=old_content)
    update_config_yaml_change_dict(rest, change_id, config_yaml_file,
                                   config_yaml_updated_dict, config_yaml_removed_dict)
    # update config_yaml change in config.yaml if there's any
    if config_yaml_updated_dict or config_yaml_removed_dict:
        print("Updating config yaml with config_yaml_change")
        config_yaml_obj.update_changes(config_yaml_updated_dict, config_yaml_removed_dict)
    # update env_change in config.yaml
    # update staged infos if exists
    env_file_changes = config_yaml_obj.update_by_env_change(parse_env_change_split(env_change_split))
    config_yaml_content = yaml.safe_dump(config_yaml_obj.config_yaml, default_flow_style=False)
    if config_yaml_content != old_content:
        return {config_yaml_file: config_yaml_content}, env_file_changes
    return {}, env_file_changes


def equal_string_dicts(dict1, dict2):
    key_list1 = dict1.keys()
    key_list2 = dict2.keys()
    for key1 in key_list1:
        if key1 not in dict2:
            return False
        if isinstance(dict1[key1], dict) and isinstance(dict2[key1], dict):
            if not equal_string_dicts(dict1[key1], dict2[key1]):
                return False
        elif dict1[key1] != dict2[key1]:
            return False
    for key2 in key_list2:
        if key2 not in dict1:
            return False
    return True


def create_config_yaml_by_content_change(rest, old_content, new_content,
                                         change_no, config_yaml_file='config.yaml'):
    old_config_yaml = config_yaml.ConfigYaml(config_yaml_content=old_content)
    new_config_yaml = config_yaml.ConfigYaml(config_yaml_content=new_content)
    file_content = rest.get_file_content(config_yaml_file, change_no)
    final_config_yaml = config_yaml.ConfigYaml(config_yaml_content=file_content)
    for new_key, section in new_config_yaml.components.items():
        if new_key in old_config_yaml.components and \
                equal_string_dicts(section, old_config_yaml.components[new_key]):
            continue
        if new_key in final_config_yaml.components:
            print('update section {}'.format(new_key))
            final_config_yaml.components[new_key].update(section)
        else:
            print('add section {}'.format(new_key))
            final_config_yaml.components[new_key] = section
    for old_key, section in old_config_yaml.components.items():
        if old_key not in new_config_yaml.components:
            print('remove section key {}'.format(old_key))
            final_config_yaml.components.pop(old_key)
    config_yaml_content = yaml.safe_dump(final_config_yaml.config_yaml, default_flow_style=False)
    if config_yaml_content != file_content:
        return {config_yaml_file: config_yaml_content}
    return {}


def create_file_change_by_env_change(env_change_split, file_content, filename):
    change_dict = parse_env_change_split(env_change_split)
    return create_file_change_by_env_change_dict(change_dict, file_content, filename, env_change_split)


def create_file_change_by_env_change_dict(change_dict, file_content, filename, env_change_split=None):
    lines = file_content.split('\n')
    for i, line in enumerate(lines):
        if '=' in line:
            key2, value2 = line.strip().split('=', 1)
            print('try to find key {}'.format(key2))
            if key2.strip() in change_dict:
                print('find key {}'.format(key2))
                lines[i] = key2 + '=' + change_dict[key2.strip()]
    if env_change_split:
        for env_line in env_change_split:
            if env_line.startswith('#'):
                lines.append(env_line)
    ret_dict = {filename: '\n'.join(lines)}
    return ret_dict


def rebase_integration_change(rest, change_no):
    # only suport change with only config.yaml, without env_change
    env_path = get_env_repo.get_env_repo_info(rest, change_no)[1]
    branch = rest.get_ticket(change_no)['branch']
    if env_path:
        print('Only support new branch without env file')
        print('Exit rebasing integration')
        return
    # get integration workspace
    int_work_dir = os.path.join(os.getcwd(), 'integration_{}'.format(change_no))
    if os.path.exists(int_work_dir):
        shutil.rmtree(int_work_dir)
    os.makedirs(int_work_dir)
    integration_git = git.Git(int_work_dir)
    integration_git.init()
    integration_git.fetch(INTEGRATION_URL, branch)
    integration_git.checkout('FETCH_HEAD')
    # get staged/submodule list from config.yaml files
    nb_related_files = get_nb_related_files(rest, change_no, int_work_dir)
    # cherry-pick ticket change
    print("Executing git fetch {}".format(rest.get_commit(change_no)['commit']))
    integration_git.fetch(INTEGRATION_URL, rest.get_commit(change_no)['commit'])
    cherry_pick_params = '--strategy=recursive -X theirs'
    try:
        print("Executing git cherry-pick FETCH_HEAD {}".format(cherry_pick_params))
        integration_git.cherry_pick('FETCH_HEAD', cherry_pick_params.split())
        print("Git Status:\n{}".format(integration_git.status()))
    except Exception:
        print('Conflict in cherry-pick, try to solve...')
        for nb_related_file in nb_related_files:
            print('Restore file: {}'.format(nb_related_file))
            integration_git.reset('HEAD', nb_related_file)
            integration_git.checkout(nb_related_file)
        if integration_git.diff():
            print("Cannot solve conflict:\n {}".format(integration_git.status()))
            return
        integration_git.config('core.editor', 'true')
        integration_git.cherry_pick('--continue')
    integration_git.commit('--amend', '--reset-author', '--no-edit')
    print('Push rebased change to {}'.format(change_no))
    integration_git.push(INTEGRATION_URL, 'HEAD:refs/for/{}'.format(branch))


def get_yaml_change_from_change(rest, change_no, config_yaml_file='config.yaml'):
    updated_dict = {}
    removed_dict = {}
    try:
        config_yaml_change = rest.get_file_change(config_yaml_file, change_no)
        if ('new' in config_yaml_change and config_yaml_change['new']) and \
                'old' in config_yaml_change and config_yaml_change['old']:
            print('Initial config_yaml_obj')
            config_yaml_obj = config_yaml.ConfigYaml(config_yaml_content=config_yaml_change['new'])
            print('Get change from config_yaml_obj')
            updated_dict, removed_dict = config_yaml_obj.get_changes(yaml.safe_load(config_yaml_change['old']))
    except Exception as e:
        print('Cannot find config.yaml for %s', change_no)
        print(str(e))
    return updated_dict, removed_dict


def rebase_component_config_yaml(rest, change_no, config_yaml_dict):
    op = RootChange(rest, change_no)
    comp_change_list, int_change = op.get_components_changes_by_comments()
    updated_dict, removed_dict = get_yaml_change_from_change(rest, change_no)
    for comp_change in comp_change_list:
        if comp_change == change_no:
            continue
        if rest.get_change(comp_change)['mergeable']:
            continue
        int_change_obj = IntegrationChange(rest, comp_change)
        comp_project = int_change_obj.get_project()
        if comp_project in config_yaml_dict:
            local_config_yaml = config_yaml_dict[comp_project]
            rebase_config_yaml_in_component(rest, comp_change, local_config_yaml,
                                            updated_dict, removed_dict)


def get_yaml_change_and_rebase(rest, root_change, comp_change,
                               local_config_yaml, rebase_version='HEAD'):
    updated_dict, removed_dict = get_yaml_change_from_change(rest, root_change)
    return rebase_config_yaml_in_component(rest, comp_change, local_config_yaml,
                                           updated_dict, removed_dict, rebase_version)


def rebase_config_yaml_in_component(rest, comp_change, local_config_yaml,
                                    updated_dict, removed_dict, rebase_version='HEAD'):
    rebase_result = True
    print('Update local config yaml :{} for {}'.format(local_config_yaml, comp_change))
    update_config_yaml_change_dict(rest, comp_change, local_config_yaml,
                                   updated_dict, removed_dict)
    delete_edit(rest, comp_change)
    print('Restor local_config_yaml: {}'.format(local_config_yaml))
    rest.restore_file_to_change(comp_change, local_config_yaml)
    rest.publish_edit(comp_change)
    try:
        print('Try rebase ...')
        if rebase_version == 'HEAD':
            rest.rebase(comp_change)
        else:
            rest.rebase(comp_change, rebase_version)
    except Exception:
        print('Rebase Failed ...')
        rebase_result = False
    config_yaml_content = create_config_yaml_by_env_change(
        '',
        rest,
        comp_change,
        config_yaml_file=local_config_yaml,
        config_yaml_updated_dict=updated_dict,
        config_yaml_removed_dict=removed_dict)[0][local_config_yaml]
    rest.add_file_to_change(comp_change, local_config_yaml, config_yaml_content)
    rest.publish_edit(comp_change)
    return rebase_result


def get_nb_related_files(rest, change_no, int_work_dir):
    nb_related_files = []
    submodule_map = get_submodule_map(int_work_dir)
    config_yaml_files = [os.path.join(int_work_dir, 'config.yaml')]
    stream_config_yaml_path = os.path.join(int_work_dir, 'meta-5g-cb', 'config_yaml')
    config_yaml_files.extend(utils.find_files(stream_config_yaml_path, 'config.yaml'))
    change_file_list = rest.get_file_list(change_no)
    config_yaml_objects = []
    for config_yaml_file in config_yaml_files:
        config_yaml_content = utils.get_file_content(config_yaml_file)
        config_yaml_objects.append(config_yaml.ConfigYaml(config_yaml_content=config_yaml_content))
    for change_file in change_file_list:
        for config_yaml_object in config_yaml_objects:
            section_key, section = config_yaml_object.find_section_by_matched_location(change_file)
            if section and section['type'] == 'staged':
                print("find matched localtion for %s", change_file)
                nb_related_files.append(change_file)
                break
            if change_file in submodule_map:
                if config_yaml_object.find_section_by_matched_location(submodule_map[change_file])[0]:
                    print("find matched submodule for %s", change_file)
                    nb_related_files.append(change_file)
                    break
    return nb_related_files


def get_submodule_map(int_work_dir):
    submodule_map = {}
    with open(os.path.join(int_work_dir, '.gitmodules'), 'r') as fr:
        file_path = ''
        for line in fr.read().splitlines():
            if line.startswith('[submodule'):
                file_path = ''
            m_path = re.search('path *= *([^ ]*)', line)
            if m_path:
                file_path = m_path.group(1)
            m_url = re.search('url *= *([^ ]*)', line)
            if m_url and file_path:
                submodule_map[file_path] = m_url.group(1)
    return submodule_map


def delete_edit(rest, change_no):
    print('delete edit for change {}'.format(change_no))
    try:
        rest.delete_edit(change_no)
    except Exception as e:
        print('delete edit failed, reason:')
        print(str(e))
