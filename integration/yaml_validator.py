#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-


import fire
import re
import os
import yaml
import json
from create_ticket import check_graph_cycling, load_structure, create_graph
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from api import gerrit_rest

EXCEPTION_LIST = []


def traverse(path):
    fs = os.listdir(path)
    yaml_list = []
    for f in fs:
        tmp_path = os.path.join(path, f)
        if os.path.isdir(tmp_path):
            if f == "tests":
                tmp_fs = os.listdir(tmp_path)
                for t_file in tmp_fs:
                    file_path = os.path.join(tmp_path, t_file)
                    yaml_list.append(file_path)
        elif os.path.isfile(tmp_path):
            if re.match(r".*\.yaml$", f):
                yaml_list.append(tmp_path)
    if yaml_list:
        return yaml_list
    else:
        raise Exception("[Error] no yaml file existed to validate!")


def validate_file_config(yaml_file):
    with open(yaml_file, 'r') as stream:
        try:
            return yaml.load(stream)
        except yaml.YAMLError as exception:
            EXCEPTION_LIST.append("Yaml file {} validated failed and fail reason is: {}".format(yaml_file, exception.message))


def validate_file(file_path, schema):
    structure_obj = load_structure(file_path)
    json_schema = json.load(open(schema))
    try:
        validate(structure_obj, json_schema)
        graph_obj = create_graph(structure_obj)[3]
        check_graph_cycling(graph_obj)
    except (ValidationError, Exception) as e:
        EXCEPTION_LIST.append("Yaml file {} validated failed and fail reason is: {}".format(file_path, e.message))
    else:
        print("[Info] Validate yaml file: {} passed".format(file_path))


def main(yaml_path, schema_path, gerrit_info_path=None, change_no=None, check_all=False):
    if check_all:
        yaml_list = traverse(yaml_path)
    else:
        yaml_list = []
        config_yaml_list = []
        rest = gerrit_rest.init_from_yaml(gerrit_info_path)
        flist = rest.get_file_list(change_no)
        for f in flist:
            if ".yaml" in f and "/" not in f:
                yaml_list.append(os.path.join(yaml_path, f))
            if re.match(r"config/.*\.yaml", f):
                config_yaml_list.append(os.path.join(yaml_path, f))
    for yaml_file in yaml_list:
        if os.path.exists(yaml_file):
            validate_file(yaml_file, schema_path)
    for yaml_file in config_yaml_list:
        print("[Info] Starting validate yaml file: {}.".format(yaml_file))
        validate_file_config(yaml_file)

    if EXCEPTION_LIST:
        raise Exception("[Error] Yaml validated failed, reasons as below: {}".format(EXCEPTION_LIST))
    else:
        print("[Info] validation succeed!")


if __name__ == '__main__':
    fire.Fire(main)
