import sys
import traceback

import fire
import sqlalchemy as sa
import urllib3
from sqlalchemy.orm import sessionmaker

from api import gerrit_rest
from api import log_api
from model import get_gate_statistics_model, get_reschedule_statistics_model

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = log_api.get_console_logger('ZUUL_LOG_DURATION')


class DbHandler(object):
    start_strings = ['added to queue', 'cancel job']
    end_strings = ['remove from queue', 'resetting for nnfi',
                   'resetting for not merge']
    break_strings = ['resetting for nnfi', 'resetting for not merge']

    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.GateStatistics = None
        self.RescheduleStatistic = None

    def init_db(self, table_name=None, table_name2=None):
        if table_name:
            self.GateStatistics = get_gate_statistics_model(table_name)
        else:
            self.GateStatistics = get_gate_statistics_model('log_duration')

        if table_name2:
            self.RescheduleStatistic = get_reschedule_statistics_model(table_name2)
        else:
            self.RescheduleStatistic = get_reschedule_statistics_model('t_reschedule_statistics')

    def query_blank(self, limit):
        query = self.session.query(self.GateStatistics)
        query = query.filter(sa.or_(self.GateStatistics.branch.is_(None),
                                    self.GateStatistics.project.is_(None)))
        query = query.order_by(sa.desc(self.GateStatistics.id))
        query = query.limit(limit)
        result = query.all()
        return result

    def query_blank2(self, limit):
        query = self.session.query(self.RescheduleStatistic)
        query = query.filter(sa.or_(self.RescheduleStatistic.branch.is_(None),
                                    self.RescheduleStatistic.project.is_(None)))
        query = query.order_by(sa.desc(self.RescheduleStatistic.id))
        query = query.limit(limit)
        result = query.all()
        return result

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def main(db_str, gerrit_conf, table_name='t_gate_statistics', table_name2='t_reschedule_statistics', entry_num=5000, run_num=1):
    db = DbHandler(db_str)
    rest = gerrit_rest.init_from_yaml(gerrit_conf)
    try:
        db.init_db(table_name, table_name2)

        log.debug(table_name)
        for i in range(0, run_num):
            try:
                log.debug('Run %s', i + 1)
                log.debug('')
                data_list = db.query_blank(entry_num)
                if not data_list:
                    log.debug('No more need to update, break')
                    break
                for item in data_list:
                    try:
                        changeset = item.changeset
                        change = changeset.split(',', 2)[0]
                        info = rest.get_change(change)
                        log.debug('%s %s %s', info['_number'], info['project'], info['branch'])
                        item.branch = info['branch']
                        item.project = info['project']
                    except Exception as e:
                        log.debug(e)
                        if 'Status code is [404]' in str(e):
                            item.branch = 'NOT_FOUND'
                            item.project = 'NOT_FOUND'
                        traceback.print_exc()
                log.debug('')
                log.debug('Committing...')
                db.commit()
                log.debug('--------')
            except Exception as e:
                log.debug(e)
                db.rollback()
                traceback.print_exc()

        log.debug(table_name2)
        for i in range(0, run_num):
            try:
                log.debug('Run %s', i + 1)
                log.debug('')
                data_list = db.query_blank2(entry_num)
                if not data_list:
                    log.debug('No more need to update, break')
                    break
                for item in data_list:
                    try:
                        change = item.change
                        info = rest.get_change(change)
                        log.debug('%s %s %s', info['_number'], info['project'], info['branch'])
                        item.branch = info['branch']
                        item.project = info['project']
                    except Exception as e:
                        log.debug(e)
                        if 'Status code is [404]' in str(e):
                            item.branch = 'NOT_FOUND'
                            item.project = 'NOT_FOUND'
                        traceback.print_exc()
                log.debug('')
                log.debug('Committing...')
                db.commit()
                log.debug('--------')
            except Exception as e:
                log.debug(e)
                db.rollback()
                traceback.print_exc()
    except Exception as ex:
        log.debug('Exception occurs:')
        log.debug(ex)
        log.debug('rollback')
        db.rollback()
        traceback.print_exc()
        raise ex


if __name__ == '__main__':
    try:
        fire.Fire(main)
    except Exception as e:
        log.debug('Exception: {}'.format(str(e)))
        traceback.print_exc()
        sys.exit(2)
