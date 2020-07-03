import os
import re
import git
import copy
import fire
import yaml
import shutil
import logging
import traceback

from mod import utils
from mod import wft_tools
from mod import integration_repo


SCRIPT_ROOT = os.path.realpath(
    os.path.join(os.path.split(os.path.realpath(__file__))[0], ".."))
FETCH_CLASS_FILE = os.path.join(
    SCRIPT_ROOT, 'CITOOLS/mod/fetch_no_submodules.bbclass')
REVISION_KEY_LIST = ['REVISION', 'SVNTAG', 'SVNREV', 'SRCREV', 'BIN_VER', 'SRC_REV']
GNB_INTERFACES_COMPS = ['cplane-5g', 'cp-nrt', 'cp-rt']


def get_feature_list(integration_obj):
    feature_dict = {}
    # get feature list info from stream_config.yaml
    stream_config_yaml_files = utils.find_files(
        os.path.join(integration_obj.work_dir, 'meta-5g-cb/config_yaml'), 'config.yaml')
    logging.info('Get feature info from : %s', stream_config_yaml_files)
    for stream_config_yaml_file in stream_config_yaml_files:
        logging.info('Parse %s', stream_config_yaml_file)
        stream_config_yaml = {}
        with open(stream_config_yaml_file, 'r') as fr:
            stream_config_yaml = yaml.safe_load(fr.read())
        for key, component_value in stream_config_yaml['components'].items():
            if 'features' in component_value and 'feature_component' in component_value:
                logging.info('Get feature info: %s', component_value)
                component = component_value['feature_component']
                for feature_id, feature_value in component_value['features'].items():
                    if feature_id not in feature_dict:
                        feature_dict[feature_id] = {'feature_id': feature_id,
                                                    'components': [],
                                                    'platform_id': feature_value['platform_id'],
                                                    'status': ''}
                    if component not in [x['name'] for x in feature_dict[feature_id]['components']]:
                        component_delivery_info = {'name': component,
                                                   'config_yaml_key': key,
                                                   'frozen_version': component_value['version'],
                                                   'delivered': feature_value['feature_delivered']}
                        feature_dict[feature_id]['components'].append(component_delivery_info)
                    if not feature_value['feature_delivered']:
                        feature_dict[feature_id]['status'] = 'on-going'
                    elif not feature_dict[feature_id]['status']:
                        feature_dict[feature_id]['status'] = 'ready'
    logging.info('Feature list: %s', feature_dict.values())
    return feature_dict.values()


def gen_component_info(component, integration_obj):
    recipe_integration_path = os.path.join(integration_obj.work_dir, 'meta-5g-cb/recipes-integration')
    logging.info('Find inc files from %s', recipe_integration_path)
    inc_files = utils.find_files(recipe_integration_path, "*.inc")
    component_infos = []
    component_regexs = []
    logging.info('Get component info for %s from %s', component, inc_files)
    for inc_file in inc_files:
        logging.info('Find in %s', inc_file)
        with open(inc_file, 'r') as fr:
            for line in fr.read().splitlines():
                if line.startswith('{}-'.format(component)):
                    logging.info('Matched line %s', line)
                    component_regex = line.split()[0]
                    config_file = os.path.basename(inc_file).split('.inc')[0].replace('components-', '.config-')
                    integration_obj.set_config_file(config_file)
                    module = os.path.basename(os.path.dirname(inc_file)).split('integration-')[1]
                    target_key = 'TARGET_{}'.format(module.replace('-', '_'))
                    try:
                        target = integration_obj.get_config_value(target_key)
                    except Exception:
                        logging.warn('Cannot get %s from %s', target_key, config_file)
                        continue
                    if component_regexs and component_regex not in component_regexs:
                        logging.warn('Multi version find in different stream %s %s',
                                     component_infos[0][1], config_file)
                        logging.warn('versions: %s %s', component_regexs[0], component_regex)
                    elif component_regex not in component_regexs:
                        component_regexs.append(component_regex)
                        component_infos.append(
                            {'name': component,
                             'regex': component_regex,
                             'target': target,
                             'module': module,
                             'config_file': config_file})
    logging.info('Get component info %s', component_infos)
    return component_infos


def run_bitbake_command(component_info, integration_obj, *bitbake_args):
    integration_obj.set_config_file(component_info['config_file'])
    module = component_info['module']
    target = component_info['target']
    return integration_obj.prepare_prefix_and_run_bitbake_cmd(
        target, module.startswith('Yocto'), *bitbake_args)


def get_component_env(component_info, integration_obj):
    component_regex = component_info['regex']
    return run_bitbake_command(component_info, integration_obj, '-e', component_regex)


def find_component_env_value(bitbake_env_out, value):
    for line in bitbake_env_out.splitlines():
        if line.endswith('="{}"'.format(value)):
            return True
    return False


def get_component_env_value(bitbake_env_out, env_key_list):
    for line in bitbake_env_out.splitlines():
        for env_key in env_key_list:
            if line.startswith('{}='.format(env_key)):
                return line.split('{}='.format(env_key))[1].replace('"', '')
    raise('Cannot find value for {}'.format(env_key_list))


def get_component_env_key(bitbake_env_out, env_value):
    for line in bitbake_env_out.splitlines():
        if line.startswith('="{}"'.format(env_value)):
            return line.split('=')[0]
    raise('Cannot find key for {}'.format(env_value))


def get_repo_and_check(component_info, integration_obj, bitbake_env_out, feature):
    feature_id = feature['feature_id']
    # use bitbake command to get component repo
    #     run bitbake \
    #                  -R "${tools_dir}/feature-checks/fetch-no-submodules.bbclass" \
    #                  -c unpack "${components_to_fetch[@]%% *}"
    logging.info('Fetch component:%s by bitbake', component_info['regex'])
    run_bitbake_command(component_info, integration_obj, '-R', FETCH_CLASS_FILE, '-c', 'unpack', component_info['regex'])
    # get component hash key name
    source_dir = get_component_env_value(bitbake_env_out, ['S'])
    src_uri = get_component_env_value(bitbake_env_out, ['SRC_URI'])
    if 'destsuffix=' in src_uri:
        source_dir = src_uri.split('destsuffix=')[1]
    if not os.path.exists(os.path.join(source_dir, '.git')):
        logging.warn('%s is not a git repo path', source_dir)
        return None
    g_source_dir = git.Git(source_dir)
    current_version = g_source_dir.log('-1', '--pretty=format:%H').strip('"')
    # get last compoent version for this stream.
    pre_component_info = copy.copy(component_info)
    previous_version = ''
    for component_delivery_info in feature['components']:
        if component_delivery_info['name'] == component_info['name']:
            pre_bbversion = component_delivery_info['frozen_version']
            pre_component_info['regex'] = '{}-{}'.format(component_info['name'], pre_bbversion)
            previous_version = get_repo_version(pre_component_info, integration_obj)
    if not previous_version:
        logging.warn('Cannot get previsou version for %s', pre_component_info)
        return None
    # check commit message
    # run git log --pretty="format:%B" "${start}..${end}" | sed -rn
    # 's/^([0-9]+_)?%FIFI=//p'
    commit_msgs = g_source_dir.log('--pretty="format:%B"', '{}..{}'.format(previous_version, current_version))
    logging.info('Commit message: %s', commit_msgs)
    m = re.search(r'%FIFI={}'.format(feature_id), commit_msgs)
    if m:
        logging.info('Find FIFI=%s in Commit message', )
        return True
    return False


def get_repo_version(pre_component_info, integration_obj):
    logging.info('Try to get bitbake env for %s', pre_component_info['regex'])
    pre_component_env = ''
    try:
        pre_component_env = run_bitbake_command(pre_component_info, integration_obj, '-e', pre_component_info['regex'])
    except Exception:
        logging.info('Directly run bitbake -e %s failed', pre_component_info['regex'])
        logging.info('Try to search this recipe')
        # find old recipe file from meta-5g
        meta_5g_path = os.path.join(os.environ['WORKSPACE'], 'meta-5g')
        logging.info('Find old recipe from %s', meta_5g_path)
        if not os.path.exists(meta_5g_path):
            logging.error('Cannot find %s', meta_5g_path)
            return ''
        logging.info('Initial git obj %s', meta_5g_path)
        meta_5g_git = git.Git(meta_5g_path)
        recipe_name = pre_component_info['regex'].replace('{}-'.format(pre_component_info['name']),
                                                          '{}_'.format(pre_component_info['name']))
        recipe_path = 'recipes-components/{}/{}.bb'.format(pre_component_info['name'], recipe_name)
        logging.info('recipe_path %s', recipe_path)
        old_recipe_hashs = meta_5g_git.log('--pretty=format:%H', '--full-history', '--', recipe_path)
        old_recipe_hash = old_recipe_hashs.split()[-1]
        logging.info('Hash for %s is %s', recipe_path, old_recipe_hash)
        if old_recipe_hash:
            logging.info('checkout  %s in %s', recipe_path, old_recipe_hash)
            meta_5g_git.checkout(old_recipe_hash, recipe_path)
            shutil.copyfile(os.path.join(meta_5g_path, recipe_path),
                            os.path.join(integration_obj.work_dir, 'meta-5g', recipe_path))
        pre_component_env = run_bitbake_command(pre_component_info, integration_obj, '-e', pre_component_info['regex'])
    return get_component_env_value(pre_component_env, REVISION_KEY_LIST)


def update_feature_yaml(feature, matched_components, not_matched_components, integration_obj):
    comp_all_delivered = True
    feature_id = feature['feature_id']
    stream_config_yaml = {}
    # get feature list info from stream_config.yaml
    stream_config_yaml_files = utils.find_files(
        os.path.join(integration_obj.work_dir, 'meta-5g-cb/config_yaml'), 'config.yaml')
    for stream_config_yaml_file in stream_config_yaml_files:
        logging.info('Open %s', stream_config_yaml_file)
        with open(stream_config_yaml_file, 'r') as fr:
            stream_config_yaml[stream_config_yaml_file] = yaml.safe_load(fr.read())
    for feature_comp in feature['components']:
        name = feature_comp['name']
        feature_delivered = feature_comp['delivered']
        if name in matched_components and name not in not_matched_components:
            feature_delivered = True
            feature_comp['delivered'] = True
        if not feature_delivered:
            comp_all_delivered = False
        for stream_config_yaml_file in stream_config_yaml_files:
            config_dict = stream_config_yaml[stream_config_yaml_file]
            for key, component_value in config_dict['components'].items():
                if 'features' in component_value and 'feature_component' in component_value:
                    feature_dict = copy.deepcopy(component_value['features'])
                    if component_value['feature_component'] == feature_comp['name']:
                        logging.info('Set delivered for %s to %s', name, feature_delivered)
                        feature_dict[feature_id]['feature_delivered'] = feature_delivered
                        logging.info('Component feature info %s', feature_dict)
                        component_value['features'] = feature_dict
    for stream_config_yaml_file in stream_config_yaml_files:
        config_dict = stream_config_yaml[stream_config_yaml_file]
        with open(stream_config_yaml_file, 'w') as fw:
            fw.write(yaml.safe_dump(config_dict))
    if comp_all_delivered:
        feature['status'] = 'ready'


def push_integration_change(integration_dir, branch, commit_message):
    # check if changed
    git_integration = git.Git(integration_dir)
    status_out = git_integration.status('-s', 'meta-5g-cb/config_yaml')
    if status_out:
        logging.info('Change in stream config.yaml: %s', status_out)
        git_integration.add('meta-5g-cb/config_yaml')
        git_integration.commit('-m', commit_message)
        logging.info('Run git pull --rebase origin %s', branch)
        git_integration.pull('--rebase', 'origin', branch)
        logging.info('Run git push origin HEAD:%s', branch)
        git_integration.push('origin', 'HEAD:{}'.format(branch))
    else:
        logging.info('No change find in stream config.yaml')


def find_multi_platforms_in_global(feature, integration_obj):
    multi_platforms_in_global = {}
    multi_platforms_list = []
    feature_id = feature['feature_id']
    # find platform from stream_config_yaml
    # without feature_components
    stream_config_yamls = utils.find_files(
        os.path.join(integration_obj.work_dir, 'meta-5g-cb/config_yaml'), 'config.yaml')
    for stream_config_yaml_file in stream_config_yamls:
        stream_config_yaml = {}
        with open(stream_config_yaml_file, 'r') as fr:
            stream_config_yaml = yaml.safe_load(fr.read())
        for component, component_value in stream_config_yaml['components'].items():
            if 'features' in component_value:
                if feature_id in component_value['features']:
                    if 'feature_components' not in component_value:
                        multi_platforms_list.append(component)
    with open(os.path.join(integration_obj.work_dir, 'config.yaml'), 'r') as fr:
        config_yaml = yaml.safe_load(fr.read())
        for platform_key in multi_platforms_list:
            if platform_key in config_yaml['components'].keys():
                multi_platforms_in_global[platform_key] = config_yaml['components'][platform_key]
    return multi_platforms_in_global


def find_component_in_global(feature, integration_obj):
    components_in_global = {}
    # get global config.yaml
    git_integration = git.Git(integration_obj.work_dir)
    git_integration.checkout('config.yaml')
    with open(os.path.join(integration_obj.work_dir, 'config.yaml'), 'r') as fr:
        config_yaml = yaml.safe_load(fr.read())
        # check if there is feature component in config.yaml
        for component_delivery_info in feature['components']:
            comp_name = component_delivery_info['name']
            if 'config_yaml_key' in component_delivery_info:
                comp_wft_key = component_delivery_info['config_yaml_key']
                if comp_wft_key in config_yaml['components'].keys():
                    components_in_global[comp_name] = {
                        'config_yaml_key': comp_wft_key,
                        'version': config_yaml['components'][comp_wft_key]['version']}
    return components_in_global


def filter_sidepackage_componets(components, together_repo_dict, is_interfaces=False):
    filter_components = []
    sidepacakges_components = []
    for component in components:
        name = component['name']
        frozen_version = component['frozen_version']
        for repo, together_comps in together_repo_dict.items():
            if name in together_comps and repo == 'MN/5G/NB/gnb':
                if name not in GNB_INTERFACES_COMPS:
                    sidepacakges_components.append(name)
                    break
                elif not is_interfaces:
                    matched_names = [x['name'] for x in filter_components if x['name'] in together_comps]
                    if matched_names:
                        sidepacakges_components.append(name)
                        break
                sub_builds = []
                try:
                    sub_builds = wft_tools.get_subuild_from_wft(frozen_version, name)
                except Exception:
                    logging.warn('Can not find wft_tools for %s:%s', name, frozen_version)
                if not sub_builds:
                    sidepacakges_components.append(name)
                break
        if name in sidepacakges_components:
            continue
        filter_components.append(component)
    return filter_components, sidepacakges_components


def get_subbuilds_and_env(components, integration_obj):
    components_all_info = {}
    for component in components:
        name = component['name']
        subbuilds_and_env = {}
        if not component['delivered']:
            sub_builds = []
            # serch component in all inc file under recipe-integration
            component_infos = gen_component_info(name, integration_obj)
            if not component_infos:
                logging.error('Cannot find component_info for %s', name)
                continue
            for component_info in component_infos:
                regex = component_info['regex']
                # get components bitbake env
                try:
                    bitbake_env_out = get_component_env(component_info, integration_obj)
                    wft_name = get_component_env_value(bitbake_env_out, ['PV'])
                except Exception:
                    traceback.print_exc()
                    logging.warn('Cannot run bitbake -e for %s', component_info)
                    logging.warn('Not delivered or some dependency not delivered')
                    continue
                # get sub_builds from WFT
                try:
                    sub_builds = wft_tools.get_subuild_from_wft(wft_name, component['name'])
                except Exception:
                    logging.warn('Cannot get package or sub_builds for %s', wft_name)
                    sub_builds = []
                subbuilds_and_env = {'wft_name': wft_name,
                                     'sub_builds': sub_builds,
                                     'component_info': component_info,
                                     'bitbake_env_out': bitbake_env_out}
                if name not in components_all_info:
                    components_all_info[name] = {}
                components_all_info[name][regex] = subbuilds_and_env
    return components_all_info


def update_feature(feature, integration_obj, together_repo_dict):
    feature_id = feature['feature_id']
    platform_id = feature['platform_id']
    multi_platforms_in_global = {}
    if platform_id == 'RCPvDU':
        multi_platforms_in_global = find_multi_platforms_in_global(feature, integration_obj)
    logging.info('multi_platforms_in_global: %s', multi_platforms_in_global)
    # branch = feature['branch']
    components = feature['components']
    logging.info('Feature components is %s', components)
    # repo_path_branch = integration_obj.get_integration_branch()
    # logging.info('Feature branch is %s', branch)
    # logging.info('Repo branch is %s', repo_path_branch)
    # if branch == repo_path_branch:
    matched_components = []
    not_matched_components = []
    components_in_global = find_component_in_global(feature, integration_obj)
    # if interfaces topic, we need to check components for all interfaces
    # otherwise we only need to check one components in GNB
    if platform_id == 'feature' and components_in_global:
        filter_components, sidepacakges_components = filter_sidepackage_componets(components, together_repo_dict, True)
    else:
        filter_components, sidepacakges_components = filter_sidepackage_componets(components, together_repo_dict)
    logging.info('filter_components: %s', filter_components)
    logging.info('sidepacakges_components: %s', sidepacakges_components)
    components_all_info = get_subbuilds_and_env(filter_components, integration_obj)
    logging.info('Components in global: %s', components_in_global)
    logging.info('Components all info: %s', components_all_info.keys())
    for component in components:
        component_name = component['name']
        if component_name not in components_all_info:
            continue
        if not component['delivered']:
            for subbuilds_and_env in components_all_info[component_name].values():
                component_info = subbuilds_and_env['component_info']
                logging.info('Check component : %s', component_info)
                bitbake_env_out = subbuilds_and_env['bitbake_env_out']
                sub_builds = subbuilds_and_env['sub_builds']
                logging.info('sub_builds : %s', sub_builds)
                wft_name = subbuilds_and_env['wft_name']
                logging.info('wft_name : %s', wft_name)
                if wft_name == component['frozen_version']:
                    logging.info('Same as forzen version: %s, skipped', wft_name)
                    continue
                if platform_id != 'feature' or (components_in_global and sub_builds):
                    if multi_platforms_in_global:
                        for platform_value in multi_platforms_in_global.values():
                            if platform_value['version'] in [k['version'] for k in sub_builds]:
                                logging.info('Find %s in sub_builds', platform_value['version'])
                                matched_components.append(component['name'])
                                continue
                            else:
                                logging.info('find value %s from Bitbake_env_out', platform_value['version'])
                                if find_component_env_value(bitbake_env_out, platform_value['version']):
                                    matched_components.append(component['name'])
                                    continue
                    if feature_id in [k['version'] for k in sub_builds]:
                        matched_components.append(component['name'])
                    elif component_name in components_in_global:
                        logging.info('Component %s is in global config.yaml', component_name)
                        if wft_name == components_in_global[component_name]['version']:
                            matched_components.append(component_name)
                        else:
                            not_matched_components.append(component_name)
                    else:
                        for interface_component, new_wft_obj in components_in_global.items():
                            config_yaml_key_matched = False
                            # check in wft if component contains right
                            # interfaces version
                            for sub_build in sub_builds:
                                config_yaml_key = '{}:{}'.format(sub_build['project'], sub_build['component'])
                                logging.info('Find if %s in components_in_global', config_yaml_key)
                                if config_yaml_key == new_wft_obj['config_yaml_key']:
                                    config_yaml_key_matched = True
                                    if sub_build['version'] == new_wft_obj['version']:
                                        matched_components.append(component_name)
                                    else:
                                        not_matched_components.append(component_name)
                            if not config_yaml_key_matched:
                                # check from depends list
                                # if comonent with new  interfaces delivered
                                depends_list = get_component_env_value(bitbake_env_out, ['DEPENDS']).split()
                                if '{}-{}'.format(interface_component, new_wft_obj['version']) in depends_list:
                                    matched_components.append(component_name)
                                    if interface_component not in components_all_info \
                                            and interface_component not in matched_components \
                                            and interface_component not in not_matched_components:
                                        # check if interfaces delivered
                                        # run bitbake -e to see if it's exists
                                        # this can be removed after all components
                                        # info is right in WFT
                                        depended_component_info = copy.deepcopy(component_info)
                                        depended_component_version = '{}-{}'.format(
                                            interface_component, new_wft_obj['version'])
                                        try:
                                            logging.info('%s is delivered', depended_component_version)
                                            run_bitbake_command(depended_component_info, integration_obj,
                                                                '-e', depended_component_version)
                                            matched_components.append(interface_component)
                                        except Exception:
                                            logging.info('%s is not delivered', depended_component_version)
                                            not_matched_components.append(interface_component)

                if component_name not in matched_components and component_name not in not_matched_components:
                    check_result = None
                    try:
                        check_result = get_repo_and_check(
                            component_info, integration_obj, bitbake_env_out, feature)
                    except Exception:
                        logging.info('Get feature from %s repo commit message Failed', component_info)
                    if check_result is not None:
                        if check_result:
                            matched_components.append(component_name)
                        else:
                            not_matched_components.append(component_name)
    logging.info('Matched components %s', matched_components)
    for together_repo, together_comps in together_repo_dict.items():
        for together_comp in together_comps:
            if together_comp in matched_components and together_repo == 'MN/5G/NB/gnb':
                logging.info('%s is delivered, set all sidepacakges_components to true for %s', together_comp, together_repo)
                matched_components.extend(sidepacakges_components)
                break
    logging.info('Matched components %s', matched_components)
    logging.info('Not Matched components %s', not_matched_components)
    update_feature_yaml(feature, matched_components, not_matched_components, integration_obj)


def unforzen_config_yaml(integration_dir, features_delivered=[]):
    stream_config_yaml_changed = []
    # get all stream config.yaml
    stream_config_yamls = utils.find_files(
        os.path.join(integration_dir, 'meta-5g-cb/config_yaml'), 'config.yaml')
    # remove sections in stream config yaml
    for stream_config_yaml_file in stream_config_yamls:
        stream_config_yaml = {}
        sections_to_removed = {}
        features_comps_has_others = []
        with open(stream_config_yaml_file, 'r') as fr:
            stream_config_yaml = yaml.safe_load(fr.read())
        for component, component_value in stream_config_yaml['components'].items():
            if 'features' in component_value:
                if features_delivered:
                    other_features = []
                    for comp_feature in component_value['features'].keys():
                        if comp_feature not in features_delivered:
                            other_features.append(comp_feature)
                    if not other_features:
                        for comp_feature in component_value['features'].keys():
                            if comp_feature not in sections_to_removed:
                                sections_to_removed[comp_feature] = []
                            sections_to_removed[comp_feature].append(component)
                    else:
                        features_comps_has_others.extend(component_value['features'].keys())
                        logging.warn('Features: %s not delivered in %s', other_features, component)
                else:
                    stream_config_yaml['components'].pop(component)
        for feature_delivered in features_delivered:
            if feature_delivered not in features_comps_has_others:
                if feature_delivered not in sections_to_removed:
                    logging.warn('no section to removed for %s', feature_delivered)
                    continue
                for section_to_removed in sections_to_removed[feature_delivered]:
                    logging.info('Unfrozen section %s for %s', section_to_removed, feature_delivered)
                    stream_config_yaml['components'].pop(section_to_removed)
                stream_config_yaml_changed.append(stream_config_yaml_file)
                logging.info('Update %s for %s', stream_config_yaml_file, feature_delivered)
        with open(stream_config_yaml_file, 'w') as fw:
            fw.write(yaml.safe_dump(stream_config_yaml))
    if features_delivered and not stream_config_yaml_changed:
        logging.warn('No stream config.yaml changed for %s', features_delivered)
        return False
    return True


def update(integration_dir, branch, *together_comps):
    # get together_comps
    logging.info('Together_comps: %s', together_comps)
    together_repo_dict = {}
    for together_string in together_comps:
        together_repo = together_string.split(':')[0]
        together_repo_dict[together_repo] = together_string.split(':')[1].split()
    logging.info('Together reop dict: %s', together_repo_dict)
    integration_obj = integration_repo.INTEGRATION_REPO('', '', work_dir=integration_dir)
    feature_list = get_feature_list(integration_obj)
    all_delivered = True
    is_delivered = False
    features_delivered = []
    for feature in feature_list:
        update_feature(feature, integration_obj, together_repo_dict)
        if feature['status'] != 'ready':
            all_delivered = False
            logging.warn('Feature is not ready: %s', feature)
        else:
            features_delivered.append(feature['feature_id'])
    if features_delivered:
        is_delivered = unforzen_config_yaml(integration_dir, features_delivered)
        if is_delivered:
            logging.warn('There is one or more feature delivered in %s', features_delivered)
    if feature_list and all_delivered:
        unforzen_config_yaml(integration_dir)
    push_integration_change(integration_dir, branch, 'unforzen as some features ready')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fire.Fire()
