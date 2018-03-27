import os
import sys
import traceback

import arrow
import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

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


def _main(log_path, db_str):
    db = DbHandler(db_str)
    db.init_db()
    dt = db.get_last_date()
    if not dt:
        raise Exception('Cannot find last datetime of log')
    dta = arrow.get(dt)
    print('Last log time')
    print(dta)
    print('To zuul server timezone')
    dta = dta.to('America/New_York')
    print(dta)
    print('Plus one day')
    dta = dta.shift(days=+1)
    print(dta)
    print('Get the path')
    res_path = log_path + '.' + dta.format('YYYY-MM-DD')
    print(res_path)
    if os.path.exists(res_path):
        print('[{}] exists, continue'.format(res_path))
    else:
        raise Exception('[{}] does not exist'.format(res_path))

    print('begin to analyze logs')
    import zuul_log_analyze
    zuul_log_analyze.main(res_path, db_str)

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
