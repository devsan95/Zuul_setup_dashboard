import fire
import re
import requests
from xml.etree import ElementTree
from scm_tools.wft.api import WftAPI
from scm_tools.wft.releasenote import Releasenote
from api import mysql_api
from api import log_api


WFT = WftAPI()
LOG = log_api.get_console_logger(name='PS')


class PSTrigger(object):
    '''
    This class is:
    1. Update PS topic based on PS release

    PS version type:
        IB011_PS_REL_2020_09_0012
        MB_PS_REL_2020_09_0011
        FB_PS_REL_2020_02_0078
    '''

    def __init__(self, topic_id, sql_yaml, baseline='', output='rebase_env.prop'):
        self.topic_id = topic_id
        self.output_file = output
        self.skytrace_handler = self.load_sql_handler(sql_yaml)
        self.topic_detail = []
        self.ps_version = baseline

    def load_sql_handler(self, sql_yaml, server_name='skytrack', db_name='skytrack'):
        connector = mysql_api.init_from_yaml(yaml_path=sql_yaml, server_name=server_name)
        connector.init_database(db_name)
        return connector

    def load_ps_integration(self):
        LOG.info('Get PS integration from SKYTRACK for issue {}'.format(self.topic_id))
        fields = ['issue_key', 'summary', 'integration_mode', 'is_update']
        sql = "SELECT {0} FROM t_issue WHERE " \
            "status = 'Open' AND issue_key = '{1}'".format(', '.join(fields), self.topic_id)
        topics = self.skytrace_handler.executor(sql, output=True)
        self.topic_detail = topics[0]
        self.check_version()

    def load_latest_PS_baseline(self):
        if self.ps_version:
            return

        version = re.search(r'\w+_REL_\d{4}_\d{2}', self.topic_detail[1]).group()
        ps_filter = "/ext/builds/?custom_filter[baseline_regexp]=1" \
                    "&custom_filter[baseline]=^{0}" \
                    "&custom_filter[sorting_field]=date" \
                    "&custom_filter[sorting_direction]=desc" \
                    "&(custom_filter[state][]=pre_released|" \
                    "custom_filter[state][]=released|" \
                    "custom_filter[state][]=released_with_restrictions)" \
                    "&custom_filter[items]=5".format(version)
        url = WFT.url + ps_filter
        LOG.info('Get Latest PS releases from WFT by url: \n\t{}'.format(url))
        r = requests.get(url, params={'access_key': WFT.key}, verify=False)
        r.raise_for_status()
        xmlroot = ElementTree.fromstring(r.text.encode('utf-8'))
        self.ps_version = [build.findtext('baseline') for build in xmlroot.findall('build')][0]

    def dump_output(self):
        version = re.search(r'\w+_REL_\d{4}_\d{2}_\d+', self.topic_detail[1]).group()
        if version == self.ps_version:
            LOG.info('No action needed, PS version already updated to {} for {}'.format(version, self.topic_detail[0]))
            return
        LOG.info("Will Update topic {2} PS version {0} -> {1}".format(version, self.ps_version, self.topic_detail[0]))
        root_change = self._get_cpi_root_change()
        env_changes = self._format_env_changes(self.ps_version)
        fdata = {
            'root_change': root_change,
            'env_change': env_changes
        }
        self._dump_file(self.output_file, **fdata)

    def run(self):
        self.load_ps_integration()
        self.load_latest_PS_baseline()
        self.dump_output()

    def check_version(self):
        version = re.search(r'\w+_REL_\d{4}_\d{2}_\d+', self.topic_detail[1])
        if not version:
            raise Exception("PS version not in format.\n\tTopic:{}\n\tSummary:{}".format(
                            self.topic_id, self.topic_detail[1]))

    def _format_env_changes(self, ps_version):
        ps_sub_builds = self._get_ps_sub_builds(ps_version)
        env_change = \
            "ENV_PS_REL={PS_REL}\\nENV_GLOBAL_ENV={GLOBAL_ENV}\\nENV_PS_LFS_REL={PS_LFS_REL}".format(
                PS_REL=ps_version,
                GLOBAL_ENV=ps_sub_builds['GLOBAL_ENV'],
                PS_LFS_REL=ps_sub_builds['PS_LFS_REL']
            )
        return env_change

    def _dump_file(self, fname, **content):
        fdata = ["{}={}".format(key, value) for key, value in content.items()]
        with open(fname, 'w+') as f:
            f.write('\n'.join(fdata))

    def _get_cpi_root_change(self):
        fields = ["id", "`change`", "issue_key"]
        issue_key = self.topic_detail[0]
        sql = "SELECT {0} FROM t_commit_component WHERE issue_key = '{1}' " \
              "AND component = 'root_monitor'".format(', '.join(fields), issue_key)
        LOG.info("cpi_root_change sql: {}".format(sql))
        search_result = self.skytrace_handler.executor(sql=sql, output=True)
        return search_result[0][1]

    def _get_ps_sub_builds(self, ps_version):
        releasenote = Releasenote.get(ps_version)
        baselines = releasenote.get_baselines()
        global_env = []
        ps_lfs_rel = []
        for item in baselines:
            if item['name'] == 'GLOBAL_ENV':
                global_env.append(item['version'])
                global_env.sort()
            if item['name'] == 'PS_LFS_REL':
                ps_lfs_rel.append(item['version'])
                ps_lfs_rel.sort()
        LOG.info('Get {0}, {1} from {2}'.format(global_env[0], ps_lfs_rel[0], ps_version))
        return {'GLOBAL_ENV': global_env[0], 'PS_LFS_REL': ps_lfs_rel[0]}


if __name__ == '__main__':
    fire.Fire(PSTrigger)
