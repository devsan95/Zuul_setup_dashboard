import os

import arrow
import fire
import ruamel.yaml as yaml
import urllib3

from api import gerrit_rest
from api import log_api
from api import file_api
from api import mysql_api
from mod import integration_change

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = log_api.get_console_logger('OPF')


def set_is_submission(feature_id, info_path):
    search_sql = 'SELECT issue_key FROM t_issue WHERE summary like "%{}%" and status="open";'
    update_sql = 'UPDATE t_integration_issue_stream SET is_submission=1 WHERE integration_name="{}";'
    mysql_yaml = os.path.join(file_api.get_file_dir(info_path), 'ext_mysql.yaml')
    mysql = mysql_api.init_from_yaml(mysql_yaml, 'skytrack')
    mysql.init_database('skytrack')
    result = mysql.executor(search_sql.format(feature_id), output=True)
    if len(result) == 1:
        mysql.executor(update_sql.format(result[0][0]))
    else:
        log.error("Find {}'s jira ID faild.".format(feature_id))


class OperateFeature(object):
    def __init__(self, info_path, gerrit_path=None):
        self.info_path = info_path
        self.info = yaml.load(open(info_path, 'r'), Loader=yaml.Loader)
        if not gerrit_path:
            try:
                gerrit_path = self.get_gerrit_path_from_info(info_path)
            except Exception as e:
                log.debug(e)
        self.rest = gerrit_rest.init_from_yaml(gerrit_path)

    def get_gerrit_path_from_info(self, info_path):
        relative_path = self.info.get('gerrit')
        if not relative_path:
            raise Exception('No gerrit info in info')
        folder = file_api.get_file_dir(info_path)
        if os.path.isabs(relative_path):
            return relative_path
        return os.path.join(folder, relative_path)

    def get_feature_not_needed_list(self, config_yaml_path):
        data = yaml.load(open(config_yaml_path, 'r'), Loader=yaml.Loader)
        feature_not_needed_list = []
        comp_list = data['components']
        for comp in comp_list:
            if 'ric' in comp:
                if 'feature_needed' in comp and comp['feature_needed'] is False:
                    feature_not_needed_list.extend(comp['ric'].split(','))
        return feature_not_needed_list

    def add_by_path(self, feature_yaml_path):
        new_yaml = yaml.load(open(feature_yaml_path, 'r'), Loader=yaml.Loader)
        self.add(new_yaml)

    def add(self, yaml_obj):
        try:
            project = self.info.get('repo')
            ongoing_file = self.info.get('file').get('ongoing')
            feature_id = yaml_obj['feature_id']
            change_id, ticket_id, rest_id = self.rest.create_ticket(project, "", 'master', 'Adding {}'.format(feature_id), has_review_started=True)
            open_content = self.rest.get_file_content(ongoing_file, ticket_id)
            if not open_content:
                open_content = '[]'
            open_yaml = yaml.load(open_content, Loader=yaml.Loader)

            if not open_yaml:
                open_yaml = []
            for feature in open_yaml:
                if feature_id == feature['feature_id']:
                    raise Exception('Feature id {} exists!'.format(feature_id))
            open_yaml.append(yaml_obj)
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

    def generate(self, root_change_no, config_yaml_file, save_path=None, add=False):
        root_change = integration_change.RootChange(self.rest, root_change_no)
        create_feature_yaml = root_change.get_create_feature_yaml()
        if create_feature_yaml.lower() == 'false':
            print("create_feature_yaml is false,skip create feature yaml.")
            return
        try:
            root_change.get_topic()
        except AttributeError:
            log.info('No an integration change')
            return
        comp_change_list = root_change.get_all_changes_by_comments()
        comp_set = set()

        for comp_change_no in comp_change_list:
            comp_change = integration_change.IntegrationChange(self.rest, comp_change_no)
            try:
                comp_list = comp_change.get_components()
                feature_not_needed_list = self.get_feature_not_needed_list(config_yaml_file)
                for comp in comp_list:
                    if comp not in feature_not_needed_list:
                        comp_set.add(comp)
            except Exception as e:
                print(e)
                continue

        new_yaml_obj = dict()
        new_yaml_obj['feature_id'] = str(root_change.get_feature_id())
        new_yaml_obj['branch'] = str(root_change.get_info().get('branch'))
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
        if add:
            self.add(new_yaml_obj)

    def close(self, feature_id):
        try:
            project = self.info.get('repo')
            ongoing_file = self.info.get('file').get('ongoing')
            closed_file = self.info.get('file').get('closed')
            change_id, ticket_id, rest_id = self.rest.create_ticket(project, "", 'master', 'close feature <{}>'.format(feature_id), has_review_started=True)
            open_content = self.rest.get_file_content(ongoing_file, ticket_id)
            closed_content = self.rest.get_file_content(closed_file, ticket_id)
            open_yaml = yaml.load(open_content, Loader=yaml.Loader)
            close_yaml = yaml.load(closed_content, Loader=yaml.Loader)
            if not close_yaml:
                close_yaml = []
            original_open_yaml = open_yaml[:]
            edited = False
            for feature in original_open_yaml:
                if feature_id == feature['feature_id']:
                    if feature['status'] != 'ready':
                        log.debug('feature {} is not ready, cannot be closed'.format(feature_id))
                        continue
                    edited = True
                    open_yaml.remove(feature)
                    feature['status'] = 'done'
                    close_yaml.append(feature)
                    log.debug('Feature {} is moved to close'.format(feature_id))
            if edited:
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
                set_is_submission(feature_id, self.info_path)
                ticket_id = None
        finally:
            if ticket_id:
                try:
                    self.rest.abandon_change(ticket_id)
                except Exception as e:
                    print(e)

    def deliver(self, feature_id, component):
        try:
            find_feature_id = False
            need_close = True
            need_edit = False
            project = self.info.get('repo')
            ongoing_file = self.info.get('file').get('ongoing')
            change_id, ticket_id, rest_id = self.rest.create_ticket(
                project, "", 'master',
                'close component <{}> in feature <{}>'.format(component, feature_id), has_review_started=True)
            open_content = self.rest.get_file_content(ongoing_file, ticket_id)
            open_yaml = yaml.load(open_content, Loader=yaml.Loader)
            for feature in open_yaml:
                if feature_id == feature['feature_id']:
                    find_feature_id = True
                    comps = feature['components']
                    for comp in comps:
                        if comp['name'] == component:
                            if comp['delivered']:
                                log.debug('Comp {} in {} is already closed'.format(component, feature_id))
                            else:
                                need_edit = True
                                comp['delivered'] = True
                                log.debug('Comp {} in {} is about to close'.format(component, feature_id))
                        if not comp['delivered']:
                            need_close = False
                    if need_close:
                        feature['status'] = 'ready'
            if not find_feature_id:
                log.debug('Feature id {} does not exist'.format(feature_id))
                return
            if not need_edit:
                return
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

    def archive(self):
        try:
            project = self.info.get('repo')
            closed_file = self.info.get('file').get('closed')
            archive_folder = self.info.get('folder').get('archive')
            log.debug(archive_folder)
            timestr = arrow.utcnow().format('YYYYMMDDHHmmss')
            archive_path = os.path.join(archive_folder, 'archived_{}.yaml'.format(timestr))
            log.debug('Start archiving closed to <{}>'.format(archive_path))
            change_id, ticket_id, rest_id = self.rest.create_ticket(project, "", 'master', 'Archive closed feature to {}'.format(archive_path), has_review_started=True)
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
