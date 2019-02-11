import sys
import copy
import logging
import argparse
import pymysql
import collections
import datetime

log = logging.getLogger(__file__)

# DB_HOST = '10.157.165.0'
# DB_USER = 'root'
# DB_PASS = 'zuul_common'
# DB_TEST = 'zuul_test'

DB_HOST = '10.159.10.111'
DB_USER = 'root'
DB_PASS = 'hzscmzuul'
DB_TEST = 'zuul'

SDB_HOST = '10.157.163.176'
SDB_USER = 'skytrack_dev'
SDB_PASS = 'dev_666'
SDB_TEST = 'skytrack'


# SDB_HOST = '10.157.165.0'
# SDB_USER = 'root'
# SDB_PASS = 'zuul_common'
# SDB_TEST = 'zuul-test-common'

class JobTreeOper(object):
    def __init__(self, host, username, password, test_db):
        self.host = host
        self.username = username
        self.password = password
        self.db = test_db
        self.connection = self._connect()
        self.datas = collections.defaultdict(dict)

    def _connect(self):
        conn = pymysql.connect(host=self.host,
                               user=self.username,
                               password=self.password,
                               db=self.db,
                               # charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor
                               )
        return conn

    def _close(self):
        if self.connection:
            self.connection.close()
        else:
            log.debug("No connection exist.")

    def _get_records_amount(self, tdate=''):
        with self.connection.cursor() as cursor:
            sql = "select count(*) from item_jobtree where " \
                  "created_at > str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(tdate)
            cursor.execute(sql)
            result = cursor.fetchone()
        return result['count(*)']

    def get_records(self, tdate=''):
        with self.connection.cursor() as cursor:
            sql = "select * from item_jobtree where created_at " \
                  "> str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(tdate)
            cursor.execute(sql)
            results = cursor.fetchall()
        if not results:
            raise Exception('No record found.')
        for res in results:
            chps = res.get('changeitem')
            qit = res.get('queueitem')
            pipeline = res.get('pipeline')
            builds = eval(res.get('builds').replace("defaultdict(<type 'list'>, ", '')[:-1])
            jobtree = eval(res.get('jobtree'))
            project = res.get('project')
            branch = res.get('branch')
            cpath = ''
            subsystem = ''
            timeslots = ''
            self.datas[':'.join([chps, qit])] = dict(pipeline=pipeline,
                                                     change=chps,
                                                     queueitem=qit,
                                                     builds=builds,
                                                     jobtree=jobtree,
                                                     project=project,
                                                     branch=branch,
                                                     cpath=cpath,
                                                     subsystem=subsystem,
                                                     timeslots=timeslots)

    def _get_longest_build(self, builds):
        try:
            longest = max([vitem[-1] for vitem in builds.values() if vitem[-1]])
        except Exception as err:
            longest = ''
            log.debug(str(err))
            log.debug('Selected data build time info is not complete.')
        lbuild = ''
        for k, v in builds.items():
            if v[-1] == longest:
                lbuild = k
                break
        return lbuild

    def get_paths(self, btree):

        def _get_dict_path(d):
            paths = list()
            for k, v in d.items():
                for inv in v:
                    if isinstance(inv, str):
                        paths.append(' -> '.join([k, inv]))
                    elif isinstance(inv, dict):
                        invpath = _get_dict_path(inv)
                        for tmpath in invpath:
                            paths.append(' -> '.join([k, tmpath]))
            return paths

        allpaths = list()
        for build in btree:
            if isinstance(build, dict):
                inv = _get_dict_path(build)
                allpaths.extend(inv)
            elif isinstance(build, str):
                allpaths.append(build)
        return allpaths

    def critical_path(self, builds, btree):
        cpath = list()
        lbuild = self._get_longest_build(builds)
        allpaths = self.get_paths(btree)
        for p in allpaths:
            if p.endswith(lbuild):
                cpath.append(p)
        return cpath

    def update_data(self):
        """
        update critical path and the timeslots, each build waiting time and running time.
        :param builds:
        :param cpath:
        :return:
        """
        for k, v in self.datas.items():
            dbuilds = v['builds']
            timeinfo = list()
            timeslots = list()
            cpath = self.critical_path(dbuilds, v['jobtree'])
            if not cpath:
                continue
            cpath_ls = cpath[0].split(' -> ')
            tmp_ls = copy.deepcopy(cpath_ls)
            log.debug(k)
            log.debug(cpath_ls)

            for i, bui in enumerate(cpath_ls):
                if i < len(cpath_ls) - 1:
                    if dbuilds[bui][-1] > dbuilds[cpath_ls[i + 1]][1]:
                        try:
                            if dbuilds[bui][-1] > dbuilds[cpath_ls[i + 1]][-1]:
                                tmp_ls.remove(cpath_ls[i + 1])
                            else:
                                tmp_ls.remove(bui)
                        except Exception as re_err:
                            log.debug(re_err)
            v['cpath'] = ' -> '.join(tmp_ls)

            for bu in tmp_ls:
                if dbuilds.get(bu):
                    timeslots.append(dbuilds[bu][1:4])
                else:
                    raise Exception("Unfound cpath build, must be error")
            try:
                totaltime = str(int(timeslots[-1][2]) - int(timeslots[0][0]))
            except Exception as err:
                log.debug(str(err))
                totaltime = 'N/A'
                log.debug('Unvalid time exist. ')
            timeinfo.append(totaltime)

            for i, ts in enumerate(timeslots):
                try:
                    base = int(timeslots[i - 1][2]) if i else int(ts[0])
                except Exception as ts_err:
                    log.debug(str(ts_err))
                    base = 'N/A'
                try:
                    waittime = str(int(ts[1]) - base)
                except Exception as wt_err:
                    log.debug(str(wt_err))
                    waittime = 'N/A'
                timeinfo.append(waittime)
                try:
                    runtime = str(int(ts[2]) - int(ts[1]))
                except Exception as rt_err:
                    log.debug(str(rt_err))
                    runtime = 'N/A'
                timeinfo.append(runtime)
            v['timeslots'] = ','.join(timeinfo)

    def update_skytrack(self, sdata):
        try:
            self.connection.ping(reconnect=True)
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO t_critical_path " \
                      "(pipeline,queueitem,changeitem,timeslot,path,subsystem,c_project,c_branch,end_time)" \
                      " VALUES ('{0}','{1}','{2}','{3}','{4}','{5}','{6}','{7}',{8})".format(*sdata)
                log.debug(sql)
                cursor.execute(sql)
            self.connection.commit()
        except Exception as err:
            log.debug(str(err))
            # self.connection.rollback()
            # self.connection.close()


class Runner(object):
    def __init__(self):
        self.parser = self.get_parser()
        self.jto_args = None
        self.other_args = None
        self.parse_arguments()

    def get_parser(self):
        parser = argparse.ArgumentParser(description='Used for job find critical path')
        parser.add_argument('-t', '--tdate', dest='tdate', help="time date")
        parser.add_argument('-d', '--debug', dest='debug', action='store_true', help="logging level")
        return parser

    def parse_arguments(self):
        self.jto_args, self.other_args = self.parser.parse_known_args()

    def run(self):
        if self.jto_args.debug:
            logging.basicConfig(level=logging.DEBUG,
                                format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                                datefmt='%a, %d %b %Y %H:%M:%S')
        if self.jto_args.tdate:
            tdate = "{} 00:00:00".format(self.jto_args.tdate.strip())
        else:
            tdate = datetime.datetime.now().strftime("%Y-%m-%d 00:00:00")
        jto_ins = JobTreeOper(DB_HOST, DB_USER, DB_PASS, DB_TEST)
        log.debug("Connection {0} to ZUUL db {1}".format(jto_ins.connection, DB_TEST))
        jto_ins.get_records(tdate)
        jto_ins.update_data()
        log.debug(jto_ins.datas)

        try:
            sky_ins = JobTreeOper(SDB_HOST, SDB_USER, SDB_PASS, SDB_TEST)
            log.debug("Connection {0} to skytrack db {1}".format(jto_ins.connection, SDB_TEST))
            for k, v in jto_ins.datas.items():
                if v['cpath']:
                    log.debug("{0},{1},{2},{3},{4},{5}".format(v['pipeline'], v['queueitem'],
                                                               v['change'], v['timeslots'],
                                                               v['cpath'], v['subsystem']))
                    try:
                        sky_ins.update_skytrack((v['pipeline'],
                                                v['queueitem'],
                                                v['change'],
                                                v['timeslots'],
                                                v['cpath'],
                                                v['subsystem'],
                                                v['project'],
                                                v['branch'],
                                                "str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(tdate)))
                    except Exception as sky_err:
                        log.debug(sky_err)
                        continue
        except Exception as sky_err:
            log.debug(str(sky_err))
        finally:
            sky_ins._close()


sys.exit(Runner().run())
