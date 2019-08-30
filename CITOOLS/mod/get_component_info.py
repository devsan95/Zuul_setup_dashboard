import os
import re
import git
import fire
import logging
import traceback

from mod import integration_repo

logging.basicConfig(level=logging.INFO)
INTEGRTION_URL = 'ssh://gerrit.ext.net.nokia.com:29418/MN/5G/COMMON/integration'


def init_integration(base_pkg):
    integration_dir = os.path.join(
        os.getcwd(), 'Integration_{}'.format(base_pkg))
    int_repo = integration_repo.INTEGRATION_REPO(
        INTEGRTION_URL, base_pkg, work_dir=integration_dir)
    int_repo.get_dep_files()
    int_repo.gen_dep_all()
    try:
        print('Base tag: {} add to gerrit'.format(base_pkg))
        g = git.Git(integration_dir)
        g.push('origin', '{}:refs/for/master%merged'.format(base_pkg))
    except Exception:
        traceback.print_exc()
    return int_repo


def find_bb_target(comp_name, dep_dict):
    if comp_name in dep_dict:
        up_comp = dep_dict[comp_name]
        if up_comp.startswith('integration-'):
            return up_comp
        else:
            return find_bb_target(up_comp, dep_dict)
    return ''


def get_comp_hash(int_repo, comp_name):
    dep_all_file = os.path.join(int_repo.work_dir, 'build/dep_all', 'all.dep')
    regex_deps = r'"([^"]+)" -> "([^"]+)"'
    # regex_dep_file = r'dep_file:\s*(\S+)'
    # int_bb_target = ''
    dep_dict = dict()
    with open(dep_all_file, 'r') as fr:
        content = fr.read()
        for line in content.splitlines():
            logging.debug('line is : %s', line)
            m_d = re.match(regex_deps, line)
            if m_d:
                up_comp = m_d.group(1)
                down_comp = m_d.group(2)
                dep_dict[down_comp] = up_comp
    platform = find_bb_target(comp_name, dep_dict).split('integration-')[-1]
    logging.info('Get %s version on %s', comp_name, platform)
    version_dict = int_repo.get_version_for_comp(comp_name, platform=platform)
    return version_dict['repo_ver']


if __name__ == '__main__':
    fire.Fire()
