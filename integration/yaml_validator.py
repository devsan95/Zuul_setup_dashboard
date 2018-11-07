#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-


import fire
import re
import os
import json
from create_ticket import check_graph_cycling, load_structure, create_graph
from jsonschema import validate
from jsonschema.exceptions import ValidationError


def traverse(path):
    fs = os.listdir(path)
    yaml_list = []
    for f in fs:
        tmp_path = os.path.join(path, f)
        if os.path.isdir(tmp_path):
            if f == "tests":
                tmp_fs = os.listdir(tmp_path)
                for file in tmp_fs:
                    file_path = os.path.join(tmp_path, file)
                    yaml_list.append(file_path)
        elif os.path.isfile(tmp_path):
            if re.match(r".*\.yaml$", f):
                yaml_list.append(tmp_path)
    if yaml_list:
        return yaml_list
    else:
        raise Exception("[Error] no yaml file existed to validate!")


def main(yaml_path, schema_path):
    yaml_list = traverse(yaml_path)
    exception_list = []
    for yaml_file in yaml_list:
        structure_obj = load_structure(yaml_file)
        json_schema = json.load(open(schema_path))
        try:
            validate(structure_obj, json_schema)
            graph_obj = create_graph(structure_obj)[3]
            check_graph_cycling(graph_obj)
        except (ValidationError, Exception) as e:
            exception_list.append("Yaml file {} validated failed and fail reason is: {}".format(yaml_file, e.message))
        else:
            print("[Info] Validate yaml file: {} passed".format(yaml_file))
    if exception_list:
        raise Exception("[Error] Yaml validated failed, reasons as below: {}".format(exception_list))
    else:
        print("[Info] validation suceed!")


if __name__ == '__main__':
    fire.Fire(main)
