import fire

from mod import integration_repo

INTEGRTION_URL = 'ssh://gerrit.ext.net.nokia.com:29418/MN/5G/COMMON/integration'


def init_integration(base_pkg):
    int_repo = integration_repo.INTEGRATION_REPO(INTEGRTION_URL, base_pkg)
    int_repo.get_dep_files()
    return int_repo


def get_comp_hash(int_repo, comp_name):
    version_dict = int_repo.get_version_for_comp(comp_name)
    return version_dict['repo_ver']


if __name__ == '__main__':
    fire.Fire()
