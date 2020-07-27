import os
import re
import fire
import fnmatch


def classiy_objs(obj_list, typ_key):
    new_dict = {}
    for obj in obj_list:
        if typ_key in obj:
            typ_val = obj[typ_key]
            if typ_val not in new_dict:
                new_dict[typ_val] = []
            obj.pop(typ_key, None)
            new_dict[typ_val].append(obj)
        else:
            print "### Warn, obj:%s do not have key:%s" % (obj, typ_key)
    return new_dict


def dict_to_file(param_dict, param_path=''):
    if not param_path:
        wkdir = os.environ.get('WORKSPACE')
        if not wkdir:
            wkdir = os.getcwd()
        param_path = os.path.join(wkdir, 'parameters')
    content = ""
    for k, v in param_dict.items():
        content = content + "\n" + '%s=%s' % (k, v)
    content = content + "\n"
    with open(param_path, 'w') as fi:
        fi.write(content)


def get_sub_dirs(dir_path=os.getcwd(), regex=''):
    dirctories = [
        x
        for x in os.listdir(dir_path)
        if os.path.isdir(os.path.join(dir_path, x))]
    matched_dirs = []
    if regex:
        for dirctor in dirctories:
            m = re.match(regex, dirctor)
            if m:
                matched_dirs.append(dirctor)
        return matched_dirs
    return dirctories


def get_sub_files(dir_path=os.getcwd(), regex=''):
    files = [
        x
        for x in os.listdir(dir_path)
        if os.path.isfile(os.path.join(dir_path, x))]
    matched_files = []
    if regex:
        for file_name in files:
            m = re.match(regex, file_name)
            if m:
                matched_files.append(file_name)
        return matched_files
    return files


def find_files(file_path, regex_str='*', path_regex=''):
    matches = []
    for root, dirnames, filenames in os.walk(file_path):
        for filename in fnmatch.filter(filenames, regex_str):
            if path_regex in root:
                matches.append(os.path.join(root, filename))
    return matches


def find_files_by_regex(file_path, regex_str='*', path_regex=''):
    matches = []
    for root, dirnames, filenames in os.walk(file_path):
        for filename in filenames:
            if re.match(regex_str, filename):
                if path_regex in root:
                    matches.append(os.path.join(root, filename))
    return matches


def get_file_content(file_path):
    with open(file_path, 'r') as fr:
        return fr.read()


if __name__ == '__main__':
    fire.Fire()
