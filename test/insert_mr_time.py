import datetime
import logging
import re
import traceback

import arrow
import fire
import gitlab
import sqlalchemy as sa
import urllib3
import yaml
from sqlalchemy.dialects.mysql import DATETIME, TINYINT, VARCHAR
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from api import gerrit_rest

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger('bb')
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
log.addHandler(ch)
log.setLevel(logging.DEBUG)

reg_mr = re.compile(r'See merge request (?P<project>[^\/]*\/[^\/!]*)?!(?P<mrid>\d*)')
reg_commit = re.compile(r'REVISION = \"(?P<commit>[^\"]*)\"')
reg_repo = re.compile(r'GIT_REPO = \"git://[^/@]*@(?P<site>[^/@]*)/(?P<project>.*)\.git\"')

module_list = [
    'siteoam',
    'nodeoam',
    'racoam',
    'sloader',
    'nloader',
    'oamagent',
    'node-js'
]

ModelBase = declarative_base()


class CCI_No_Zuul(ModelBase):
    __tablename__ = 't_cci_no_zuul'

    id = sa.Column(sa.Integer, primary_key=True)

    commit = sa.Column(VARCHAR(50), server_default='')
    start_time = sa.Column(DATETIME, server_default='')
    end_time = sa.Column(DATETIME, server_default='')
    stage = sa.Column(VARCHAR(25), server_default='')
    result = sa.Column(TINYINT(1), server_default='')
    create_time = sa.Column(DATETIME, server_default='')
    modify_time = sa.Column(DATETIME, server_default='')


class DbHandler(object):
    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def update_commit(self, commit, start_time, end_time):
        # search if bb  exists
        if self.if_commit_exist(commit):
            # if exists, pass
            log.debug('{} exists, skip'.format(commit))
        else:
            # else add
            self._insert_commit_date(commit, start_time, end_time)
            log.debug('Insert {}'.format(commit))

    def query_commit(self, commit):
        return self.session.query(CCI_No_Zuul).filter(CCI_No_Zuul.commit == commit).all()

    def if_commit_exist(self, commit):
        return self.session.query(sa.exists().where(CCI_No_Zuul.commit == commit)).scalar()

    def _insert_commit_date(self, commit, start_time, end_time):
        entry = CCI_No_Zuul()
        entry.commit = commit
        entry.start_time = arrow.get(start_time).datetime
        entry.end_time = arrow.get(end_time).datetime
        entry.stage = 'check'
        entry.result = 1
        self.session.add(entry)
        self.session.flush()

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def test():
    glapi = gitlab.Gitlab('http://baltig.nsn-net.net',
                          private_token='8a2Kj9ms7Do6GCS3qQHA')
    project = glapi.projects.get('5g/siteoam')
    print(project.name)

    commit = project.commits.get('f8eb4bdc2719e4683e68a01fc6c29dd504e14a4b')
    print(dir(commit))
    print(commit.attributes['message'])

    match_result = reg_mr.search(commit.attributes['message'])
    if not match_result:
        raise Exception('Cannot find merge request in: \n{}'.format(commit.attributes['message']))
    print(match_result.group('mrid'))

    mr = project.mergerequests.get(match_result.group('mrid'))
    print(mr.attributes['created_at'])
    print(mr.attributes['merged_at'])


def get_mr_time_by_commit(glapi, site, project, commit):
    if site not in glapi:
        raise Exception('{} not inited'.format(site))
    gl = glapi[site]
    project = gl.projects.get(project)
    commit = project.commits.get(commit)
    match_result = reg_mr.search(commit.attributes['message'])
    if not match_result:
        raise Exception('Cannot find merge request in: \n{}'.format(commit.attributes['message']))
    mr = project.mergerequests.get(match_result.group('mrid'))
    return mr.attributes['created_at'], mr.attributes['merged_at']


def process_mr(file_content):
    mc = reg_commit.search(file_content)
    mp = reg_repo.search(file_content)
    commit = mc.group('commit')
    project = mp.group('project')
    site = mp.group('site')
    log.debug('site is {}'.format(site))
    log.debug('commit is {}'.format(commit))
    log.debug('project is {}'.format(project))
    return site, project, commit


def run(gerrit_yaml_path, db_str, gitlab_yaml_path, init=0, count=5, after='2018-8-13', skip_error=True):
    rest = gerrit_rest.init_from_yaml(gerrit_yaml_path)
    glapi = {}
    with open(gitlab_yaml_path) as f:
        obj = yaml.load(f)
        for key, item in obj.items():
            glapi[key] = gitlab.Gitlab(item['url'], item['token'])
    start = init
    error_list = []
    while True:
        try:
            log.info('new cycle skip {}'.format(start))
            result = rest.query_ticket(
                'project:MN/5G/COMMON/meta-5g '
                'status:merged after:{}'.format(after),
                count=count,
                start=start)
            db = DbHandler(db_str)
            for change in result:
                change_no = change['_number']
                merge_time = datetime.datetime.strptime(
                    change.get('submitted'),
                    '%Y-%m-%d %H:%M:%S.%f000')
                log.debug(
                    'change [{}] merge time [{}]'.format(change_no, merge_time))
                file_list = rest.get_file_list(change_no)
                for filepath, fileinfo in file_list.items():
                    if fileinfo.get('status') == 'A':
                        for module in module_list:
                            if module in filepath:
                                try:
                                    log.debug('Process {}'.format(filepath))
                                    file_content = \
                                        rest.get_file_content(filepath, change_no)
                                    site, project, commit = process_mr(file_content)
                                    if db.if_commit_exist(commit):
                                        log.debug('{} exists, skip query gitlab'.format(commit))
                                    else:
                                        created, merged = \
                                            get_mr_time_by_commit(glapi, site, project, commit)
                                        db.update_commit(commit, created, merged)
                                    log.debug('---')
                                except Exception as e:
                                    if skip_error:
                                        log.debug(e)
                                        traceback.print_exc()
                                        error_list.append((change_no, filepath, site, project, commit, str(e)))
                                    else:
                                        raise e

            db.commit()
            start += len(result)
            if not result[-1].get('_more_changes'):
                log.info('no more change')
                break
        except Exception as e:
            log.debug(e)
            traceback.print_exc()
            raise

    if error_list:
        for e in error_list:
            for p in e:
                print(p)
            print('\n')


if __name__ == '__main__':
    fire.Fire(run)
