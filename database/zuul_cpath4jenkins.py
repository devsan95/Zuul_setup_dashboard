import sys
import ast
import pytz
import logging
import argparse
import pymysql
import collections
import datetime

log = logging.getLogger(__file__)


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
        update critical path and the timeslots, without build waiting time and running time.
        :param builds:
        :param cpath:
        :return:
        """

        def _get_final_cpath(cpath, buildsinfo):
            fcpath = list()
            cpath_ls = cpath.split(' -> ')
            for i, p in enumerate(cpath_ls):
                if not i:
                    fcpath.append(p)
                else:
                    try:
                        _last_job_endtime = buildsinfo[fcpath[-1]][3]
                        _current_job_starttime = buildsinfo[p][2]
                    except Exception as job_err:
                        log.debug("job time with exception: {}".format(str(job_err)))
                        return None, None, None
                    if _current_job_starttime > _last_job_endtime:
                        fcpath.append(p)
            timeslots = list()
            firstJobLaunch = buildsinfo[fcpath[0]][1]
            for n, fcp in enumerate(fcpath):
                try:
                    running_time = buildsinfo[fcp][3] - buildsinfo[fcp][2]
                except Exception as time_err:
                    log.debug("job item time with exception: {}".format(str(time_err)))
                    return None, None, None
                timeslots.append(running_time)
            total = sum(timeslots)
            timeslots.insert(0, total)
            dyn_path = ' -> '.join(fcpath)
            tlstr = ','.join([str(tls) for tls in timeslots])
            return dyn_path, firstJobLaunch, tlstr

        for k, v in self.datas.items():
            dbuilds = v['builds']
            cpath = self.critical_path(dbuilds, v['jobtree'])
            if not cpath:
                continue
            dynamic_path, firstJobLaunch, tlstr = _get_final_cpath(cpath[0], dbuilds)
            if not dynamic_path:
                continue
            else:
                v['cpath'] = dynamic_path
                v['timeslots'] = tlstr
                v['firstJobLaunch'] = firstJobLaunch

            if cpath and (cpath[0].count(r'MASTER_PROD/UPLANE') or cpath[0].count(r'MASTER/GNB/UPLANE')):
                subs = 'UPLANE'
            elif cpath and (cpath[0].count(r'MASTER_PROD/CPLANE') or cpath[0].count(r'MASTER/GNB/CPLANE')):
                subs = 'CPLANE'
            else:
                subs = 'Reserved'
            v['subsystem'] = subs

    def update_skytrack(self, sdata):
        try:
            log.debug(sdata)
            self.connection.ping(reconnect=True)
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO t_critical_path_no_waiting " \
                      "(pipeline,queueitem,changeitem,timeslot,path,subsystem,c_project,c_branch,end_time," \
                      "first_job_launch_time_in_zuul)" \
                      " VALUES ('{0}','{1}','{2}','{3}','{4}','{5}','{6}','{7}',{8},{9})".format(*sdata)
                log.debug(sql)
                cursor.execute(sql)
            self.connection.commit()
        except Exception as err:
            log.debug(str(err))


class Runner(object):
    def __init__(self):
        self.parser = self.get_parser()
        self.jto_args = None
        self.other_args = None
        self.parse_arguments()

    def get_parser(self):
        parser = argparse.ArgumentParser(description='Used for job find critical path')
        parser.add_argument('-t', '--tdate', dest='tdate', help="time date")
        parser.add_argument('-o', '--zuul-host', dest='zuul_host', help='ZUUL DB host')
        parser.add_argument('-u', '--zuul-username', dest='zuul_usr', help='ZUUL DB username')
        parser.add_argument('-p', '--zuul-password', dest='zuul_passwd', help='ZUUL DB password')
        parser.add_argument('-q', '--zuul-table', dest='zuul_table', help='ZUUL DB test table')
        parser.add_argument('-s', '--sky-host', dest='sky_host', help='ZUUL DB host')
        parser.add_argument('-l', '--sky-username', dest='sky_usr', help='SKY DB username')
        parser.add_argument('-m', '--sky-password', dest='sky_passwd', help='SKY DB password')
        parser.add_argument('-n', '--sky-table', dest='sky_table', help='SKY DB test table')
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
        jto_ins = JobTreeOper(self.jto_args.zuul_host,
                              self.jto_args.zuul_usr,
                              self.jto_args.zuul_passwd,
                              self.jto_args.zuul_table)
        jto_ins.get_records(tdate)
        jto_ins.update_data()
        log.debug(jto_ins.datas)
        try:
            sky_ins = JobTreeOper(self.jto_args.sky_host,
                                  self.jto_args.sky_usr,
                                  self.jto_args.sky_passwd,
                                  self.jto_args.sky_table)
            for k, v in jto_ins.datas.items():
                if v['cpath']:
                    pipeline, enqueuetime = v['pipeline'].split(',')
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
                                                "str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(tdate), "str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(str(fjlDate))))
                    except Exception as sky_err:
                        log.debug(sky_err)
                        continue
        except Exception as sky_err:
            log.debug(str(sky_err))
        finally:
            sky_ins._close()


sys.exit(Runner().run())
