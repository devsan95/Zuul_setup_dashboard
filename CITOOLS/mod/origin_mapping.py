import copy
import logging


class Origin_Mapping(object):
    """
    A Class to do operations on cloned integration/ repository
    """

    def __init__(self, mapping_dict, no_platform=False):
        self.mapping_dict = mapping_dict
        self.src_list = mapping_dict['sources']
        self.depend_dict = {}
        if not no_platform:
            self.generate_platform_dict()

    def get_depended_dict(self):
        depend_dict = {}
        for src in self.src_list:
            for recipe in src['recipes']:
                for key_name in recipe.keys():
                    if key_name.endswith('.bb'):
                        bb_values = recipe[key_name]
                        if 'depends' in bb_values and 'component' in recipe:
                            depend_dict[recipe['component']] = bb_values['depends'].split()
        logging.info('Depend dict %s', depend_dict)
        self.depend_dict = depend_dict

    def get_depended_files(self, comp_name, platform=''):
        recipe_list = []
        comp_recipe = self.get_component_related(comp_name, platform)[2][0]
        logging.info("Find depending component for: %s", comp_recipe)
        for component, depend_list in self.depend_dict.items():
            if comp_name in depend_list or \
                    ('component' in comp_recipe and comp_recipe['component'] in depend_list):
                recipe_list.extend(self.get_component_related(component)[1])
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
        logging.info("Start parse bb_mapping file")
        self.get_depended_dict()
        platform_dict = {}
        for component in self.depend_dict:
            if component.startswith('integration-'):
                if component not in platform_dict:
                    platform_dict[component] = []
                self.find_sub_components(component, platform_dict[component])
                platform_dict[component] = list(set(platform_dict[component]))
                logging.info("Components in %s is %s", component, platform_dict[component])
        logging.info("Parse bb_mapping file done")
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
        return recipe_files

    def get_component_related(self, comp_name, platform=''):
        ret_src = {}
        ret_recipes = []
        ret_recipe_values = []
        for src in self.src_list:
            if 'recipes' not in src:
                continue
            if 'src_uri' in src and src['src_uri'] == comp_name:
                if ret_src:
                    ret_src['recipes'].extend(src['recipes'])
                else:
                    ret_src = copy.deepcopy(src)
                for recipe_dict in src['recipes']:
                    ret_recipes.extend(recipe_dict.keys())
                    ret_recipe_values.append(recipe_dict.values())
            for recipe in src['recipes']:
                recipe_file = get_recipe_file(recipe)
                if comp_name == recipe.get('component') or \
                        comp_name == recipe.get('WFT_COMPONENT') or \
                        recipe_file == comp_name:
                    if platform and \
                            comp_name not in self.platform_dict['integration-{}'.format(platform)]:
                        continue
                    if ret_src:
                        ret_src['recipes'].extend(src['recipes'])
                    else:
                        ret_src = copy.deepcopy(src)
                    ret_recipes.append(get_recipe_file(recipe))
                    ret_recipe_values.append(recipe)
                    break
        if (len(ret_recipes)) > 1:
            logging.warn('***MULTI RECIPES matched***')
            logging.warn(ret_recipes)
        return ret_src, ret_recipes, ret_recipe_values

    def get_component_file(self, comp_name, platform=''):
        recipe_files = self.get_component_related(comp_name, platform)[1]
        if recipe_files:
            return recipe_files[0]
        return ''

    def get_component_files(self, comp_name, platform=''):
        return self.get_component_related(comp_name, platform)[1]

    def get_component_source(self, comp_name, platform=''):
        return self.get_component_related(comp_name, platform)[0]

    def get_component_value(self, comp_name, key, platform=''):
        source, recipes, recipe_values = self.get_component_related(comp_name, platform)
        if not source:
            return None
        return self._get_value_from_src_dict(source, recipe_values, key)

    def _get_value_from_src_dict(self, src_dict, recipe_values, mapping_key):
        logging.info("Get value for %s from %s", mapping_key, src_dict)
        if mapping_key in src_dict:
            logging.info("Get info for %s: %s", mapping_key, src_dict)
            return src_dict[mapping_key]
        for recipe_value in recipe_values:
            if mapping_key in recipe_value:
                logging.info("Get info for %s: %s", mapping_key, recipe_value)
                return recipe_value[mapping_key]
        if 'recipes' in src_dict:
            for recipe_dict in src_dict['recipes']:
                if mapping_key in recipe_dict:
                    logging.info("Get info for %s: %s", mapping_key, recipe_dict)
                    return recipe_dict[mapping_key]
        return ''

    def get_comp_value_by_keys(self, comp_name, keys):
        source, recipes, recipe_values = self.get_component_related(comp_name)
        logging.info('get source for component {}'.format(comp_name))
        logging.info(source)
        for mapping_key in keys:
            found = self._get_value_from_src_dict(source, recipe_values, mapping_key)
            if found:
                return found
        if source:
            return ''
        return None


def get_recipe_file(recipe):
    for key_name in recipe.keys():
        if key_name.endswith('.bb'):
            return key_name
    return ''
