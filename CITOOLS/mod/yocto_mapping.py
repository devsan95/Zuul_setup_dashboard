import os
import copy


class Yocto_Mapping(object):
    """
    A Class to do operations on yocto mapping from WFT
    """

    def __init__(self, mapping_dict, no_platform=False):
        self.mapping_dict = mapping_dict
        self.src_list = mapping_dict['sources']
        self.depend_dict = {}
        self.platform_dict = {}
        if not no_platform:
            self.generate_platform_dict()

    def get_depended_dict(self):
        depend_dict = {}
        for src in self.src_list:
            for recipe in src['recipes']:
                for key_name in recipe.keys():
                    if key_name.endswith('.bb'):
                        bb_values = recipe[key_name]
                        if 'depends' in bb_values and 'PN' in bb_values:
                            depend_dict[bb_values['PN']] = bb_values['depends'].split()
        self.depend_dict = depend_dict

    def get_depended_files(self, comp_name, platform=''):
        recipe_list = []
        comp_recipe = self.get_component_related(comp_name, platform)[2][0]
        print("Find depending component for: {}".format(comp_recipe))
        for component, depend_list in self.depend_dict.items():
            if comp_name in depend_list or \
                    ('PN' in comp_recipe and comp_recipe['PN'] in depend_list):
                recipe = self.get_component_related(component)[1]
                recipe_list.extend(recipe)
        return recipe_list

    def find_up_component(self, component, until_integration=False):
        parent_list = []
        for name, depend_list in self.depend_dict.items():
            if component in depend_list:
                if not name.startswith('integration-') and until_integration:
                    parent_list.extend(self.find_up_component(name, True))
                else:
                    parent_list.extend(name)
        return parent_list

    def find_sub_components(self, component, sub_list=None, collected=None):
        if sub_list is None:
            sub_list = []
        if collected is None:
            collected = []
        if component in self.depend_dict and component not in collected:
            sub_list.extend(self.depend_dict[component])
            collected.append(component)
            for sub_component in self.depend_dict[component]:
                self.find_sub_components(sub_component, sub_list, collected)

    def generate_platform_dict(self):
        print("Start parse bb_mapping file")
        self.get_depended_dict()
        if not self.depend_dict:
            print("No depended dict")
            return
        platform_dict = {}
        for component in self.depend_dict:
            if component.startswith('integration-'):
                if component not in platform_dict:
                    platform_dict[component] = []
                self.find_sub_components(component, platform_dict[component])
                platform_dict[component] = list(set(platform_dict[component]))
                print("Components in {} is {}".format(component, platform_dict[component]))
        print("Parse bb_mapping file done")
        self.platform_dict = platform_dict

    def get_integration_targets(self, comp_name, platform=''):
        integration_targets = []
        for integration_target, depend_list in self.platform_dict.items():
            if comp_name in depend_list:
                if platform and 'integration-{}'.format(platform) != integration_target:
                    continue
                integration_targets.append(integration_target)
        return list(set(integration_targets))

    def get_integration_files(self, comp_name, platform=''):
        recipe_files = []
        integration_targets = self.get_integration_targets(comp_name, platform)
        for integration_target in integration_targets:
            recipe_files.append(self.get_component_file(integration_target))

    def get_component_source_by_project(self, project_name):
        for source in self.mapping_dict['sources']:
            if 'recipes' not in source:
                continue
            if 'src_uri' in source and self.is_src_uri_match(source['src_uri'], project_name):
                return source
        return None

    def is_src_uri_match(self, src_uri1, src_uri2):
        print('Compare {} and {}'.format(src_uri1, src_uri2))
        if src_uri1.endswith(src_uri2) or src_uri1.endswith('{}.git'.format(src_uri2)):
            return True
        return False

    def get_component_related(self, comp_name, platform=''):
        ret_list = []
        ret_src = {}
        ret_recipes = []
        ret_recipe_values = []
        for src in self.src_list:
            if 'recipes' not in src:
                continue
            if 'src_uri' in src and \
                    (src['src_uri'] == comp_name or self.is_src_uri_match(src['src_uri'], comp_name)):
                ret_list.append((copy.deepcopy(src), src['recipes']))
            for recipe in src['recipes']:
                for recipe_key, recipe_value in recipe.items():
                    if comp_name == recipe_value.get('PN') or \
                            comp_name == recipe_value.get('WFT_COMPONENT') or \
                            comp_name == recipe_key:
                        if platform and \
                                comp_name not in self.platform_dict['integration-{}'.format(platform)]:
                            continue
                        ret_list.append((copy.deepcopy(src), [{recipe_key: recipe_value}]))
        # only for legency knife json format , can be removed later
        if not ret_list:
            ret_by_recipe_name = self.get_related_by_recipe_name(comp_name, platform)
            if ret_by_recipe_name:
                return ret_by_recipe_name
        if (len(ret_list)) > 1:
            print('***MULTI RECIPES matched***')
            print(ret_list)
            filtered_tuple = self.filter_matched_tuple(ret_list, comp_name)
            if filtered_tuple:
                return filtered_tuple
        for src, recipe_dicts in ret_list:
            if ret_src:
                ret_src['recipes'].extend(src['recipes'])
            else:
                ret_src = src
            for recipe_dict in recipe_dicts:
                ret_recipes.extend(recipe_dict.keys())
                ret_recipe_values.append(recipe_dict.values())
        return ret_src, ret_recipes, ret_recipe_values

    def get_related_by_recipe_name(self, comp_name, platform):
        # only for legency knife json format , can be removed later
        ret_list = []
        for src in self.src_list:
            for recipe in src['recipes']:
                for recipe_key, recipe_value in recipe.items():
                    if os.path.basename(recipe_key).split('.bb')[0].split('_')[0] == comp_name:
                        if platform and \
                                comp_name not in self.platform_dict['integration-{}'.format(platform)]:
                            continue
                        ret_list.append((src, src['recipes']))
        return self.filter_matched_tuple(ret_list, comp_name)

    def filter_matched_tuple(self, ret_list, comp_name):
        if len(ret_list) == 0:
            return None
        if len(ret_list) == 1:
            return ret_list[0]
        for ret_tuple in ret_list:
            if ret_tuple and ret_tuple[1]:
                for recipe in ret_tuple[1]:
                    if recipe.values()[0].get('name') and recipe.values()[0].get('name').lower() == comp_name.lower():
                        return (ret_tuple[0], recipe.keys(), recipe.values())
        print('***Match multi src: {} for {} ***'.format(ret_list, comp_name))
        return None

    def get_component_file(self, comp_name, platform=''):
        recipe_files = self.get_component_related(comp_name, platform)[1]
        if recipe_files:
            return recipe_files[0]
        return ''

    def get_component_files(self, comp_name, platform=''):
        return self.get_component_related(comp_name, platform)[1]

    def get_component_source(self, comp_name, platform=''):
        return self.get_component_related(comp_name, platform)[0]

    def get_sub_sources(self, src_dict):
        if not src_dict or not src_dict.get('recipes'):
            return []
        for recipe_info in src_dict['recipes']:
            if recipe_info:
                if 'subsources' in recipe_info:
                    return recipe_info['subsources']
        return []

    def get_component_value(self, comp_name, key, platform=''):
        source, recipes, recipe_values = self.get_component_related(comp_name, platform)
        print('Get source')
        print(source)
        if not source:
            return None
        return self._get_value_from_src_dict(source, recipe_values, key)

    def _get_value_from_src_dict(self, src_dict, recipe_values, mapping_key):
        if mapping_key in src_dict:
            return src_dict[mapping_key]
        sub_sources = self.get_sub_sources(src_dict)
        src_uri_type = src_dict.get('src_uri_type')
        if sub_sources:
            print('Get sub_sources {}'.format(sub_sources))
        for sub_source in sub_sources:
            if mapping_key in sub_source:
                if src_uri_type == 'svn' and mapping_key == 'rev':
                    return '{}@{}'.format(sub_source['module'], sub_source['rev'])
                else:
                    return sub_source[mapping_key]
        for recipe_value in recipe_values:
            if mapping_key in recipe_value:
                print("Get info for {}: {}".format(mapping_key, recipe_value))
                return recipe_value[mapping_key]
        return ''

    def get_comp_value_by_keys(self, comp_name, keys):
        source, recipes, recipe_values = self.get_component_related(comp_name)
        for mapping_key in keys:
            found = self._get_value_from_src_dict(source, recipe_values, mapping_key)
            if found:
                return found
        if source:
            return ''
        return None
