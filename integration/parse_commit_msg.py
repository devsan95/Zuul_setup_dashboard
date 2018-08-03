#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import traceback
import sys
import argparse
import git
import re
import json


def _parse_args():
    parser = argparse.ArgumentParser(description='Parse commit msg')
    parser.add_argument('repo_path', type=str,
                        help='path to repo')
    parser.add_argument('change_id', type=str,
                        help='change_id')
    args = parser.parse_args()
    return vars(args)


def _main(repo_path, change_id):
    repo = git.Repo(repo_path)
    msg = repo.head.commit.message
    json_re = re.compile(r'Tickets-List: ({.*})')
    result_list = json_re.findall(msg)
    json_text = result_list[0]
    json_obj = json.loads(json_text)
    json_obj['manager'] = change_id
    print(json.dumps(json_obj))


if __name__ == '__main__':
    try:
        param = _parse_args()
        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
