#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import json
import numbers

import requests
from xml.etree import cElementTree as ElementTree


class WftAuth(object):
    def __init__(self, access_key):
        self.access_key = None
        self.set_access_key(access_key)

    def set_access_key(self, access_key):
        self.access_key = access_key

    def get_auth(self):
        return {'access_key': self.access_key}

    def get_access_key(self):
        return self.access_key


class WftBuildQuery(object):
    def __init__(self, auth):
        self.auth = None
        self.set_auth(auth)

        self.columns = []
        self.filters = []
        self.page = None
        self.items = None
        self.sorting_field = None
        self.sorting_direction = None
        self.group_by = None
        self.group_by_processor = None

        self.reset()

        self.operations = [
            'eq', 'not_eq', 'eq_any', 'cont', 'not_cont', 'cont_any',
            'matches_regexp', 'does_not_match_regexp', 'lt', 'lteq', 'gt',
            'gteq', 'start', 'not_start', 'end', 'not_end', 'date_between',
            'date_between_relative', 'not_date_between',
            'not_date_between_relative'
        ]
        self.sorting_directions = ['ASC', 'DESC']

    def reset(self):
        self.reset_columns()
        self.reset_filters()
        self.page = 1
        self.items = '20'
        self.sorting_field = 'baseline'
        self.sorting_direction = 'DESC'
        self.group_by = ''
        self.group_by_processor = ''

    def set_auth(self, auth):
        self.auth = auth

    def reset_columns(self):
        self.columns = [
            'deliverer.project.full_path', 'deliverer.title', 'baseline',
            'branch.title', 'state', 'planned_delivery_date', 'common_links',
            'compare_link', 'id', 'created_at', 'version'
        ]

    def set_columns(self, columns):
        if not isinstance(columns, list):
            raise Exception("columns type wrong, please input list.")
        self.columns = columns

    def reset_filters(self):
        self.filters = []

    def _filter_param_check(self, column, operation, value):
        if operation not in self.operations:
            raise Exception(
                'operation wrong, '
                'please use operations in {}'.format(self.operations))

        if not isinstance(column, basestring):
            raise Exception(
                'column wrong, '
                'column should be a string')

        if (not isinstance(value, basestring)) and \
           (not isinstance(value, list)):
            raise Exception(
                'value wrong, '
                'value should be a string or a list')

    def _find_filter(self, column, operation, value):
        for item in self.filters:
            if item['column'] == column and \
               item['operation'] == operation and \
               item['value'] == value:
                return item
        return None

    def add_filter(self, column, operation, value):
        self._filter_param_check(column, operation, value)
        item = self._find_filter(column, operation, value)
        if not item:
            self.filters.append(
                {'column': column,
                 'operation': operation,
                 'value': value}
            )

    def remove_filter(self, column, operation, value):
        self._filter_param_check(column, operation, value)
        item = self._find_filter(column, operation, value)
        if item:
            self.filters.remove(item)

    def add_columns(self, column):
        if column not in self.columns:
            self.columns.append(column)

    def remove_columns(self, column):
        if column in self.columns:
            self.columns.remove(column)

    def set_result_number(self, number):
        if isinstance(number, numbers.Integral) and number > 0:
            self.items = str(number)
        else:
            raise Exception('number wrong, please input positive integer')

    def get_result_number(self):
        return int(self.items)

    def set_group_by(self, group=None, processor=None):
        if isinstance(group, basestring):
            self.group_by = group
        else:
            self.group_by = ''

        if isinstance(processor, basestring):
            self.group_by_processor = processor
        else:
            self.group_by_processor = ''

    def set_sorting(self, field=None, desc=True):
        if isinstance(field, basestring):
            self.sorting_field = field
        else:
            self.sorting_field = ''

        if desc:
            self.sorting_direction = 'DESC'
        else:
            self.sorting_field = 'ASC'

    def set_page(self, page):
        self.page = page

    def next_page(self):
        self.page += 1

    def previous_page(self):
        if self.page > 1:
            self.page -= 1

    def _gen_request_json(self):
        json_dict = {
            "page": str(self.page),
            "items": self.items,
            "sorting_field": self.sorting_field,
            "sorting_direction": self.sorting_direction,
            "group_by": self.group_by,
            "group_by_processor": self.group_by_processor,
            "columns": self.columns,
            "view_filters_attributes": {},
            "access_key": self.auth.get_access_key()
        }
        for i, filter_ in enumerate(self.filters):
            json_dict['view_filters_attributes'][i] = {
                "column": filter_['column'],
                "operation": filter_['operation'],
                "value": filter_['value']
            }
        return json.dumps(json_dict)

    def query(self, ssl_verify=False):
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        json_str = self._gen_request_json()
        response = \
            requests.get('https://wft.int.net.nokia.com:8091/api/v1/build.json',
                         headers=headers,
                         data=json_str,
                         verify=ssl_verify)
        if not response.ok:
            raise Exception('error {}, content: {}'.format(
                response.status_code, response.content))
        return json.loads(response.content)


class WftBuild(object):
    def __init__(self, xml):
        self.xml = xml
        self.tree = ElementTree.fromstring(self.xml)

    @classmethod
    def get_build(cls, baseline):
        response = \
            requests.get('https://wft.int.net.nokia.com/ext/'
                         'build_content/{}'.format(baseline),
                         verify=False)
        if not response.ok:
            raise Exception('Cannot get build xml')
        return cls(response.content)

    def traverse(self):
        self.print_children(self.tree, 0)

    @staticmethod
    def print_children(ele, indent):
        if isinstance(ele.text, basestring):
            text = ele.text.strip()
        else:
            text = ''
        print('{}{}<{}>{} {}'.format(' ' * indent,
                                     '└', ele.tag,
                                     text, ele.attrib,))
        for child in ele:
            WftBuild.print_children(child, indent + 2)

    def find_items(self, xpath):
        return self.tree.findall(xpath)


class WftBaselineConfigurations(object):

    def __init__(self, content):
        self.content = content
        self.json_content = json.loads(self.content)

    @classmethod
    def get_baseline_configurations(cls, project, component, version, wftauth):
        headers = {
            'Accept': 'text/legacy'
        }
        requests_url = 'https://wft.int.net.nokia.com:8091/api/v1/{project}/{component}/builds/{version}.json'.format(
            project=project,
            component=component,
            version=version
        )
        response = requests.get(
            requests_url,
            headers=headers,
            data=wftauth.get_auth()
        )
        if not response.ok:
            raise Exception('error {}, content: {}'.format(response.status_code, response.content))
        return cls(response.content)

    def get_element(self, element_key):
        return self.json_content[element_key] if element_key in self.json_content else None

    def get_html_releasenote_id(self):
        return self.get_element('html_releasenote_id') if self.get_element('html_releasenote_id') else 0

    def get_xml_releasenote_id(self):
        return self.get_element('xml_releasenote_id') if self.get_element('xml_releasenote_id') else 0

    def get_release_setting_id(self):
        return self.get_element('release_setting_id') if self.get_element('release_setting_id') else 0

    def get_release_note_template_id(self):
        return self.get_element('release_note_template_id') if self.get_element('release_note_template_id') else 0

    def get_release_note_template_version_id(self):
        return self.get_element('release_note_template_version_id') if self.get_element('release_note_template_version_id') else 0

    def get_config_spec_id(self):
        return self.get_element('config_spec_id') if self.get_element('config_spec_id') else 0

    def get_config_spec_version_id(self):
        return self.get_element('config_spec_version_id') if self.get_element('config_spec_version_id') else 0

    def get_repository(self):
        return {
            'repository_url': self.get_element('repository_url'),
            'repository_branch': self.get_element('repository_branch'),
            'repository_revision': self.get_element('repository_revision'),
            'repository_type': self.get_element('repository_type')
        }


class WftObjBuild(object):
    def __init__(self):
        self.credential = None
        self.project = None,
        self.component = None,
        self.build = None
        self.wft_url = "https://wft.int.net.nokia.com"
        self.cached_details = {}

    def set_component(self, component):
        self.component = component

    def set_project(self, project):
        self.project = project

    def set_build(self, build):
        self.build = build

    def set_wft_url(self, url):
        self.wft_url = url

    def set_credential(self, credential):
        self.credential = credential

    def get_detailed_info(self, refresh=False):
        if not refresh and len(self.cached_details) == 0:
            pass
        else:
            uri = "{}/api/v1/{}/{}/builds/{}.json?access_key={}".format(self.wft_url,
                                                                        self.project,
                                                                        self.component,
                                                                        self.build,
                                                                        self.credential.get_access_key())
            try:
                req = requests.get(uri, verify=False)
            except Exception as ex:
                print(ex)
            else:
                self.cached_details = req.json()
        return self.cached_details

    def get_available_status(self):
        uri = "{}/api/v1/{}/{}/builds/{}/transitions.json?access_key={}".format(self.wft_url,
                                                                                self.project,
                                                                                self.component,
                                                                                self.build,
                                                                                self.credential.get_access_key())
        try:
            req = requests.get(uri, verify=False)
            if not req.ok:
                raise Exception("request item failed")
        except Exception as ex:
            print(ex)
        else:
            data = req.json()
            output = {}
            for item in data:
                if item["via_trigger"]:
                    output[item['to']] = {"id": item['id'], "from": item['from'], "to": item["to"]}
            return output

    def get_status(self):
        info = self.get_detailed_info(True)
        return info['state']

    def update_status(self, new_status):
        available_status = self.get_available_status()
        if new_status in available_status:
            uri = "{}/api/v1/{}/{}/builds/{}/transitions/{}/trigger.json?access_key={}".format(
                self.wft_url,
                self.project,
                self.component,
                self.build,
                available_status[new_status]["id"],
                self.credential.get_access_key()
            )
            try:
                response = requests.post(
                    uri,
                    verify=False
                )
                if not response.ok:
                    raise Exception("failed to change status on build {}".format(self.build))
            except Exception as ex:
                print("failed Code: {}".format(response.status_code))
                print(ex)
                return False
            else:
                print("changed {} to {}".format(self.build, new_status))
                return True
        else:
            print("changed {} cannot be migrate to status: {}".format(self.build, new_status))
            return False

    def update_build(self, repo_url, repo_branch, repo_repository_revision, repo_type, note):
        uri = "{}/api/v1/{}/{}/builds/{}.json".format(self.wft_url, self.project, self.component, self.build)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        # payload
        payload = {
            "build": {"repository_url": repo_url,
                      "repository_branch": repo_branch,
                      "repository_type": repo_type,
                      "repository_revision": repo_repository_revision,
                      "important_note": note}
        }
        print("modify build with following info:")
        print(json.dumps(payload, sort_keys=True, indent=4))
        payload.update(self.credential.get_auth())
        try:
            response = requests.patch(
                uri,
                headers=headers,
                json=payload,
                verify=False
            )
            if not response.ok:
                raise Exception("failed when post new increment to WFT")
        except Exception as ex:
            print("failed Code: {}".format(response.status_code))
            print(ex)
            return None
        else:
            return True

    def __str__(self):
        data = "project: {}, component: {}, build: {}".format(self.project, self.credential, self.build)
        return data
