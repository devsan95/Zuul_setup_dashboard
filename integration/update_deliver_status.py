#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import os
import copy
import fire
import logging
import ruamel.yaml as yaml
from mod import utils
import update_feature_yaml


def update_component_deliver_status(integration_dir, components_update_dict,
                                    streams_to_set, features_to_update=[]):
    # get feature list info from stream_config.yaml
    stream_config_yaml_files = utils.find_files(
        os.path.join(integration_dir, 'meta-5g-cb/config_yaml'), 'config.yaml')
    logging.info('Get feature info from : %s', stream_config_yaml_files)
    for stream_config_yaml_file in stream_config_yaml_files:
        if streams_to_set:
            if os.path.basename(os.path.dirname(stream_config_yaml_file)) not in streams_to_set:
                logging.info('%s not in streams %s', stream_config_yaml_file, streams_to_set)
                continue
        logging.info('Parse %s', stream_config_yaml_file)
        stream_config_yaml = {}
        with open(stream_config_yaml_file, 'r') as fr:
            stream_config_yaml = yaml.safe_load(fr.read())
        updated = False
        for key, component_value in stream_config_yaml['components'].items():
            if 'features' in component_value and 'feature_component' in component_value:
                feature_component = component_value['feature_component']
                logging.info('check %s', feature_component)
                features = component_value['features']
                new_features = copy.deepcopy(features)
                if feature_component in components_update_dict:
                    for feature_id, feature_obj in new_features.items():
                        if not features_to_update or feature_id in features_to_update:
                            feature_delivered = components_update_dict[feature_component] is True
                            if feature_delivered != feature_obj['feature_delivered']:
                                logging.info('set %s of %s to %s', feature_id, feature_component, feature_delivered)
                                feature_obj['feature_delivered'] = feature_delivered
                                updated = True
                component_value['features'] = new_features
        if not updated:
            continue
        with open(stream_config_yaml_file, 'w') as fw:
            fw.write(yaml.safe_dump(stream_config_yaml))


def update(integration_dir, features, branch, together_comps, streams, *components_to_update):
    feature_list = features.split(',')
    components_update_dict = {}
    together_repo_dict = {}
    for together_line in together_comps.split(','):
        if ':' in together_line:
            together_repo_dict[together_line.split(':')[0]] = together_line.split(':')[1].split()
    for component_line in components_to_update:
        component = component_line.split(':')[0]
        component_status = component_line.split(':')[1].strip() == 'true'
        if component in together_repo_dict:
            for sub_component in together_repo_dict[component]:
                components_update_dict[sub_component] = component_status
            continue
        if component_status and component:
            components_update_dict[component] = component_status
    logging.info('Component update dict: %s', components_update_dict)
    streams_to_set = []
    if streams.strip() != 'none':
        streams_to_set = streams.strip().split(',')

    update_component_deliver_status(integration_dir, components_update_dict,
                                    streams_to_set, feature_list)
    update_feature_yaml.push_integration_change(integration_dir, branch, 'update component feature status')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fire.Fire()
