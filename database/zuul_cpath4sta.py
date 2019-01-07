import sys
import datetime
import logging
import argparse
import pymysql
import collections

log = logging.getLogger(__file__)

# DB_HOST = '10.157.165.0'
# DB_USER = 'root'
# DB_PASS = 'zuul_common'
# DB_TEST = 'zuul-test-common'

DB_HOST = '10.159.10.111'
DB_USER = 'root'
DB_PASS = 'hzscmzuul'
DB_TEST = 'zuul'

SDB_HOST = '10.157.163.176'
SDB_USER = 'skytrack_dev'
SDB_PASS = 'dev123'
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

    def _get_records_amount(self):
        with self.connection.cursor() as cursor:
            sql = "select count(*) from item_jobtree"
            cursor.execute(sql)
            result = cursor.fetchone()
        return result['count(*)']

    def get_records(self, number=0):
        condstr = 'where id > {}'.format(self._get_records_amount() - number) if number else ''
        with self.connection.cursor() as cursor:
            sql = "select * from item_jobtree {}".format(condstr)
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
            cpath = ''
            subsystem = ''
            self.datas[':'.join([chps, qit])] = dict(pipeline=pipeline,
                                                     change=chps,
                                                     queueitem=qit,
                                                     builds=builds,
                                                     jobtree=jobtree,
                                                     cpath=cpath,
                                                     subsystem=subsystem)

    def _get_queueitems(self, chps):
        with self.connection.cursor() as cursor:
            sql = "select queueitem from item_jobtree where changeitem='{}'".format(chps)
            cursor.execute(sql)
            result = cursor.fetchall()
            log.debug("Queueitems: {}".format(result))
            return [res['queueitem'] for res in result]

    def _get_all_queueitems(self):
        with self.connection.cursor() as cursor:
            sql = "select queueitem from item_jobtree"
            cursor.execute(sql)
            result = cursor.fetchall()
            log.debug("Queueitems: {}".format(result))
            return [res['queueitem'] for res in result]

    def _get_builds(self, qitem):
        with self.connection.cursor() as cursor:
            sql = "select builds from item_jobtree where queueitem='{}'".format(qitem)
            cursor.execute(sql)
            result = cursor.fetchone()
            log.debug("Builds: {}".format(result))
            return result

    def _get_longest_build(self, builds):
        try:
            longest = max([vitem[-1] for vitem in builds.values() if vitem[-1]])
        except Exception as err:
            longest = ''
            log.debug(str(err))
            log.debug('Selected data build time info is not complete.')
            # raise Exception('Selected data build time info is not complete.')
        lbuild = ''
        for k, v in builds.items():
            if v[-1] == longest:
                lbuild = k
                break
        return lbuild

    def _get_trees(self, qitem):
        with self.connection.cursor() as cursor:
            sql = "select jobtree from item_jobtree where queueitem='{}'".format(qitem)
            cursor.execute(sql)
            result = cursor.fetchone()
            # log.debug("Trees: {}".format(result))
            return result

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

    def update_skytrack(self, *sdata):
        try:
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO t_critical_path " \
                      "(pipeline,queueitem,changeitem,timeslot,path,subsystem,create_time,update_time)" \
                      " VALUES {}".format(sdata)
                log.debug(sql)
                cursor.execute(sql)
            self.connection.commit()
        except Exception as err:
            log.debug(str(err))
            self.connection.rollback()
            self.connection.close()

    def update_test(self, *sdata):
        try:
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO item_jobtree (pipeline, queueitem, changeitem, builds, jobtree)" \
                      " VALUES {}".format(sdata)
                log.debug(sql)
                cursor.execute(sql)
            self.connection.commit()
        except Exception as db_err:
            log.debug(str(db_err))
            self.connection.rollback()
            self.connection.close()


class Runner(object):
    def __init__(self):
        self.parser = self.get_parser()
        self.jto_args = None
        self.other_args = None
        self.parse_arguments()

    def get_parser(self):
        parser = argparse.ArgumentParser(description='Used for job find critical path')
        parser.add_argument('-p', '--patchset', dest='ps', help='change and patch-set')
        parser.add_argument('-q', '--queueitem', dest='qitem', help='queue item of change')
        parser.add_argument('-l', '--lines', dest='lines', help='latest lines data')
        parser.add_argument('-a', '--all', dest='all', action='store_true', help='all items')
        parser.add_argument('-d', '--debug', dest='debug', action='store_true', help="logging level ")
        return parser

    def parse_arguments(self):
        self.jto_args, self.other_args = self.parser.parse_known_args()

    def get_buildtime(self, cpath, builds):
        timeinfo = list()
        timeslots = list()
        for bu in cpath.split(' -> '):
            if builds.get(bu):
                timeslots.append(builds[bu][1:4])
            else:
                timeslots.append([0, 0, 0])
        try:
            totaltime = str(int(timeslots[-1][2]) - int(timeslots[0][0]))
        except Exception as err:
            log.debug(str(err))
            totaltime = 'N/A'
            log.debug('Unvalid time exist. ')
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
        timeinfo.append(totaltime)
        return ','.join(timeinfo)

    def run(self):
        if self.jto_args.debug:
            logging.basicConfig(level=logging.DEBUG,
                                format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                                datefmt='%a, %d %b %Y %H:%M:%S')

        if not self.jto_args.all and not self.jto_args.ps:
            raise Exception("Please input change and patchset.")
        input_lines = self.jto_args.lines if self.jto_args.lines else 3000

        jto_ins = JobTreeOper(DB_HOST, DB_USER, DB_PASS, DB_TEST)
        log.debug("Connection {0} to ZUUL db {1}".format(jto_ins.connection, DB_TEST))

        jto_ins.get_records(input_lines)
        for k, v in jto_ins.datas.items():
            log.debug(v['builds'])
            log.debug(v['jobtree'])
            cpa = jto_ins.critical_path(v['builds'], v['jobtree'])
            jenkins = 'NONE'
            for buildset in v['builds'].values():
                if buildset[0].startswith('http'):
                    jenkins = buildset[0].split('/')[2]
                    break
            if cpa and cpa[0].count(r'MASTER_PROD/UPLANE'):
                subs = jenkins + ',' + 'UPLANE'
            elif cpa and cpa[0].count(r'MASTER_PROD/CPLANE'):
                subs = jenkins + ',' + 'CPLANE'
            else:
                subs = jenkins + ',' + 'Reserved'
            v['cpath'] = cpa
            v['subsystem'] = subs

        sky_ins = JobTreeOper(SDB_HOST, SDB_USER, SDB_PASS, SDB_TEST)
        log.debug("Connection {0} to skytrack db {1}".format(jto_ins.connection, SDB_TEST))
        cutime = str(datetime.datetime.now())[:19]
        for k, v in jto_ins.datas.items():
            if v['cpath']:
                log.debug('Create time: {}'.format(cutime))
                timeslot = self.get_buildtime(v['cpath'][0], v['builds'])
                log.debug("{0},{1},{2},{3},{4},{5}".format(v['pipeline'], v['queueitem'],
                                                           v['change'], timeslot, v['cpath'][0], v['subsystem']))
                sky_ins.update_skytrack(v['pipeline'],
                                        v['queueitem'],
                                        v['change'],
                                        timeslot,
                                        v['cpath'][0],
                                        v['subsystem'],
                                        cutime,
                                        cutime)


sys.exit(Runner().run())
