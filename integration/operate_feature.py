import os

import arrow
import fire
import ruamel.yaml as yaml
import urllib3

from api import gerrit_rest
from api import log_api

from mod import integration_change

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = log_api.get_console_logger('OPF')


class OperateFeature(object):
    def __init__(self, gerrit_path, info_path):
        self.rest = gerrit_rest.init_from_yaml(gerrit_path)
        self.info = yaml.load(open(info_path, 'r'), Loader=yaml.Loader)

    def add(self, feature_yaml_path):
        try:
            project = self.info.get('repo')
            ongoing_file = self.info.get('file').get('ongoing')
            new_yaml = yaml.load(open(feature_yaml_path, 'r'), Loader=yaml.Loader)
            feature_id = new_yaml['feature_id']
            change_id, ticket_id, rest_id = self.rest.create_ticket(project, "", 'master', 'Adding {}'.format(feature_id))
            open_content = self.rest.get_file_content(ongoing_file, ticket_id)
            if not open_content:
                open_content = '[]'
            open_yaml = yaml.load(open_content, Loader=yaml.Loader)

            for feature in open_yaml:
                if feature_id == feature['feature_id']:
                    raise Exception('Feature id {} exists!'.format(feature_id))
            open_yaml.append(new_yaml)
            log.debug('Feature {} is about to be added'.format(feature_id))
            open_yaml_string = yaml.dump(open_yaml, Dumper=yaml.RoundTripDumper)
            self.rest.add_file_to_change(ticket_id, ongoing_file, open_yaml_string)
            self.rest.publish_edit(ticket_id)
            self.rest.review_ticket(ticket_id, 'merge',
                                    {'Verified': 1,
                                     'Code-Review': 2,
                                     'Gatekeeper': 1})
            self.rest.submit_change(ticket_id)
            print(self.rest.get_change_address(ticket_id))
            ticket_id = None
        finally:
            if ticket_id:
                try:
                    self.rest.abandon_change(ticket_id)
                except Exception as e:
                    print(e)

    def generate(self, root_change_no, save_path):
        root_change = integration_change.RootChange(self.rest, root_change_no)
        comp_change_list = root_change.get_all_changes_by_comments()
        comp_set = set()
        for comp_change_no in comp_change_list:
            comp_change = integration_change.IntegrationChange(self.rest, comp_change_no)
            comp_list = comp_change.get_components()
            for comp in comp_list:
                comp_set.add(comp)

        new_yaml_obj = dict()
        new_yaml_obj['feature_id'] = str(root_change.get_feature_id())
        new_yaml_obj['status'] = 'on-going'
        new_yaml_obj['components'] = list()
        for comp in comp_set:
            comp_dict = dict()
            comp_dict['name'] = str(comp)
            comp_dict['delivered'] = False
            new_yaml_obj['components'].append(comp_dict)
        new_yaml = yaml.dump(new_yaml_obj, Dumper=yaml.RoundTripDumper)
        log.debug('Generated Yaml is: \n{}'.format(new_yaml))
        if save_path:
            with open(save_path, 'w') as f:
                f.write(new_yaml)

    def close(self, feature_id):
        try:
            project = self.info.get('repo')
            ongoing_file = self.info.get('file').get('ongoing')
            closed_file = self.info.get('file').get('closed')
            change_id, ticket_id, rest_id = self.rest.create_ticket(project, "", 'master', 'close feature <{}>'.format(feature_id))
            open_content = self.rest.get_file_content(ongoing_file, ticket_id)
            closed_content = self.rest.get_file_content(closed_file, ticket_id)
            open_yaml = yaml.load(open_content, Loader=yaml.Loader)
            close_yaml = yaml.load(closed_content, Loader=yaml.Loader)
            if not close_yaml:
                close_yaml = []
            original_open_yaml = open_yaml[:]
            for feature in original_open_yaml:
                if feature_id == feature['feature_id']:
                    open_yaml.remove(feature)
                    close_yaml.append(feature)
                    log.debug('Feature {} is moved to close'.format(feature_id))
            open_yaml_string = yaml.dump(open_yaml, Dumper=yaml.RoundTripDumper)
            close_yaml_string = yaml.dump(close_yaml, Dumper=yaml.RoundTripDumper)
            self.rest.add_file_to_change(ticket_id, ongoing_file, open_yaml_string)
            self.rest.add_file_to_change(ticket_id, closed_file, close_yaml_string)
            self.rest.publish_edit(ticket_id)
            self.rest.review_ticket(ticket_id, 'merge',
                                    {'Verified': 1,
                                     'Code-Review': 2,
                                     'Gatekeeper': 1})
            self.rest.submit_change(ticket_id)
            print(self.rest.get_change_address(ticket_id))
            ticket_id = None
        finally:
            if ticket_id:
                try:
                    self.rest.abandon_change(ticket_id)
                except Exception as e:
                    print(e)

    def deliver(self, feature_id, component):
        try:
            need_close = True
            project = self.info.get('repo')
            ongoing_file = self.info.get('file').get('ongoing')
            change_id, ticket_id, rest_id = self.rest.create_ticket(
                project, "", 'master',
                'close component <{}> in feature <{}>'.format(component, feature_id))
            open_content = self.rest.get_file_content(ongoing_file, ticket_id)
            open_yaml = yaml.load(open_content, Loader=yaml.Loader)
            for feature in open_yaml:
                if feature_id == feature['feature_id']:
                    comps = feature['components']
                    for comp in comps:
                        if comp['name'] == component:
                            comp['delivered'] = True
                            log.debug('Comp {} in {} is about to close'.format(component, feature_id))
                        if not comp['delivered']:
                            need_close = False
            open_yaml_string = yaml.dump(open_yaml, Dumper=yaml.RoundTripDumper)
            self.rest.add_file_to_change(ticket_id, ongoing_file, open_yaml_string)
            self.rest.publish_edit(ticket_id)
            self.rest.review_ticket(ticket_id, 'merge',
                                    {'Verified': 1,
                                     'Code-Review': 2,
                                     'Gatekeeper': 1})
            self.rest.submit_change(ticket_id)
            print(self.rest.get_change_address(ticket_id))
            if need_close:
                self.close(feature_id)
            ticket_id = None
        finally:
            if ticket_id:
                try:
                    self.rest.abandon_change(ticket_id)
                except Exception as e:
                    print(e)

    def archive(self):
        try:
            project = self.info.get('repo')
            closed_file = self.info.get('file').get('closed')
            archive_folder = self.info.get('folder').get('archive')
            log.debug(archive_folder)
            timestr = arrow.utcnow().format('YYYYMMDDHHmmss')
            archive_path = os.path.join(archive_folder, 'archived_{}.yaml'.format(timestr))
            log.debug('Start archiving closed to <{}>'.format(archive_path))
            change_id, ticket_id, rest_id = self.rest.create_ticket(project, "", 'master', 'Archive closed feature to {}'.format(archive_path))
            closed_content = self.rest.get_file_content(closed_file, ticket_id)

            log.debug('Content to archive:')
            log.debug(closed_content)
            if len(closed_content) < 1000:
                log.debug('Too short, no need to archive')
                self.rest.abandon_change(ticket_id)
                return

            self.rest.add_file_to_change(ticket_id, archive_path, closed_content)
            self.rest.add_file_to_change(ticket_id, closed_file, '')
            self.rest.publish_edit(ticket_id)
            self.rest.review_ticket(ticket_id, 'merge',
                                    {'Verified': 1,
                                     'Code-Review': 2,
                                     'Gatekeeper': 1})
            self.rest.submit_change(ticket_id)
            print(self.rest.get_change_address(ticket_id))
            ticket_id = None
        finally:
            if ticket_id:
                try:
                    self.rest.abandon_change(ticket_id)
                except Exception as e:
                    print(e)


if __name__ == '__main__':
    fire.Fire(OperateFeature)
