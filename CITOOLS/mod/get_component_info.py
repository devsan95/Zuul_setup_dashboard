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


def get_comp_hash(int_repo, comp_name):
    dep_all_file = os.path.join(int_repo.work_dir, 'build/dep_all', 'all.dep')
    regex_comps = r'" \[label="([^\\]+)\\n:([^\\]+)\\n([^\\]+)"\]'
    regex_dep_file = r'dep_file:\s*(\S+)'
    int_bb_target = ''
    comp_dict = dict()
    with open(dep_all_file, 'r') as fr:
        for line in fr.read().splitlines():
            logging.debug('line is : %s', line)

            m_f = re.match(regex_dep_file, line)
            if m_f:
                dep_file = m_f.group(1)
                int_bb_target = os.path.basename(dep_file).split('.dep')[0]
            m = re.search(regex_comps, line)
            if m:
                comp = m.group(1)
                comp_dict[comp] = int_bb_target
                if comp == comp_name:
                    break
    platform = comp_dict[comp_name].split('-')[-1] if comp_name in comp_dict else ''
    version_dict = int_repo.get_version_for_comp(comp_name, platform=platform)
    return version_dict['repo_ver']


if __name__ == '__main__':
    fire.Fire()
