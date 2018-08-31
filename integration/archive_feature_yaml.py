#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import arrow
import fire
import ruamel.yaml as yamllib
from slugify import slugify

import yaml_validator
from api import gerrit_rest


def save_file_to_gerrit(rest, file_content, project, branch, path):
    message = "Archive feature yaml {}".find(path)
    change_id, ticket_id, rest_id = rest.create_ticket(
        project, None, branch, message)
    rest.add_file_to_change(rest_id, path, file_content)
    rest.publish_edit(rest_id)
    print(rest.get_change_address(ticket_id))
    rest.review_ticket(rest_id, 'merge', {'Code-Review': 2})


def save_to_gerrit(
        gerrit_info_path, yaml, identity,
        project, branch,
        schema_path=None, dependent=True,
        output_path=None):
    adt = arrow.utcnow()
    name = adt.isoformat()
    if identity:
        name = name + '_' + identity
    name += '.yaml'
    name = slugify(name)
    file_path = 'feature_archive/{}'.format(name)
    print('Archive into gerrit, path {}'.format(file_path))
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    yaml_obj = yamllib.load(
        yaml, Loader=yamllib.Loader, version='1.1')
    if schema_path:
        print('Verify schema')
        with open(schema_path) as f:
            json_schema = yaml_validator.json.load(f)
            yaml_validator.validate(yaml_obj, json_schema)
    if dependent:
        print('Verify dependent')
        graph_obj = yaml_validator.create_graph(yaml_obj)[3]
        yaml_validator.check_graph_cycling(graph_obj)
    formatted_yaml = yamllib.dump(yaml_obj, Dumper=yamllib.RoundTripDumper)
    save_file_to_gerrit(rest, formatted_yaml, project, branch, file_path)
    print('Begin to save file to {}'.format(output_path))
    if output_path:
        with open(output_path, 'w') as f:
            f.write(formatted_yaml)


if __name__ == '__main__':
    fire.Fire(save_to_gerrit)
