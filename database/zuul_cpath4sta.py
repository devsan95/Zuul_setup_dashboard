import sys
import ast
import pytz
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
            builds = ast.literal_eval(res.get('builds').replace("defaultdict(<type 'list'>, ", '')[:-1])
            jobtree = ast.literal_eval(res.get('jobtree'))
            project = res.get('project')
            branch = res.get('branch')
            cpath = ''
            subsystem = ''
            timeslots = ''
            pipelineWaiting = ''
            firstJobLaunch = ''
            self.datas[':'.join([chps, qit])] = dict(pipeline=pipeline,
                                                     change=chps,
                                                     queueitem=qit,
                                                     builds=builds,
                                                     jobtree=jobtree,
                                                     project=project,
                                                     branch=branch,
                                                     cpath=cpath,
                                                     subsystem=subsystem,
                                                     pipelineWaiting=pipelineWaiting,
                                                     firstJobLaunch=firstJobLaunch,
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

    def get_layer_jobs(self, btree):
        ljob = collections.defaultdict(list)
        tmpbt = btree
        i = 0
        while tmpbt:
            ttmpbt = list()
            for b in tmpbt:
                if isinstance(b, str):
                    ljob[i].append(b)
                if isinstance(b, dict):
                    ljob[i].append(b.keys()[0])
                    ttmpbt.extend(b.values()[0])
            i += 1
            tmpbt = ttmpbt
        return ljob

    def critical_path(self, builds, btree):
        cpath = list()
        lbuild = self._get_longest_build(builds)
        allpaths = self.get_paths(btree)
        ljobs = self.get_layer_jobs(btree)
        for p in allpaths:
            if p.endswith(lbuild):
                cpath.append(p)
        return cpath, ljobs

    def update_data(self):
        """
        update critical path and the timeslots, each build waiting time and running time.
        :param builds:
        :param cpath:
        :return:
        """

        def _get_final_cpath(cpath, ljobs, buildsinfo):
            def _reform_final_path(o_path, c_path, ljobs):
                def _item_index_in_o_path(path, job):
                    for i, item in enumerate(path.split(' -> ')):
                        if item == job:
                            return i
                    return 0

                def _item_first_run_layer(job, layerjobs):
                    ljobitems = layerjobs.items()
                    sorted_ljobsitems = sorted(ljobitems, key=lambda x: x[0])
                    for titem in sorted_ljobsitems:
                        if job in titem[1]:
                            return titem[0]
                    return 0

                opath = o_path.split(' -> ')
                cpath = c_path.split(' -> ')
                fpath = c_path.split(' -> ')
                for i, cj in enumerate(cpath):
                    if i:
                        preJob = cpath[i - 1]
                        preJobIndex = _item_index_in_o_path(o_path, preJob)
                        curJobIndex = _item_index_in_o_path(o_path, cj)
                        curJobIndexInCPath = _item_index_in_o_path(c_path, cj)
                        if (curJobIndex - preJobIndex) == 1:
                            continue
                        firstRunJobLayer = _item_first_run_layer(cj, ljobs)
                        if firstRunJobLayer > i:
                            for j in range(firstRunJobLayer - i):
                                if (preJobIndex + j + 1) < len(opath) - 1:
                                    addJob = opath[preJobIndex + j + 1]
                                    if addJob not in fpath:
                                        fpath.insert(curJobIndexInCPath, addJob)
                return fpath

            fcpath = list()
            cpath_ls = cpath.split(' -> ')
            for i, p in enumerate(cpath_ls):
                if not i:
                    fcpath.append(p)
                else:
                    tls = list()
                    for j in range(i):
                        tls.extend(ljobs[j])
                    if p not in tls:
                        fcpath.append(p)
                    else:
                        pl = 0
                        ttls = list()
                        for firstRun in range(i):
                            if p in ljobs[firstRun]:
                                pl = firstRun
                                break
                        for h in range(pl, i):
                            ttls.append(cpath_ls[h])
                        if ttls:
                            et = buildsinfo[ttls[-1]][3]
                            if buildsinfo[p][3] > et:
                                fcpath.append(p)
                                for m in ttls:
                                    try:
                                        fcpath.remove(m)
                                    except Exception as re_err:
                                        log.debug(str(re_err))
                                        log.debug("Maybe already removed.")
            c_path = ' -> '.join(fcpath)
            f_cpath = _reform_final_path(cpath, c_path, ljobs)
            timeslots = list()
            try:
                total = int(buildsinfo[f_cpath[-1]][3] - buildsinfo[f_cpath[0]][1])
                firstJobLaunch = buildsinfo[f_cpath[0]][1]
            except Exception as t_err:
                total = 'N/A'
                firstJobLaunch = 'N/A'
                log.debug(str(t_err))
            timeslots.append(total)
            for n, fcp in enumerate(f_cpath):
                try:
                    if not n:
                        t0 = 0
                        t1 = int(buildsinfo[fcp][2] - buildsinfo[fcp][1])
                        t2 = int(buildsinfo[fcp][3] - buildsinfo[fcp][2])
                    else:
                        t0 = int(buildsinfo[fcp][1] - buildsinfo[f_cpath[n - 1]][3])
                        t1 = int(buildsinfo[fcp][2] - buildsinfo[fcp][1])
                        t2 = int(buildsinfo[fcp][3] - buildsinfo[fcp][2])
                except Exception as t_err:
                    t0 = 'N/A'
                    t1 = 'N/A'
                    t2 = 'N/A'
                    log.debug(str(t_err))
                timeslots.append(t0)
                timeslots.append(t1)
                timeslots.append(t2)
            dyn_path = ' -> '.join(f_cpath)
            tlstr = ','.join([str(tls) for tls in timeslots])
            return dyn_path, firstJobLaunch, tlstr

        for k, v in self.datas.items():
            dbuilds = v['builds']
            patadata = self.critical_path(dbuilds, v['jobtree'])
            cpath = patadata[0]
            ljobs = patadata[1]
            if not cpath:
                continue

            if cpath and (cpath[0].count(r'MASTER_PROD/UPLANE') or cpath[0].count(r'MASTER/GNB/UPLANE')):
                subs = 'UPLANE'
            elif cpath and (cpath[0].count(r'MASTER_PROD/CPLANE') or cpath[0].count(r'MASTER/GNB/CPLANE')):
                subs = 'CPLANE'
            else:
                subs = 'Reserved'
            v['subsystem'] = subs

            dynamic_path, firstJobLaunch, tlstr = _get_final_cpath(cpath[0], ljobs, dbuilds)
            v['cpath'] = dynamic_path
            v['timeslots'] = tlstr
            v['firstJobLaunch'] = firstJobLaunch

    def update_skytrack(self, sdata):
        try:
            self.connection.ping(reconnect=True)
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO t_critical_path " \
                      "(pipeline,queueitem,changeitem,timeslot,path,subsystem,c_project,c_branch,end_time," \
                      "pipeline_waiting_time,first_job_launch_time_in_zuul)" \
                      " VALUES ('{0}','{1}','{2}','{3}','{4}','{5}','{6}','{7}',{8},{9},{10})".format(*sdata)
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
            tdate = datetime.datetime.now(tz=pytz.timezone('UTC')).strftime("%Y-%m-%d 00:00:00")
        jto_ins = JobTreeOper(DB_HOST, DB_USER, DB_PASS, DB_TEST)
        jto_ins.get_records(tdate)
        jto_ins.update_data()
        log.debug(jto_ins.datas)
        try:
            sky_ins = JobTreeOper(SDB_HOST, SDB_USER, SDB_PASS, SDB_TEST)
            for k, v in jto_ins.datas.items():
                if v['cpath']:
                    pipeline, enqueuetime = v['pipeline'].split(',')
                    try:
                        v['pipelineWaiting'] = v['firstJobLaunch'] - float(enqueuetime)
                    except Exception as time_err:
                        log.debug(time_err)
                        continue
                    fjlDate = datetime.datetime.fromtimestamp(v['firstJobLaunch'], tz=pytz.timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S')
                    try:
                        sky_ins.update_skytrack((pipeline,
                                                v['queueitem'],
                                                v['change'],
                                                v['timeslots'],
                                                v['cpath'],
                                                v['subsystem'],
                                                v['project'],
                                                v['branch'],
                                                "str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(tdate),
                                                 v['pipelineWaiting'],
                                                 "str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(str(fjlDate))))
                    except Exception as sky_err:
                        log.debug(sky_err)
                        continue
        except Exception as sky_err:
            log.debug(str(sky_err))
        finally:
            sky_ins._close()


sys.exit(Runner().run())
