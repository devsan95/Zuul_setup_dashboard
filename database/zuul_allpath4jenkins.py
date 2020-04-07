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
        self.allpaths = collections.defaultdict(dict)

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
        cd = datetime.datetime.strptime(tdate, "%Y-%m-%d")
        nd = str(datetime.datetime.date(cd) + datetime.timedelta(days=1))
        with self.connection.cursor() as cursor:
            sql = "select count(*) from item_jobtree where created_at  >= '{0} 00:00:00' and " \
                  "created_at  < '{1} 00:00:00'".format(cd, nd)
            cursor.execute(sql)
            result = cursor.fetchone()
        return result['count(*)']

    def get_records(self, tdate=''):
        cd = datetime.datetime.strptime(tdate, "%Y-%m-%d")
        nd = str(datetime.datetime.date(cd) + datetime.timedelta(days=1))
        log.debug("data is from {0} to {1}".format(cd, nd))
        with self.connection.cursor() as cursor:
            sql = "select * from item_jobtree where created_at  >= '{0}' and " \
                  "created_at  < '{1} 00:00:00'".format(cd, nd)
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
            enqueue_time = res.get('enqueue_time')
            result = res.get('result')
            retry_info = [rk + ',' + str(rv) for rk, rv in ast.literal_eval(res.get('retry_info')).items()]
            none_info = [nk + ',' + str(nv) for nk, nv in ast.literal_eval(res.get('none_info')).items()]
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
                                                     enqueuetime=enqueue_time,
                                                     result=result,
                                                     retry_info=';'.join(retry_info),
                                                     none_info=';'.join(none_info),
                                                     subsystem=subsystem,
                                                     pipelineWaiting=pipelineWaiting,
                                                     firstJobLaunch=firstJobLaunch,
                                                     timeslots=timeslots)

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

    def update_data(self):
        """
        update critical path and the timeslots, each build waiting time and running time.
        :param builds:
        :param cpath:
        :return:
        """
        for k, v in self.datas.items():
            log.debug("Generate allpath data for {}".format(k))
            buildsinfo = v['builds']
            allpath = self.get_paths(v['jobtree'])
            for path_index, apath in enumerate(allpath):
                path_key = k + '-' + str(path_index)
                if apath.count(r'MASTER_PROD/UPLANE') or apath.count(r'MASTER/GNB/UPLANE'):
                    subs = 'UPLANE'
                elif apath.count(r'MASTER_PROD/CPLANE') or apath.count(r'MASTER/GNB/CPLANE'):
                    subs = 'CPLANE'
                else:
                    subs = 'Reserved'
                self.allpaths[path_key]['subsystem'] = subs
                self.allpaths[path_key]['path'] = apath
                self.allpaths[path_key]['pipeline'] = v['pipeline']
                self.allpaths[path_key]['queueitem'] = v['queueitem']
                self.allpaths[path_key]['change'] = v['change']
                self.allpaths[path_key]['result'] = v['result']
                self.allpaths[path_key]['project'] = v['project']
                self.allpaths[path_key]['branch'] = v['branch']
                path_job_ls = apath.split(' -> ')
                self.allpaths[path_key]['firstJobLaunch'] = buildsinfo[path_job_ls[0]][1]
                timeslots = list()
                for n, fcp in enumerate(path_job_ls):
                    try:
                        # print buildsinfo[fcp][3], buildsinfo[fcp][2]
                        running_time = int(buildsinfo[fcp][3]) - int(buildsinfo[fcp][2])
                    except Exception as time_err:
                        log.debug("job item time with exception: {}".format(str(time_err)))
                        continue
                    timeslots.append(running_time)
                total = sum(timeslots)
                timeslots.insert(0, total)
                tlstr = ','.join([str(tls) for tls in timeslots])
                self.allpaths[path_key]['timeslots'] = tlstr

    def update_skytrack(self, sdata):
        log.debug("test data {} will be updated into skytrack".format(sdata))
        try:
            log.debug(sdata)
            self.connection.ping(reconnect=True)
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO t_critical_path_no_waiting " \
                      "(pipeline,queueitem,status,changeitem,timeslot,path,subsystem,c_project,c_branch,end_time," \
                      "first_job_launch_time_in_zuul)" \
                      " VALUES ('{0}','{1}','{2}','{3}','{4}','{5}','{6}','{7}','{8}',{9},{10})".format(*sdata)
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
            tdate = self.jto_args.tdate.strip()
            # tdate = "{} 00:00:00".format(self.jto_args.tdate.strip())
        else:
            # tdate = datetime.datetime.now(tz=pytz.timezone('UTC')).strftime("%Y-%m-%d 00:00:00")
            tdate = datetime.datetime.now(tz=pytz.timezone('UTC')).strftime("%Y-%m-%d")
        jto_ins = JobTreeOper(self.jto_args.zuul_host,
                              self.jto_args.zuul_usr,
                              self.jto_args.zuul_passwd,
                              self.jto_args.zuul_table)
        # cnt = jto_ins._get_records_amount(tdate)
        jto_ins.get_records(tdate)
        jto_ins.update_data()
        log.debug(jto_ins.datas)

        try:
            sky_ins = JobTreeOper(self.jto_args.sky_host,
                                  self.jto_args.sky_usr,
                                  self.jto_args.sky_passwd,
                                  self.jto_args.sky_table)
            for k, v in jto_ins.allpaths.items():
                log.debug("{0}: {1}".format(k, v))
                fjlDate = datetime.datetime.fromtimestamp(v['firstJobLaunch'],
                                                          tz=pytz.timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S')
                try:
                    sky_ins.update_skytrack((v['pipeline'],
                                             k,
                                             v['result'],
                                             v['change'],
                                             v['timeslots'],
                                             v['path'],
                                             v['subsystem'],
                                             v['project'],
                                             v['branch'],
                                             "str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(tdate),
                                             "str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(str(fjlDate))))
                except Exception as sky_err:
                    log.debug(str(sky_err))
                    continue
        except Exception as sky_err:
            log.debug(str(sky_err))
        finally:
            sky_ins._close()


sys.exit(Runner().run())
