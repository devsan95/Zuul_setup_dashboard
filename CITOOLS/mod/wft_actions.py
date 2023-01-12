import configparser
import json
import os
import re
import requests
from api import config
from api import log_api
from api import wft_api
from datetime import datetime

WFT_CONFIG_FILE = os.path.join(config.get_config_path(), 'properties/wft.properties')
WFT_CONFIG = configparser.ConfigParser()
WFT_CONFIG.read(WFT_CONFIG_FILE)
WFT_URL = WFT_CONFIG.get('wft', 'url')
WFT_KEY = WFT_CONFIG.get('wft', 'key')
WFT_API_URL = "{}:8091".format(WFT_URL)
log = log_api.get_console_logger("WFT actions")
WFTAUTH = wft_api.WftAuth(WFT_KEY)


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
        wft = wft_api.WftBuildQuery(WFTAUTH)
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
        status = builddetail.tree.get('state')
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
                'status': status,
                'subbuilds': subbuilds}

    @staticmethod
    def get_next_version(version, sub_version=None, int_method=None):
        integration_table = {'PSINT': '9000', 'RCPINT': '9100', 'FEINT': '9200', 'NIDDINT': '9501'}
        # eg, sub_version is "201221" in SBTS00_ECL_SACK_BASE_9000_201221_000008
        if 'SBTS' in version:
            # change int method
            [prod_name, bti, major_version, minor_version] = version.rsplit('_', 3)
            # SBTS Logic
            if sub_version:
                short_version = str(sub_version)
            else:
                short_version = datetime.strftime(datetime.now(), '%y%m%d')
            release_id = (int(minor_version) + 1) if short_version == major_version else 1
            new_bti = integration_table[int_method] if (int_method and int_method in integration_table) else bti
            new_version = "{0}_{1}_{2}_{3:06d}".format(prod_name, new_bti, short_version, release_id)
            # log.info("New build increment version: {}".format(new_version))
            return new_version
        else:
            # vDU/vCU logic
            if '-' in version:
                [base_name, increase_number] = version.split('-', 1)
                return "{}-{}".format(base_name, int(increase_number) + 1)
            else:
                [prod_name, build_name] = version.split('_', 1)
                [bid, build_number] = build_name.split('.', 1)
                if not int_method:
                    bid = 0
                elif int_method in integration_table:
                    bid = integration_table[int_method]
                return "{prod_name}_{bid}.{build_number}-1".format(prod_name=prod_name,
                                                                   bid=bid,
                                                                   build_number=build_number)

    @staticmethod
    def set_note(version, note):
        """
        WFT API link: https://wft.int.net.nokia.com/api/index.html#/Builds/patch_api_v1__project___component__builds__version___format_
        parameters:
            version: baseline version in WFT
            note: note string which need to be added in baseline
        return: None
        """
        build_detail = WFTUtils.get_build_detail(version)
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        json_str = {"build": {"note": note}}
        json_str.update(WFTAUTH.get_auth())
        request_url = 'https://wft.int.net.nokia.com:8091/api/v1/{project}/{component}/builds/{version}.json'.format(
            project=build_detail['project'],
            component=build_detail['component'],
            version=version
        )
        response = requests.patch(
            request_url,
            headers=headers,
            json=json_str
        )
        if not response.ok:
            raise Exception('error {}, content: {}'.format(response.status_code, response.content))


class BuildIncrement(object):
    '''
    parameters:
        wft_branch: wft branch of current builds, used to get next build
        base_build: base build of increment, like SBTS00_ENB_9999_201222_000007, SBTS00_ECL_SACK_BASE_9000_201221_000008
                    if not set, get the latest build based on wft_branch
        changed: python dictionary, format like: {"Common:RCPvDU_oam": {"version": "RCPvDU_oam-2.23.0"}}
    '''

    def __init__(self, wft_branch, changed={}, base_build=None, inherit_map_obj=None, type_filter=''):
        self.wft_branch = wft_branch
        self.base_build = base_build
        self.changed = changed
        self.inherit_map_obj = inherit_map_obj
        self.type_filter = type_filter
        if type_filter != 'in_parent':
            inherit_map_obj.get_all_inherit_dict()

    def get_diff(self, current, updated):
        diff_list = list()
        if (not updated):
            return diff_list
        if self.type_filter != 'in_build':
            for comp_key in updated:
                self.inherit_map_obj.get_list_in_parent_from_builds(comp_key)
        for c in current:
            project = c.get('project')
            component = c.get('component')
            version = c.text
            comp_key = "{}:{}".format(project, component)
            updated_version = updated.get(comp_key, {}).get('version')
            if comp_key in updated and version != updated_version:
                if not self.inherit_map_obj.is_in_inherit_sub(comp_key, type_filter=self.type_filter):
                    log.info('Component {0} need update version: {1} -> {2}'.format(comp_key, version, updated_version))
                    diff = dict()
                    diff["version"] = updated_version
                    diff["project"] = project
                    diff["component"] = component
                    diff_list.append(diff)
        log.debug("ENV change list: {}".format(diff_list))
        return diff_list

    def send_inc_request(self, latest_build, psint_cycle=None):
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        current_version = latest_build["baseline"]
        log.info("Current latest version is: {}".format(current_version))
        base_details = WFTUtils.get_build_detail(self.base_build)
        current_detail = WFTUtils.get_build_detail(current_version)
        new_version = WFTUtils.get_next_version(current_version, psint_cycle)
        build_configurations = wft_api.WftBaselineConfigurations.get_baseline_configurations(
            project=base_details["project"],
            component=base_details["component"],
            version=current_version,
            wftauth=WFTAUTH
        )
        diff_list = self.get_diff(base_details["subbuilds"], self.changed)
        inc_data = {
            "parent_version": base_details["baseline"],
            "parent_project": base_details["project"],
            "parent_component": base_details["component"],
            "branch": current_detail["branch"],
            "branch_for": current_detail["branch_for"],
            "repository_url": current_detail["repository_url"],
            "increment": diff_list,
            # This is set to true because we want to change the status into freeze by our selves
            # after the unification, the original state machine cannot process if the submodule is not released.
            # we decided to switch the status by our self
            "check_before_freeze": "true",
            "xml_releasenote_id": build_configurations.get_xml_releasenote_id(),
            "release_setting_id": build_configurations.get_release_setting_id(),
            "release_note_template_id": build_configurations.get_release_note_template_id(),
            "release_note_template_version_id": build_configurations.get_release_note_template_version_id()
        }
        inc_service = "{}/api/v1/{}/{}/builds/{}/increment.json".format(
            WFT_API_URL, current_detail["project"], current_detail["component"], new_version
        )
        log.info("Build increment url: {}".format(inc_service))
        log.info("inc data: %s", inc_data)
        inc_data.update({"access_key": WFT_KEY})
        response = requests.post(
            inc_service,
            headers=headers,
            data=json.dumps(inc_data),
            verify=True
        )
        if not response.ok:
            raise Exception("Failed to increment new {0}:{1} in WFT; error message was: {2}".format(current_detail["project"], current_detail["component"], response.text))
        log.info("New build {} created in WFT".format(new_version))

        return new_version

    def filter_candidate_builds(self, candidate_builds, name_regex):
        for candidate_build in candidate_builds:
            if re.match(name_regex, candidate_build['baseline']):
                return candidate_build
        raise Exception('Not find matched regex {} in {}'.format(name_regex, candidate_builds))

    def int_increment(self, repository={}, note=""):
        # Determine the next build name
        base_build_detail = WFTUtils.get_build_detail(self.base_build)
        base_build_project = base_build_detail["project"]
        base_build_component = base_build_detail["component"]
        build_configurations = wft_api.WftBaselineConfigurations.get_baseline_configurations(
            project=base_build_project,
            component=base_build_component,
            version=self.base_build,
            wftauth=WFTAUTH
        )
        if "_" in self.wft_branch:
            [prod_name, increase_method] = self.wft_branch.split("_", 1)
        else:
            raise Exception("Your branch should be XXXX_XXINT but {}".format(self.wft_branch))
        new_version = WFTUtils.get_next_version(version=self.base_build, int_method=increase_method)
        # Will update the increment number if the target build is existed
        all_existed_builds = WFTUtils.get_branch_builds(
            self.wft_branch,
            project=base_build_project,
            component=base_build_component)
        for build in all_existed_builds:
            if bool(re.search(r"v[DC]UCNF[0-9R]*", prod_name)):
                [new_version_base_name, new_version_increase_number] = new_version.split("-", 1)
                if new_version_base_name in build['baseline'] and "-" in build['baseline'] and \
                        int(build['baseline'].split("-", 1)[1]) >= int(new_version_increase_number):
                    new_version = WFTUtils.get_next_version(build['baseline'])
                    log.info("There is {}-{} existed, use {} instead".format(new_version_base_name,
                                                                             new_version_increase_number,
                                                                             new_version))
            else:
                if new_version == build['baseline']:
                    pre_version = new_version
                    new_version = WFTUtils.get_next_version(new_version)
                    log.info("There is {} existed, use {} instead".format(pre_version, new_version))
        # create current_build
        current_build = wft_api.WftObjBuild()
        current_build.set_project(base_build_project)
        current_build.set_component(base_build_component)
        current_build.set_build(self.base_build)
        current_build.set_credential(WFTAUTH)
        # Start to increment
        incremented_build = current_build.increment(new_version,
                                                    self.wft_branch,
                                                    self.get_diff(base_build_detail["subbuilds"], self.changed),
                                                    build_configurations,
                                                    repository,
                                                    note)
        print("Successfully create a build: {} , refer: {}".format(incremented_build.build,
                                                                   incremented_build.get_url()))
        incremented_build.frozen()
        return incremented_build.build, incremented_build.get_url()

    def run(self, psint_cycle=None, name_regex='.*'):
        base_build_project = None
        base_build_component = None
        if self.base_build:
            base_build_detail = WFTUtils.get_build_detail(self.base_build)
            base_build_project = base_build_detail['project']
            base_build_component = base_build_detail['component']
        candidate_builds = WFTUtils.get_branch_builds(self.wft_branch, project=base_build_project, component=base_build_component)
        latest_build = self.filter_candidate_builds(candidate_builds, name_regex)
        if not self.base_build:
            self.base_build = latest_build['baseline']
        return self.send_inc_request(latest_build, psint_cycle)
