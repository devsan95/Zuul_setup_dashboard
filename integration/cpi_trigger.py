import re
import fire
import requests
from xml.etree import ElementTree
from scm_tools.wft.api import WftAPI
from scm_tools.wft.releasenote import Releasenote


from api import mysql_api
from api import log_api

WFT = WftAPI()
LOG = log_api.get_console_logger(name='CPI')


def filter_mb_ps_from_wft():
    LOG.info('Get PS MB releases from WFT')
    ps_filter = "/ext/builds/?custom_filter[baseline_regexp]=1" \
                "&custom_filter[baseline]=^MB_PS_REL_" \
                "&custom_filter[sorting_field]=date" \
                "&custom_filter[sorting_direction]=desc" \
                "&(custom_filter[state][]=pre_released|" \
                "custom_filter[state][]=released|" \
                "custom_filter[state][]=released_with_restrictions&custom_filter[items]=50"
    url = WFT.url + ps_filter
    r = requests.get(url, params={'access_key': WFT.key}, verify=False)
    if r.status_code != 200:
        raise Exception('Failed to get PS MB releases from WFT')
    root = ElementTree.fromstring(r.text.encode('utf-8'))
    return [build.findtext('baseline') for build in root.findall('build')]


def get_on_going_cpi_topics(sql_yaml):
    LOG.info('Get on-going CPI in SKYTRACK')
    regex = re.compile(r'CPI Integration on master-(.*) Integration')
    mysql = mysql_api.init_from_yaml(yaml_path=sql_yaml, server_name='skytrack')
    mysql.init_database('skytrack')
    sql = "SELECT * FROM t_issue WHERE status = " \
          "'Open' AND summary LIKE '%CPI Integration on master%'"
    search_result = mysql.executor(sql, output=True)
    return {regex.match(topic[3]).group(1): topic[1] for topic in search_result}


def get_cpi_root_change(issue_key, sql_yaml):
    mysql = mysql_api.init_from_yaml(yaml_path=sql_yaml, server_name='skytrack')
    mysql.init_database('skytrack')
    sql = "SELECT * FROM t_commit_component WHERE issue_key = '{issue_key}' " \
          "AND component = 'root_monitor'".format(issue_key=issue_key)
    search_result = mysql.executor(sql=sql, output=True)
    return search_result[0][1]


def get_top_two_releases(releases):
    top_two_releases = list()
    major_version = 0
    for topic in releases:
        if not major_version:
            top_two_releases.append(topic)
            major_version = get_major_version(topic)
            continue
        topic_mv = get_major_version(topic)
        if topic_mv == major_version:
            continue
        if topic_mv == (major_version - 1):
            top_two_releases.append(topic)
            break
    return top_two_releases


def get_major_version(ps_version):
    mb_ps_regex = re.compile(r'MB_PS_REL_(\d+)_(\d+)*')
    version_match = mb_ps_regex.match(ps_version)
    return int("{0}{1}".format(version_match.group(1), version_match.group(2)))


def if_create(on_going_cpi_topics, mb_ps_releases, sql_yaml):
    root_change = {}
    if not on_going_cpi_topics:
        LOG.info('No on-going CPI topics, create CPI topic for {0}'.format(mb_ps_releases[0]))
        return {mb_ps_releases[0]: 'create'}, root_change
    cpi_topics = on_going_cpi_topics.keys()
    cpi_topics.sort(reverse=True)
    top_two_cpi_topic = get_top_two_releases(cpi_topics)
    LOG.info("Top two on going CPI topics:{0}".format(' '.join(top_two_cpi_topic)))
    top_two_mb_releases = get_top_two_releases(mb_ps_releases)
    LOG.info("Top two PS MB releases:{0}".format(' '.join(top_two_mb_releases)))
    results = {}
    for mb_release in top_two_mb_releases:
        for cpi_topic in top_two_cpi_topic:
            if get_major_version(mb_release) \
                    == get_major_version(cpi_topic):
                if mb_release > cpi_topic:
                    results[mb_release] = 'update'
                    root_change[mb_release] = get_cpi_root_change(on_going_cpi_topics[cpi_topic],
                                                                  sql_yaml=sql_yaml)
                else:
                    LOG.info('Current on going CPI: {0}'.format(cpi_topic))
                    LOG.info('Latest PS MB release {0}'.format(mb_release))
                    LOG.info('No need to update')
                break
            if get_major_version(mb_release) \
                    > get_major_version(cpi_topic):
                results[mb_release] = 'create'
                break
    return results, root_change


def get_ps_sub_builds(ps_version):
    releasenote = Releasenote.get(ps_version)
    baselines = releasenote.get_baselines()
    global_env = ''
    ps_lfs_rel = ''
    for item in baselines:
        if item['name'] == 'GLOBAL_ENV':
            global_env = item['version']
        if item['name'] == 'PS_LFS_REL':
            ps_lfs_rel = item['version']
    LOG.info('Get {0}, {1} from {2}'.format(global_env, ps_lfs_rel, ps_version))
    return {'GLOBAL_ENV': global_env, 'PS_LFS_REL': ps_lfs_rel}


def write_parameters(action, env_change, structure_file,
                     streams, promoted_user_id, integration_mode,
                     version_name, root_changes):
    file_name = "create_feature.pop" if action == 'create' else "rebase_env.pop"
    with open(file_name, 'w+') as parameters_file:
        parameters_file.write(
            """structure_file={structure_file}
env_change={env_change}
streams={streams}
PROMOTED_USER_ID={promoted_user_id}
integration_mode={integration_mode}
root_change={root_change}
version_name={version_name}""".format(
                structure_file=structure_file,
                env_change=env_change,
                streams=streams,
                promoted_user_id=promoted_user_id,
                integration_mode=integration_mode,
                root_change=root_changes[version_name] if version_name in root_changes else '',
                version_name=version_name
            )
        )


def cpi_topic_handler(cpi_topics, structure_file, streams,
                      promoted_user_id, integration_mode,
                      root_changes):
    for ps_version, action in cpi_topics.items():
        ps_sub_builds = get_ps_sub_builds(ps_version)
        env_change = \
            "ENV_PS_REL={PS_REL}\\nENV_GLOBAL_ENV={GLOBAL_ENV}\\nENV_PS_LFS_REL={PS_LFS_REL}".format(
                PS_REL=ps_version,
                GLOBAL_ENV=ps_sub_builds['GLOBAL_ENV'],
                PS_LFS_REL=ps_sub_builds['PS_LFS_REL']
            )
        LOG.info('Will {0} CPI topic for {1}'.format(action, ps_version))
        write_parameters(
            action=action,
            env_change=env_change,
            structure_file=structure_file,
            streams=streams,
            promoted_user_id=promoted_user_id,
            integration_mode=integration_mode,
            root_changes=root_changes,
            version_name=ps_version
        )


def run(structure_file, streams, promoted_user_id, integration_mode, sql_yaml, baseline=None):
    mb_releases = [baseline] if baseline else filter_mb_ps_from_wft()
    on_going_cpi_topics = get_on_going_cpi_topics(sql_yaml=sql_yaml)
    actions, root_changes = if_create(
        on_going_cpi_topics=on_going_cpi_topics,
        mb_ps_releases=mb_releases,
        sql_yaml=sql_yaml
    )
    if not actions:
        LOG.info('No action needed in this round')
    else:
        LOG.info('will take action for below versions:')
        LOG.info(actions)
    cpi_topic_handler(cpi_topics=actions, structure_file=structure_file,
                      streams=','.join([str(stream) for stream in streams]),
                      promoted_user_id=promoted_user_id, integration_mode=integration_mode,
                      root_changes=root_changes)


if __name__ == '__main__':
    fire.Fire(run)
