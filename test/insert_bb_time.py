import datetime
import logging

import fire
import sqlalchemy as sa
import urllib3
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from api import gerrit_rest

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger('bb')
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
log.addHandler(ch)
log.setLevel(logging.DEBUG)


ModelBase = declarative_base()


class PciBB(ModelBase):
    __tablename__ = 't_pci_bb'
    id = sa.Column(sa.Integer, primary_key=True)

    cb_package = sa.Column(sa.String(50), server_default='abc')
    bb_name = sa.Column(sa.String(1000), server_default='abc')
    component = sa.Column(sa.String(50), server_default='abc')
    release_time = sa.Column(sa.DATETIME, server_default='abc')
    create_time = sa.Column(sa.DATETIME, server_default='abc')
    modify_time = sa.Column(sa.DATETIME, server_default='abc')


class DbHandler(object):
    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def update_bb(self, bb, time):
        # search if bb  exists
        qlist = self.query_bb(bb)
        if qlist:
            # if exists, update
            self._update_bb_date(qlist, time)
        else:
            # else add
            self._insert_bb_date(bb, time)

    def query_bb(self, bb):
        return self.session.query(PciBB).filter(PciBB.bb_name == bb).all()

    def _update_bb_date(self, pbb_list, time):
        for pbb in pbb_list:
            pbb.release_time = time

    def _insert_bb_date(self, bb, time):
        pbb = PciBB()
        pbb.bb_name = bb
        pbb.release_time = time
        self.session.add(pbb)

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def run(gerrit_yaml_path, db_str, init=0, count=50):
    rest = gerrit_rest.init_from_yaml(gerrit_yaml_path)
    start = init
    while True:
        try:
            log.info('new cycle skip {}'.format(start))
            result = rest.query_ticket(
                'project:MN/5G/COMMON/meta-5g status:merged after:2018-8-6',
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
                        if filepath.endswith('.bb'):
                            bbname = filepath.split('/')[-1]
                            log.debug('File Added: {} {}'.format(bbname, filepath))
                            db.update_bb(bbname, merge_time)

            db.commit()
            start += len(result)
            if not result[-1].get('_more_changes'):
                log.info('no more change')
                break

        except Exception as e:
            log.debug(e)


if __name__ == '__main__':
    fire.Fire(run)
