import copy
import yaml

from mod import wft_tools


class ConfigYaml(object):
    """
    A Class to do operations on cloned integration/ repository
    """

    def __init__(self, config_yaml_file=None, local_config_file=None,
                 config_yaml_content=None, local_config_content=None):
        self.config_yaml_file = config_yaml_file
        self.config_yaml_content = config_yaml_content
        self.local_config_file = local_config_file
        self.local_config_content = local_config_content
        self.local_config_yaml = None
        self.update_yaml_data()

    def update_yaml_data(self):
        if self.config_yaml_file:
            with open(self.config_yaml_file, 'r') as fhandler_r:
                self.config_yaml = yaml.safe_load(fhandler_r.read())
        elif self.config_yaml_content:
            self.config_yaml = yaml.safe_load(self.config_yaml_content)
        self.origin_config_yaml = copy.deepcopy(self.config_yaml)
        if self.local_config_file:
            with open(self.local_config_file, 'r') as fhandler_r:
                self.local_config_yaml = yaml.safe_load(fhandler_r.read())
            self.config_yaml.update(self.local_config_yaml)
        elif self.local_config_content:
            self.local_config_yaml = yaml.safe_load(self.local_config_content)
            self.config_yaml.update(self.local_config_yaml)
        self.components = self.config_yaml['components']

    def get_section_value(self, section_name, option_key):
        return self.components[section_name][option_key]

    def get_wft_comp_proj(self, internal_key, internal_key_name):
        section_key, section = self.get_section_by_internal_key(internal_key, internal_key_name)
        if not section_key:
            raise Exception("ERROR: component key {} can't be found in config.yaml".format(internal_key_name))
        return section_key.split(':')[0], section_key.split(':')[1]

    def get_section_by_internal_key(self, internal_key, internal_key_name):
        for section_key, section in self.components.items():
            if internal_key in section and section[internal_key] == internal_key_name:
                return section_key, section
        return None, None

    def get_internal_key_value(self, internal_key, internal_key_name, option_key):
        for section in self.components.values():
            if internal_key in section and section[internal_key] == internal_key_name:
                return section[option_key]
        return None

    def update_by_local_config(self, local_config_file):
        local_config_yaml = yaml.safe_load(local_config_file)
        self.config_yaml.update(local_config_yaml)
        self.components = self.config_yaml['components']

    def replace_section_value(self, section_name, option_key, option_value):
        self.components[section_name][option_key] = option_value

    def replace_internal_key_value(self, internal_key,
                                   internal_key_name, option_key, option_value):
        for section in self.components.values():
            if internal_key in section and section[internal_key] == internal_key_name:
                section[option_key] = option_value

    def get_env_change_section(self, key_name):
        if key_name in self.components:
            print('get section from section key')
            return key_name, self.components[key_name]
        section_key, section = self.get_component_section(key_name)
        if section:
            print('get section from component')
            return section_key, section
        section_key, section = self.get_section_by_internal_key('env_key', key_name)
        if section:
            print('get section from env_key')
            return section_key, section
        return None, None

    def get_component_section(self, component_name):
        for section_key, section in self.components.items():
            if 'feature_component' in section and section['feature_component'] == component_name:
                return section_key, section
            elif section_key.endswith(':{}'.format(component_name)):
                return section_key, section
        return None, None

    def replace_comonent_value(self, component_name, option_key, option_value):
        section_key, section = self.get_component_section(component_name)
        if section:
            section[option_key] = option_value
            return True
        return False

    def update_config_yaml(self, update_local=False, update_all_to_origin=False):
        copy_of_local_config = copy.deepcopy(self.local_config_yaml)
        copy_of_local_components = {}
        if copy_of_local_config:
            copy_of_local_components = copy_of_local_config['components']
        if update_local and self.local_config_yaml:
            for section_key, value in self.components.items():
                if section_key in copy_of_local_components:
                    copy_of_local_components[section_key] = value
            with open(self.local_config_file, 'w') as fhandler_w:
                fhandler_w.write(yaml.safe_dump(copy_of_local_config))
        with open(self.config_yaml_file, 'w') as fhandler_w:
            if update_all_to_origin:
                fhandler_w.write(yaml.safe_dump(self.config_yaml))
                return
            copy_of_config_yaml = copy.deepcopy(self.origin_config_yaml)
            copy_of_config_components = copy_of_config_yaml['components']
            for section_key, value in self.components.items():
                if not self.local_config_yaml or \
                        section_key not in self.local_config_yaml['components']:
                    copy_of_config_components[section_key] = value
            fhandler_w.write(yaml.safe_dump(copy_of_config_yaml))

    def update_by_env_change(self, env_change_dict):
        # used to restore changes to env file
        # will be removed after env file removed
        env_file_changes = {}
        for key, value in env_change_dict.items():
            replace_section_key, replace_section = self.get_env_change_section(key)
            if not replace_section:
                raise Exception('Cannot find env key {}'.format(key))
            if 'env_key' in replace_section:
                env_file_changes[replace_section['env_key']] = value
            # update env_change version in config.yaml
            print('update key: {} to {}'.format(key, replace_section_key))
            if replace_section['version'] == replace_section['commit']:
                replace_section['commit'] = value
            replace_section['version'] = value
            wft_component, wft_project = replace_section_key.split(':')
            # update staged infos if exists
            staged_dict = wft_tools.get_staged_from_wft(value, wft_component, wft_project)
            if not staged_dict:
                staged_dict = wft_tools.get_staged_from_wft(value)
            for staged_key, staged_value in staged_dict.items():
                if staged_value:
                    replace_section[staged_key] = staged_value
        return env_file_changes
