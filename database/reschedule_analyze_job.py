import sys
import traceback

import fire
import sqlalchemy as sa
import urllib3
from sqlalchemy.orm import sessionmaker

# from api import gerrit_rest
from api import log_api
from model import get_reschedule_statistics_model, ZuulBuild, ZuulBuildset

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
        self.RescheduleAnalyze = None

    def init_db(self, table_name=None):
        if table_name:
            self.RescheduleAnalyze = get_reschedule_statistics_model(table_name)
        else:
            self.RescheduleAnalyze = get_reschedule_statistics_model()

    def query_blank(self, limit):
        query = self.session.query(self.RescheduleAnalyze.c_change,
                                   self.RescheduleAnalyze.c_patchset,
                                   self.RescheduleAnalyze.c_queue_item).distinct()
        query = query.filter(self.RescheduleAnalyze.c_job.is_(None),
                             self.RescheduleAnalyze.c_queue_item.isnot(None),
                             self.RescheduleAnalyze.c_status == 'fail')
        query = query.order_by(sa.desc(self.RescheduleAnalyze.id))
        query = query.limit(limit)
        result = query.all()
        return result

    def query_job(self, change, patchset, queue_item):
        query = self.session.query(ZuulBuildset, ZuulBuild).filter(
            ZuulBuild.buildset_id == ZuulBuildset.id, ZuulBuildset.change == change,
            ZuulBuildset.patchset == patchset, ZuulBuild.queue_item == queue_item,
            ZuulBuild.result != 'SUCCESS', ZuulBuild.result != 'CANCELLED', ZuulBuild.result != 'SKIPPED')
        query.order_by(ZuulBuild.id)
        result = query.first()
        if not result:
            log.debug('No Resule, %s, %s, %s', change, patchset, queue_item)
            return 'None', 'None'
        return result[1].job_name, result[1].result

    def update_job(self, change, patchset, queue_item, job_name, job_result):
        self.session.query(self.RescheduleAnalyze).filter(
            self.RescheduleAnalyze.c_change == change,
            self.RescheduleAnalyze.c_patchset == patchset,
            self.RescheduleAnalyze.c_queue_item == queue_item).update(
            {
                'c_job': job_name,
                'c_job_status': job_result
            })

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def main(db_str, gerrit_conf, db_str2=None, table_name=None, entry_num=5000, run_num=1):
    db = DbHandler(db_str)
    db2 = db
    # db for analyze table and db2 for zuul tables
    if db_str2:
        db2 = DbHandler(db_str2)
    # rest = gerrit_rest.init_from_yaml(gerrit_conf)
    try:
        db.init_db(table_name)

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
                        change = item[0]
                        patchset = item[1]
                        queue_item = item[2]
                        job_name, job_status = db2.query_job(change, patchset, queue_item)
                        db.update_job(change, patchset, queue_item, job_name, job_status)
                        log.debug('%s %s %s %s %s', change, patchset, queue_item, job_name, job_status)
                    except Exception as e:
                        log.debug(e)
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
