import json
import os
import requests
from api import log_api
from api import wft_api
from datetime import datetime

WFT_API_URL = os.environ['WFT_API_URL']
WFT_KEY = os.environ['WFT_KEY']
log = log_api.get_console_logger("WFT actions")


class WFTUtils(object):
    '''
    common method for Workflow tool
    '''
    @staticmethod
    def get_branch_builds(branch, project=None, component=None, limit=50):
        '''
        return build list, each build as a dictionary,
        include keys/fields: deliverer.title, branches_title, branch.title, baseline, version
        '''
        wftauth = wft_api.WftAuth(WFT_KEY)
        wft = wft_api.WftBuildQuery(wftauth)
        wft.set_sorting('created_at')
        wft.add_filter("branch.title", "eq", branch)
        if project:
            wft.add_filter("deliverer.project.full_path", "eq", project)
        if component:
            wft.add_filter("deliverer.title", "eq", component)
        wft.add_columns("branches_title")
        wft.set_result_number(limit)
        content = wft.query()
        builds = content['items']
        return builds

    @staticmethod
    def get_build_detail(version):
        builddetail = wft_api.WftBuild.get_build(version)
        baseline = builddetail.tree.get('baseline')
        project = builddetail.tree.find('./project').text
        component = builddetail.tree.find('./component').text
        repo_url = builddetail.tree.find('./repository_url').text
        branch = builddetail.tree.find("./branch").text
        branch_for = [bf.text for bf in builddetail.find_items("./branch_for/branch")]
        ecl_sack_base = builddetail.tree.find("./content/baseline/[@component='ECL_SACK_BASE']")
        ecl_sack_base = ecl_sack_base.text if (ecl_sack_base is not None) else ''
        subbuilds = builddetail.find_items("./content/baseline") + builddetail.find_items("peg_revisions/peg_revision")

        return {'project': project,
                'component': component,
                'baseline': baseline,
                'repository_url': repo_url,
                'branch': branch,
                'branch_for': branch_for,
                'ecl_sack_base': ecl_sack_base,
                'subbuilds': subbuilds}

    @staticmethod
    def get_next_version(version, sub_version=None):
        # eg, sub_version is "201221" in SBTS00_ECL_SACK_BASE_9000_201221_000008
        if sub_version:
            short_version = sub_version
        else:
            short_version = datetime.strftime(datetime.now(), '%y%m%d')
        units = version.rsplit('_', 2)
        release_id = (int(units[2]) + 1) if short_version == units[1] else 1
        new_version = "{0}_{1}_{2:06d}".format(units[0], short_version, release_id)
        log.info("New build increment version: {}".format(new_version))
        return new_version


class BuildIncrement(object):
    '''
    parameters:
        wft_branch: wft branch of current builds, used to get next build
        base_build: base build of increment, like SBTS00_ENB_9999_201222_000007, SBTS00_ECL_SACK_BASE_9000_201221_000008
                    if not set, get the latest build based on wft_branch
        changed: python dictionary, format like: {"Common:RCPvDU_oam": {"version": "RCPvDU_oam-2.23.0"}}
    '''
    INHERIT_COMP = ["PS:PS_LFS_REL", "Common:GLOBAL_ENV"]

    def __init__(self, wft_branch, changed={}, base_build=None):
        self.wft_branch = wft_branch
        self.base_build = base_build
        self.changed = changed

    def get_diff(self, current, updated):
        diff_list = list()
        if (not updated):
            return diff_list

        for c in current:
            project = c.get('project')
            component = c.get('component')
            version = c.text
            comp_key = "{}:{}".format(project, component)
            updated_version = updated.get(comp_key, {}).get('version')
            if (comp_key not in self.INHERIT_COMP) and (comp_key in updated) and version != updated_version:
                log.info('Component {0} need update version: {1} -> {2}'.format(comp_key, version, updated_version))
                diff = dict()
                diff["version"] = updated_version
                diff["project"] = project
                diff["component"] = component
                diff_list.append(diff)
        log.debug("ENV change list: {}".format(diff_list))
        return diff_list

    def send_inc_request(self, latest_build, psint_cycle=None):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        current_version = latest_build['baseline']
        log.info("Current latest version is: {}".format(current_version))
        base_details = WFTUtils.get_build_detail(self.base_build)
        current_detail = WFTUtils.get_build_detail(current_version)
        new_version = WFTUtils.get_next_version(current_version, psint_cycle)
        diff_list = self.get_diff(base_details['subbuilds'], self.changed)
        inc_data = {
            "parent_version": base_details['baseline'],
            "parent_project": base_details["project"],
            "parent_component": base_details["component"],
            "branch": current_detail['branch'],
            "branch_for": current_detail['branch_for'],
            "repository_url": current_detail['repository_url'],
            "increment": diff_list,
            "check_before_freeze": 'false'
        }
        inc_service = "{}/api/v1/{}/{}/builds/{}/increment.json".format(
            WFT_API_URL, current_detail['project'], current_detail['component'], new_version
        )
        log.info("Build increment url: {}".format(inc_service))
        log.info(inc_data)
        inc_data.update({"access_key": WFT_KEY})
        response = requests.post(
            inc_service,
            headers=headers,
            data=json.dumps(inc_data),
            verify=True
        )
        if not response.ok:
            log.error(response.text)
            raise Exception("Failed to increment new  {}:{} in WFT".format(current_detail['project'], current_detail['component']))
        log.info("New build {} created in WFT".format(new_version))

    def run(self, psint_cycle=None):
        base_build_project = None
        base_build_component = None
        if self.base_build:
            base_build_detail = WFTUtils.get_build_detail(self.base_build)
            base_build_project = base_build_detail['project']
            base_build_component = base_build_detail['component']
        latest_build = WFTUtils.get_branch_builds(self.wft_branch, project=base_build_project, component=base_build_component)[0]
        if not self.base_build:
            self.base_build = latest_build['baseline']

        self.send_inc_request(latest_build, psint_cycle)
