#!/usr/bin/env python
import copy


def get_component_list(comp_config):
    return [
        component for group in comp_config['components']
        for component in comp_config['components'][group]
    ]


def parse_hierarchy(hierarchy, pkey=None):
    parse_dict = {}
    if isinstance(hierarchy, dict):
        for key, value in hierarchy.items():
            if isinstance(value, (dict, list)):
                sub_dict = parse_hierarchy(value, key)
                parse_dict.update(sub_dict)
                if not pkey:
                    continue
                if pkey not in parse_dict:
                    parse_dict[pkey] = copy.deepcopy(sub_dict.values()[0])
                else:
                    parse_dict[pkey].extend(sub_dict.values()[0])
                    parse_dict[pkey] = list(set(parse_dict[pkey]))
            else:
                raise Exception('{} dict and not list'.format(hierarchy))
    elif isinstance(hierarchy, list):
        for list_obj in hierarchy:
            if isinstance(list_obj, basestring):
                if not pkey:
                    raise Exception('{} not have key'.format(hierarchy))
                if pkey not in parse_dict:
                    parse_dict[pkey] = [list_obj]
                else:
                    parse_dict[pkey].append(list_obj)
            else:
                parse_dict.update(parse_hierarchy(list_obj, pkey))
    else:
        raise Exception('{} dict and not list'.format(hierarchy))
    return parse_dict
