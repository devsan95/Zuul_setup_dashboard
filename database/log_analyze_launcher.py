import os
import sys
import traceback

import arrow
import fire
import pytz
import requests
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from api import file_api
from model import LogAction


class DbHandler(object):
    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def init_db(self):
        LogAction.metadata.create_all(self.engine)

    def get_last_date(self):
        query = self.session.query(LogAction).order_by(sa.desc(LogAction.datetime))
        row = query.first()
        if not row:
            return None
        else:
            return row.datetime

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.rollback()


def _main(db_str, log_path=None, log_url=None, tz=None):
    if not tz:
        tz = 'America/New_York'
    if tz not in pytz.all_timezones:
        print('{} is not a valid timezone. Use default'.format(tz))
        tz = 'America/New_York'
    print('Using timezone of {}'.format(tz))
    db = DbHandler(db_str)
    db.init_db()
    dt = db.get_last_date()
    if not dt:
        raise Exception('Cannot find last datetime of log')
    dta = arrow.get(dt)
    print('Last log time')
    print(dta)
    print('To zuul server timezone')
    dta = dta.to(tz)
    print(dta)
    print('Plus one day')
    dta = dta.shift(days=+1)
    print(dta)
    res_path = None

    if log_path:
        print('Get the path')
        res_path = log_path + '.' + dta.format('YYYY-MM-DD')
        print(res_path)
        if os.path.exists(res_path):
            print('[{}] exists, continue'.format(res_path))
        else:
            raise Exception('[{}] does not exist'.format(res_path))

    if log_url:
        print('Get the url')
        print('Create tmp folder')
        tf = file_api.TempFolder()
        tmp_folder = tf.get_directory('log')
        print('Tmp folder is {}'.format(tmp_folder))
        res_path_ = os.path.join(tmp_folder, dta.format('YYYY-MM-DD'))
        log_url_ = log_url + '.' + dta.format('YYYY-MM-DD')
        print(log_url_)
        res = requests.get(log_url_)
        if res.ok:
            file_api.save_file(res.content, res_path_)
            res_path = res_path_
            print('Save log to {}'.format(res_path))
        else:
            raise Exception('Fetch URL {} failed, error is {}{}'.format(log_url_, res.status_code, res.content))

    print('begin to analyze logs')
    import zuul_log_analyze
    zuul_log_analyze.main(res_path, db_str, tz=tz)

    print('begin to calculate duration')
    import zuul_log_duration
    zuul_log_duration.main(db_str, 10000, 100)

    print('[LOGANA Result] All done, {}'.format(res_path))


if __name__ == '__main__':
    try:
        fire.Fire(_main)
    except Exception as e:
        print('=' * 20)
        print('Exception: {}'.format(str(e)))
        traceback.print_exc()
        print('=' * 20)
        print('[LOGANA Result] Exception, {}'.format(str(e)))
        sys.exit(2)
