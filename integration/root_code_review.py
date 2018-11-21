#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import click
import ruamel.yaml as yaml
from api import gerrit_rest


def check_deliver_feature(feature_list_path, rest):
    ok_to_go = False
    with open(feature_list_path, 'r') as f:
        feature_list = yaml.load(f, Loader=yaml.Loader, version='1.1')
    if feature_list:
        print "[ERROR] There's feature under deliver and deliver_feature_list yaml file is not empty"
        return ok_to_go
    else:
        query_string = 'project:MN/SCMTA/zuul/inte_root AND status:open AND label:Code-Review=2'
        query_result = rest.query_ticket(query_string)
        print query_result
        if query_result:
            print "[ERROR] There's root change get code review but not go into post"
            return ok_to_go
        else:
            ok_to_go = True
            return ok_to_go


@click.command()
@click.option('--root_change', help='the root gerrit change number')
@click.option('--gerrit_info_path', help='gerrit info path')
@click.option('--feature_list_path', help='the feature list path')
def main(root_change, gerrit_info_path, feature_list_path):

    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    ok_to_go = check_deliver_feature(feature_list_path, rest)
    if not ok_to_go:
        raise Exception("There's other feature under deliver, please contact CB SCM team to handle!")

    print "There's no other feature under deliver, going to give code review+2 to the change"
    rest.review_ticket(root_change, 'going to deliver this feature, code review+2 given to root change', {'Code-Review': 2})


if __name__ == '__main__':
    main()
