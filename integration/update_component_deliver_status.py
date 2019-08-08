#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import argparse
import ruamel.yaml as yaml
from api import gerrit_rest


def check_need_update(feature_list):
    need_update = False
    if not feature_list:
        print('[Info] No feature is under delivering now!')
    else:
        for feature in feature_list:
            if feature['status'] == 'on-going':
                need_update = True
            else:
                continue
    return need_update


def update_component_deliver_status(component_deliver_list, feature_list):
    for deliver_component_item in component_deliver_list:
        deliver_feature_found = False
        deliver_component = deliver_component_item['component']
        deliver_feature = deliver_component_item['feature_id']
        for feature in feature_list:
            if deliver_feature == feature['feature_id']:
                deliver_feature_found = True
                for component in feature['components']:
                    if deliver_component == component['name']:
                        component['delivered'] = True
                        print("[Info] Component {} deliver status updated to true".format(deliver_component))
                    else:
                        print("[Info] Component {} is not in feature {}".format(deliver_component, deliver_feature))
        if not deliver_feature_found:
            print("[Info] Feature {} is not in the deliver list".format(deliver_feature))


def update_feature_status(feature_list):
    for feature in feature_list:
        if feature['status'] == "ready":
            continue
        component_deliver_done = True
        for component in feature['components']:
            if not component['delivered']:
                component_deliver_done = False
                break
        if component_deliver_done:
            feature['status'] = "ready"


def submit_change_to_gerrit(rest, file_path, new_feature_list):
    change_id, ticket_id, rest_id = rest.create_ticket(
        'MN/SCMTA/zuul/feature_list', None, 'master', 'update component and feature status')
    rest.add_file_to_change(ticket_id, file_path, new_feature_list)
    rest.publish_edit(ticket_id)
    rest.review_ticket(ticket_id,
                       'submit new deliver feature list',
                       {'Code-Review': 2, 'Verified': 1, 'Gatekeeper': 1})
    rest.submit_change(ticket_id)


def main():
    parser_obj = argparse.ArgumentParser(
        description="this is the help usage of %(prog)s",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser_obj.add_argument(
        "--component_deliver_list_yaml",
        required=True,
        default='',
        help=" the list which contains the component deliver status ",
        dest="component_deliver_list_yaml")
    parser_obj.add_argument(
        "--feature_list_path",
        required=True,
        default='',
        help=" update the status to which feature list file ",
        dest="feature_list_path")
    parser_obj.add_argument(
        "--gerrit_info_path",
        required=True,
        default='',
        help="",
        dest="gerrit_info_path")
    param_parser = parser_obj.parse_args()
    component_deliver_list_yaml = param_parser.component_deliver_list_yaml
    feature_list_path = param_parser.feature_list_path
    gerrit_info_path = param_parser.gerrit_info_path

    component_deliver_list = yaml.load(component_deliver_list_yaml, Loader=yaml.Loader, version='1.1')
    with open(feature_list_path, 'r') as f:
        feature_list = yaml.load(f, Loader=yaml.Loader, version='1.1')
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)

    # 0 no need to update if no on-going status feature in feature list
    need_update = check_need_update(feature_list)
    if need_update:
        # 1 update component deliver status
        update_component_deliver_status(component_deliver_list, feature_list)
        # 2 update feature status if all component delivered
        update_feature_status(feature_list)
        # 3 replace the old deliver_feature_list and submit to gerrit
        new_feature_list = yaml.dump(feature_list, Dumper=yaml.RoundTripDumper)
        submit_change_to_gerrit(rest, 'deliver_feature_list.yaml', new_feature_list)


if __name__ == '__main__':
    main()
