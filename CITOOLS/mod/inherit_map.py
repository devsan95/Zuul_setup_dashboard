import copy
import yaml
import yamlordereddictloader
from mod import wft_tools
from mod import env_changes
from mod import config_yaml


DEFAULT_STREAM_LIST = ['0.990', '0.400', '0.300']


class Inherit_Map(object):

    def __init__(self, base_loads=None, stream_list=None, extra_components=None):
        self.stream_list = stream_list
        self.base_loads = self.get_base_loads(base_loads)
        self.inherit_dict = {}
        self.inherit_comps = {}
        self.build_config_dict = {}
        self.extra_components = extra_components

    def get_base_loads(self, base_loads):
        if base_loads:
            wft_base_loads = []
            for base_load in base_loads:
                wft_base_loads.append(wft_tools.get_wft_release_name(base_load))
            return wft_base_loads
        elif not self.stream_list:
            self.stream_list = DEFAULT_STREAM_LIST
        return wft_tools.get_latest_build_load(self.stream_list, strip_prefix=False)[1]

    def get_all_inherit_list(self, component):
        if component not in self.inherit_comps:
            self.inherit_comps[component] = {}
            self.inherit_comps[component]['in_parent'] = self.get_list_in_parent_from_builds(component)
            self.inherit_comps[component]['in_build'] = self.get_list_in_build_from_builds(component)
        all_list = copy.copy(self.inherit_comps[component]['in_parent'])
        all_list.extend(self.inherit_comps[component]['in_build'])
        return all_list

    def get_inherit_list_in_parent(self, component):
        if component not in self.inherit_comps:
            self.inherit_comps[component] = {}
        if 'in_parent' not in self.inherit_comps[component]:
            self.inherit_comps[component]['in_parent'] = self.get_list_in_parent_from_builds(component)
        return self.inherit_comps[component]['in_parent']

    def get_inherit_list_in_build(self, component):
        if component not in self.inherit_comps:
            self.inherit_comps[component] = {}
        if 'in_build' not in self.inherit_comps[component]:
            self.inherit_comps[component]['in_build'] = self.get_list_in_build_from_builds(component)
        return self.inherit_comps[component]['in_build']

    def get_list_in_parent_from_builds(self, component):
        inherit_list = []
        print('Get inherit list from base loads: {}'.format(self.base_loads))
        for base_load in self.base_loads:
            inherit_list.extend(self.get_inherit_list_from_parent(base_load, component))
        return inherit_list

    def get_list_in_build_from_builds(self, component):
        inherit_list = []
        for base_load in self.base_loads:
            inherit_list.extend(self.get_inherit_sub_components(base_load, component))
        return inherit_list

    def get_inherit_list_by_filter(self, component, type_filter):
        if not type_filter or type_filter == 'all':
            return self.get_all_inherit_list(component)
        if type_filter == 'in_parent':
            return self.get_inherit_list_in_parent(component)
        if type_filter == 'in_build':
            return self.get_inherit_list_in_build(component)
        print('Cannot find valid type filter {}'.format(type_filter))
        return []

    def get_build_configs(self):
        for base_load in self.base_loads:
            if base_load not in self.build_config_dict:
                base_build_config = {}
                try:
                    base_build_config = yaml.load(wft_tools.get_build_config(base_load),
                                                  Loader=yamlordereddictloader.Loader)
                except Exception:
                    print('Cannot find build_config for {}'.format(base_load))
                self.build_config_dict[base_load] = base_build_config

    def get_build_components(self):
        if not self.build_config_dict:
            self.get_build_configs()
        component_list = []
        for build_config in self.build_config_dict.values():
            if 'components' in build_config:
                component_list.extend(build_config['components'].keys())
        if self.extra_components:
            component_list.extend(self.extra_components)
        return component_list

    def is_component_staged(self, component):
        is_staged = False
        if not self.build_config_dict:
            self.get_build_configs()
        for build_config in self.build_config_dict.values():
            if 'components' in build_config:
                if component in build_config['components']:
                    if 'type' in build_config['components'][component]:
                        if build_config['components'][component]['type'] == 'staged':
                            is_staged = True
                        else:
                            return False
        return is_staged

    def get_inherit_changes(self, component, version, type_filter='', filter_by_build_config=True):
        inherit_list = self.get_inherit_list_by_filter(component, type_filter=type_filter)
        component_list = self.get_build_components()
        inherit_change_dict = {}
        if not inherit_list:
            return {}
        for sub_build in wft_tools.get_subuild_from_wft(version):
            project_component = "{}:{}".format(sub_build['project'], sub_build['component'])
            if project_component in inherit_list:
                if filter_by_build_config:
                    if project_component not in component_list:
                        print("{} is not in build_config components".format(project_component))
                        continue
                update_dict = {"version": sub_build['version']}
                staged_dict = wft_tools.get_staged_from_wft(
                    sub_build['version'],
                    project=sub_build['project'],
                    component=sub_build['component'])
                is_staged = self.is_component_staged(project_component)
                for key, value in staged_dict.items():
                    if not is_staged and key not in ['commit', 'version']:
                        continue
                    if key and value:
                        update_dict[key] = value
                inherit_change_dict[project_component] = update_dict
        if not inherit_change_dict:
            print("Can not get {} version from {}'s sub_build".format(inherit_list, version))
        return inherit_change_dict

    def get_inherit_change_by_changedict(self, rest, env_change_dict, change_no,
                                         config_yaml_file='config.yaml', type_filter=''):
        config_yaml_content = rest.get_file_content(config_yaml_file, change_no)
        return self.get_inherit_change_for_changedict(env_change_dict, config_yaml_content, type_filter)

    def get_inherit_change_for_changedict(self, env_change_dict, config_yaml_content, type_filter=''):
        inherit_changes = {}
        config_yaml_obj = config_yaml.ConfigYaml(config_yaml_content=config_yaml_content)
        for env_key, env_value in env_change_dict.items():
            version = env_changes.get_version_from_change_value(env_value)
            section_key, section = config_yaml_obj.get_env_change_section(env_key)
            if section_key and version:
                inherit_changes.update(self.get_inherit_changes(section_key, version, type_filter))
        return inherit_changes

    def get_inherit_dict(self, build):
        if build not in self.inherit_dict:
            self.inherit_dict[build] = self._get_inherit_dict(build)
        return self.inherit_dict[build]

    def get_inherit_sub_components(self, build, component):
        sub_comps = []
        inherit_dict = self.get_inherit_dict(build)
        for sub_comp, parent_comp in inherit_dict.items():
            if parent_comp == component:
                sub_comps.append(sub_comp)
        return sub_comps

    def order_comp_with_count(self, parent_count_dict):
        value_key_pairs = ((value, key) for (key, value) in parent_count_dict.items())
        return [x[1] for x in sorted(value_key_pairs, reverse=True)]

    def get_inherit_parent_component(self, build, sub_component):
        inherit_dict = self.get_inherit_dict(build)
        parent_count_dict = {}
        base_subbuild_list = wft_tools.get_subbuilds(build)
        for sub_comp, parent_comp in inherit_dict.items():
            if parent_comp not in parent_count_dict:
                parent_count_dict[parent_comp] = 0
            parent_count_dict[parent_comp] += 1
        if sub_component in inherit_dict:
            for subbuild in base_subbuild_list:
                wft_comp_name = '{}:{}'.format(subbuild['project'], subbuild['sc'])
                if wft_comp_name == inherit_dict[sub_component]:
                    return subbuild
        if self.extra_components:
            if sub_component not in self.extra_components:
                print("Canot find {} directly in inherit_dict".format(sub_component))
                return None
        print("Try to find {} in parent components".format(sub_component))
        for parent_comp in self.order_comp_with_count(parent_count_dict):
            print("Try to find from {}".format(parent_comp))
            for subbuild in base_subbuild_list:
                wft_comp_name = '{}:{}'.format(subbuild['project'], subbuild['sc'])
                if wft_comp_name == parent_comp and 'sub_build_baseline' in subbuild:
                    parent_inherit_dict = self.get_inherit_dict(subbuild['sub_build_baseline'])
                    print('Parent inherit_dict for {}'.format(subbuild['sub_build_baseline']))
                    if sub_component in parent_inherit_dict.values():
                        return subbuild
        print("Canot find matched parent component for {}".format(sub_component))
        return None

    def get_parent_inherit_dict(self, build, sub_component):
        parent_build = self.get_inherit_parent_component(build, sub_component)
        if parent_build and 'sub_build_baseline' in parent_build:
            print("Get sub_build_baseline {}".format(parent_build['sub_build_baseline']))
            return self.get_inherit_dict(parent_build['sub_build_baseline'])
        return {}

    def get_inherit_list_from_parent(self, build, component):
        inherit_list = []
        inherit_dict = self.get_parent_inherit_dict(build, component)
        for sub_comp, parent_comp in inherit_dict.items():
            if component == parent_comp and sub_comp not in inherit_list:
                inherit_list.append(sub_comp)
        return inherit_list

    def _get_inherit_dict(self, build):
        inherit_dict = {}
        base_subbuild_list = wft_tools.get_subbuilds(build)
        print(build)
        print(base_subbuild_list)
        for subbuild in base_subbuild_list:
            if "inherited_from" in subbuild:
                wft_comp_name = '{}:{}'.format(subbuild['project'], subbuild['sc'])
                parent_comp_name = '{}:{}'.format(subbuild['inherited_from']['project'],
                                                  subbuild['inherited_from']['component'])
                inherit_dict[wft_comp_name] = parent_comp_name
        print('Inherit dict for {}'.format(build))
        print(inherit_dict)
        return inherit_dict

    def get_all_inherit_dict(self):
        for base_load in self.base_loads:
            self.get_inherit_dict(base_load)

    def is_in_inherit_map(self, component, type_filter=''):
        self.get_all_inherit_dict()
        for build_name, inherit_dict in self.inherit_dict.items():
            if type_filter:
                if type_filter == 'in_parent':
                    if build_name in self.base_loads:
                        continue
                if type_filter == 'in_build':
                    if build_name not in self.base_loads:
                        continue
            if component in inherit_dict.keys() or component in inherit_dict.values():
                return True
        return False

    def is_in_inherit_parent(self, component, type_filter=''):
        self.get_all_inherit_dict()
        for build_name, inherit_dict in self.inherit_dict.items():
            if type_filter:
                if type_filter == 'in_parent':
                    if build_name in self.base_loads:
                        continue
                if type_filter == 'in_build':
                    if build_name not in self.base_loads:
                        continue
            if component in inherit_dict.values():
                return True
        return False

    def is_in_inherit_sub(self, component, type_filter=''):
        self.get_all_inherit_dict()
        for build_name, inherit_dict in self.inherit_dict.items():
            if type_filter:
                if type_filter == 'in_parent':
                    if build_name in self.base_loads:
                        continue
                if type_filter == 'in_build':
                    if build_name not in self.base_loads:
                        continue
            if component in inherit_dict.keys():
                return True
        return False
