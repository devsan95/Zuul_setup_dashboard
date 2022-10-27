###############################################
# this is a script to increment skyrack build #
###############################################

import fire
import json
import re
import time
from api import gerrit_rest
from mod import inherit_map
from mod import integration_change
from mod import utils
from mod import wft_actions
import skytrack_database_handler


BRANCH_MAP = {'PS': 'PSINT', 'RCP': 'RCPINT', 'NIDD': 'NIDDINT', 'feature': 'FEINT'}
PRODUCTION_TYPES = ['SBTS', 'vDUCNF', 'vCUCNF']


def get_wft_int_branch(topic_type, baseline):
    intbranch_end = 'FEINT'
    for key_name in BRANCH_MAP:
        if topic_type.startswith(key_name):
            intbranch_end = BRANCH_MAP.get(key_name)
    if not intbranch_end:
        raise Exception('topic type {} not in map {}'.format(topic_type, BRANCH_MAP))
    product_type = re.sub(r'[0-9]*$', '', baseline.split('_')[0])
    if product_type not in PRODUCTION_TYPES:
        raise Exception('product type {} not in {}'.format(product_type, PRODUCTION_TYPES))
    return '{}_{}'.format(product_type, intbranch_end)


def get_changed_info(knife_change_file):
    changed_dict = dict()
    yaml_changed_dict = dict()
    with open(knife_change_file, 'r') as fr:
        knife_data = json.load(fr)
        if 'knife_changes' in knife_data['knife_request']:
            changed_dict['knife_changes'] = knife_data['knife_request']['knife_changes'].values()
        if 'yaml_changes' in knife_data['knife_request']:
            changed_dict['yaml_changes'] = knife_data['knife_request']['yaml_changes'].values()
            for yaml_change in knife_data['knife_request']['yaml_changes'].values():
                source_component = yaml_change['source_component']
                version = yaml_change['replace_version']
                commit = yaml_change['replace_commit']
                yaml_changed_dict[source_component] = {'version': version, 'commit': commit}
    return changed_dict, yaml_changed_dict


def update_build_info(database_info_path, wft_name, wft_link, jira_key, stream):
    now_time = int(time.time())
    skytrack_database_handler.skytrack_detail_api(
        integration_name=jira_key,
        product='5G',
        package_name=wft_name,
        mini_branch=stream,
        type_name='Integration Build',
        status=0,
        link=wft_link,
        start_time=now_time,
        end_time=now_time
    )
    build_info_in_link = "<a href='{}'>{}</a>".format(wft_link, wft_name)
    skytrack_database_handler.update_events(
        database_info_path=database_info_path,
        integration_name=jira_key,
        description="{0} integration package created: {1}".format(stream, build_info_in_link)
    )


def run(property_file, change_id, gerrit_info_path, knife_change_file, database_info_path):
    rest = gerrit_rest.init_from_yaml(gerrit_info_path)
    data = utils.file_to_dict(property_file)
    baseline = data['BASELINE']
    revision = data['REVISION']
    branch = data['BRANCH']
    diff_note = 'Cotent Diff : {}'.format(data.get('DIFF_URL'))
    int_change = integration_change.ManageChange(rest, change_id)
    topic_type = int_change.get_topic_type()
    jira_id = int_change.get_jira_id()
    wft_branch = get_wft_int_branch(topic_type, baseline)
    changed_dict, yaml_changed_dict = get_changed_info(knife_change_file)
    diff_note = diff_note + "\n" + json.dumps(changed_dict, indent=4)
    inherit_map_obj = inherit_map.Inherit_Map(base_loads=[baseline])
    increment_obj = wft_actions.BuildIncrement(wft_branch=wft_branch,
                                               changed=yaml_changed_dict,
                                               base_build=baseline,
                                               inherit_map_obj=inherit_map_obj,
                                               type_filter='in_parent')
    wft_name, wft_link = increment_obj.int_increment(
        {"repository_url": "ssh://gerrit.ext.net.nokia.com:29418/MN/5G/COMMON/integration",
         "repository_branch": branch,
         "repository_revision": revision,
         "repository_type": "git"},
        note=diff_note)
    update_build_info(database_info_path, wft_name, wft_link, jira_id, baseline.split('_')[0])
    rest.review_ticket(change_id, 'IntegrationBuild: {} - {}'.format(wft_name, wft_link))


if __name__ == '__main__':
    fire.Fire(run)
