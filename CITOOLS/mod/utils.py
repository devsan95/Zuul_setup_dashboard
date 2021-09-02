import os
import re
import git
import fire
import shutil
import fnmatch
import traceback
import jenkins
import jenkinsapi.jenkins


INTEGRATION_URL = 'ssh://gerrit.ext.net.nokia.com:29418/MN/5G/COMMON/integration'
JENKINS_URL = 'http://production-5g.cb.scm.nsn-rdnet.net:80'


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
            print('### Warn, obj:{0} do not have key:{1}'.format(obj, typ_key))
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


def push_base_tag(base_pkg, branch=''):
    integration_dir = os.path.join(os.getcwd(), 'Integration_for_tags')
    if os.path.exists(integration_dir):
        g = git.Git(integration_dir)
        if g.remote('get-url', 'origin') == INTEGRATION_URL:
            g.fetch('--tags')
        else:
            shutil.rmtree(integration_dir)
    else:
        git.Repo.clone_from(INTEGRATION_URL, integration_dir)
    g = git.Git(integration_dir)
    if branch:
        g.fetch('origin', branch)
    g.checkout(base_pkg)
    push_merged_change(integration_dir, base_pkg, branch=branch)


def push_merged_change(integration_dir, base_pkg, branch=''):
    if not branch:
        branch = get_integration_branch(integration_dir)
    try:
        print('Base tag: {} add to gerrit'.format(base_pkg))
        g = git.Git(integration_dir)
        g.push('origin', '{}:refs/for/{}%merged'.format(base_pkg, branch))
    except Exception:
        traceback.print_exc()
        print('Tag {} may already exists'.format(base_pkg))
        print('Please ignore above error, \
               it will not cause the job build failed! \
               The build is moving on....')


def get_integration_branch(work_dir):
    g_repo = git.Git(work_dir)
    branch_data = g_repo.branch('--contains', 'HEAD', '-a')
    for line in branch_data.splitlines():
        line_str = line.strip()
        if line_str == 'master' or 'rel/' in line_str:
            return re.sub('.*/rel', 'rel', line_str)
    return ''


def get_jenkins_obj_from_nginx(jenkins_url=JENKINS_URL,
                               username=None, password=None,
                               timeout='', ssl_verify=None):
    jenkins_server = jenkins.Jenkins(jenkins_url)
    real_jenkins_url = jenkins_server.get_jobs()[0]['url'].split('/job/')[0]
    print(real_jenkins_url)
    if username and password:
        return jenkins.Jenkins(real_jenkins_url, username=username, password=password)
    if timeout:
        return jenkinsapi.jenkins.Jenkins(real_jenkins_url, timeout=timeout, ssl_verify=ssl_verify)
    return jenkins.Jenkins(real_jenkins_url)


if __name__ == '__main__':
    fire.Fire()
