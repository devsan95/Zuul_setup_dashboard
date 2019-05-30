#! /usr/bin/env python2.7
# -*- coding:utf8 -*-
import re
import fire
import urllib3
from api import gerrit_rest
from datetime import datetime
from submodule_handle import get_topic_from_commit_message


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_platform(commit_message):
    platform = ""
    m = re.search(r"Platform ID: \<([^\>]*)\>", commit_message)
    platform = m.group(1)
    print("[Info] Platform is {}".format(platform))
    return platform


def parse_file_name_by_stream_list(stream_list, commit_message):
    print("[Info] Parsing platform ID from original commit message...")
    platform = get_platform(commit_message)
    print("[Info] Parsing topic from original commit message...")
    topic = get_topic_from_commit_message(commit_message)
    file_list = []
    for stream in stream_list:
        file_path = "{}/{}/{}.inte_tmp".format(platform, stream, topic)
        file_list.append(file_path)
    return file_list


def add_stream(change_number, stream_list, rest, commit_message):
    need_publish = False
    file_list = parse_file_name_by_stream_list(stream_list, commit_message)
    current_file_list = rest.get_file_list(change_number)
    for file_path in file_list:
        if file_path not in current_file_list:
            print("[Info] {} is going to be added into change {}".format(file_path, change_number))
            rest.add_file_to_change(change_number, file_path, datetime.utcnow().strftime('%Y%m%d%H%M%S'))
            need_publish = True
    return need_publish


def remove_stream(change_number, stream_list, rest, commit_message):
    need_publish = False
    file_list = parse_file_name_by_stream_list(stream_list, commit_message)
    current_file_list = rest.get_file_list(change_number)
    if file_list:
        for file_path in file_list:
            if file_path in current_file_list:
                print("[Info] File {} is going to be removed from change {}".format(file_path, change_number))
                rest.restore_file_to_change(change_number, file_path)
                need_publish = True
    return need_publish


def set_stream(change_number, stream_list, rest, commit_message):
    need_publish = False
    current_file_list = rest.get_file_list(change_number)
    if current_file_list:
        for current_file in current_file_list:
            print("[Info] The files in change {} is: {}".format(change_number, current_file))
            if len(current_file.split('/', 2)) > 1:
                stream = current_file.split('/', 2)[1]
            else:
                continue
            if stream != "default" and current_file != "/COMMIT_MSG":
                print("[Info] File {} is going to be removed from the change {}".format(current_file, change_number))
                rest.restore_file_to_change(change_number, current_file)
                need_publish_remove = True
    if not need_publish_remove:
        print("[Info] No need to remove files from the original file list, goint to add new stream")
    if stream_list:
        need_publish_add = add_stream(change_number, stream_list, rest, commit_message)
    need_publish = need_publish_remove or need_publish_add
    return need_publish


def main(change_number, action, stream_number, gerrit_info_path, auto_reexperiment=True):
    if not change_number:
        print "[Error] Please input change_number!"
        raise ValueError
    if not action:
        print "[Error] Please input action you want to perform!"
        raise ValueError
    if not stream_number:
        print "[Error] Please input stream_number!"
        raise ValueError

    stream_number = str(stream_number)
    stream_number.strip()
    if ',' in stream_number:
        stream_list = stream_number.split(",")
    if ';' in stream_number:
        stream_list = stream_number.split(";")
    if ',' not in stream_number and ';' not in stream_number:
        stream_list = stream_number.split()
    stream_re = re.compile(r'^\d+\.\d+$')
    for stream in stream_list:
        if not stream_re.match(stream):
            print('[Error] {} is not stream number, please input stream number only!'.format(stream))

    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    commit_message = rest.get_commit(change_number)['message']

    need_publish = False
    try:
        rest.delete_edit(change_number)
    except Exception as e:
        print('Delete edit failed, reason:')
        print(str(e))

    if action == "add":
        print('[Info] {} are going to be added to build knife package!'.format(stream_number))
        need_publish = add_stream(change_number, stream_list, rest, commit_message)
    elif action == "remove":
        print('[Info] {} are going to be removed from knife build stream list!'.format(stream_number))
        need_publish = remove_stream(change_number, stream_list, rest, commit_message)
    elif action == "set":
        print('[Info] {} are going to be set as knife build stream list!'.format(stream_number))
        need_publish = set_stream(change_number, stream_list, rest, commit_message)
    else:
        print('[Error] Invalid action!')
    if need_publish:
        print("[Info] Submitting change to gerrit")
        rest.publish_edit(change_number)
    if auto_reexperiment:
        print("[Info] Reply reexperiment in gerrit change")
        rest.review_ticket(change_number, 'reexperiment')


if __name__ == '__main__':
    fire.Fire(main)
