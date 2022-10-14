###############################################
# this is a script to increment skyrack build #
###############################################

import fire
import json
import re
from api import gerrit_rest
from mod import integration_change
from mod import utils
from mod import wft_actions


BRANCH_MAP = {'PS': 'PSINT', 'RCP': 'RCPINT', 'NIDD': 'NIDDINT', 'feature': 'FEINT'}
PRODUCTION_TYPES = ['SBTS', 'vDUCNF', 'vCUCNF']


def get_wft_int_branch(rest, change_id, baseline):
    int_change = integration_change.ManageChange(rest, change_id)
    topic_type = int_change.get_topic_type()
    intbranch_end = BRANCH_MAP.get(topic_type)
    if not intbranch_end:
        raise Exception('topic type {} not in map {}'.format(topic_type, BRANCH_MAP))
    product_type = re.sub(r'[0-9]*$', '', baseline.split('_')[0])
    if product_type not in PRODUCTION_TYPES:
        raise Exception('product type {} not in {}'.format(product_type, PRODUCTION_TYPES))
    return '{}_{}'.format(product_type, intbranch_end)


def get_changed_info(knife_change_file):
    changed_dict = dict()
    with open(knife_change_file, 'r') as fr:
        knife_data = json.load(fr)
        if 'yaml_changes' in knife_data['knife_request']:
            for yaml_change in knife_data['knife_request']['yaml_changes'].values():
                source_component = yaml_change['source_component']
                version = yaml_change['replace_version']
                commit = yaml_change['replace_commit']
                changed_dict[source_component] = {'version': version, 'commit': commit}
    return changed_dict


def run(property_file, change_id, gerrit_info_path, knife_change_file):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    data = utils.file_to_dict(property_file)
    baseline = data['BASELINE']
    revision = data['REVISION']
    branch = data['BRANCH']
    wft_branch = get_wft_int_branch(rest, change_id, baseline)
    increment_obj = wft_actions.BuildIncrement(wft_branch=wft_branch,
                                               changed=get_changed_info(knife_change_file),
                                               base_build=baseline,
                                               inherit_map_obj=None,
                                               type_filter='in_parent')
    wft_name, wft_link = increment_obj.int_increment(
        {"repository_url": "ssh://gerrit.ext.net.nokia.com:29418/MN/5G/COMMON/integration",
         "repository_branch": branch,
         "repository_revision": revision,
         "repository_type": "git"})
    rest.review_ticket(change_id, 'IntegrationBuild: {} - {}'.format(wft_name, wft_link))


if __name__ == '__main__':
    fire.Fire(run)
