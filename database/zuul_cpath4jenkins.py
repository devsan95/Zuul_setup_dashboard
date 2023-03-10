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
        cd = datetime.datetime.strptime(tdate, "%Y-%m-%d 00:00:00")
        nd = str(datetime.datetime.date(cd) + datetime.timedelta(days=1))
        with self.connection.cursor() as cursor:
            sql = "select count(*) from item_jobtree where created_at  >= '{0}' and " \
                  "created_at  < '{1} 00:00:00'".format(cd, nd)
            cursor.execute(sql)
            result = cursor.fetchone()
        return result['count(*)']

    def get_records(self, tdate=''):
        cd = datetime.datetime.strptime(tdate, "%Y-%m-%d 00:00:00")
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
                                                     enqueuetime=enqueue_time,
                                                     result=result,
                                                     retry_info=';'.join(retry_info),
                                                     none_info=';'.join(none_info),
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
                    ljob[i].append(list(b.keys())[0])
                    ttmpbt.extend(list(b.values())[0])
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
                        preJobinFpath = fpath[fpath.index(cj) - 1]
                        preJobinFpathFirstRun = _item_first_run_layer(preJobinFpath, ljobs)
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
                                    addJobIndex = _item_first_run_layer(addJob, ljobs)
                                    if addJob not in fpath and addJobIndex > preJobinFpathFirstRun:
                                        fpath.insert(curJobIndexInCPath, addJob)

                ffpath = list()
                for layer, jobs in sorted(ljobs.items(), key=lambda x: x[0]):
                    pjobs = set(jobs) & set(fpath)
                    if len(pjobs) < 1:
                        continue
                    elif len(pjobs) < 2:
                        ffpath.append(list(pjobs)[0])
                        fpath.remove(list(pjobs)[0])
                    else:
                        last_finished = max([buildsinfo[p][3] for p in pjobs])
                        for pjob in pjobs:
                            if buildsinfo[pjob][3] == last_finished:
                                log.debug("Adding {0} {1}".format(pjob, buildsinfo[pjob][3]))
                                ffpath.append(pjob)
                            fpath.remove(pjob)

                return ffpath

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
                firstJobLaunch = buildsinfo[f_cpath[0]][1]
            except Exception as t_err:
                firstJobLaunch = 'N/A'
                log.debug(str(t_err))
            for n, fcp in enumerate(f_cpath):
                try:
                    running_time = int(buildsinfo[fcp][3] - buildsinfo[fcp][2])
                except Exception as t_err:
                    running_time = 'N/A'
                    log.debug(str(t_err))
                timeslots.append(running_time)
            total = sum(timeslots)
            timeslots.insert(0, total)
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
            try:
                dynamic_path, firstJobLaunch, tlstr = _get_final_cpath(cpath[0], ljobs, dbuilds)
            except Exception as time_err:
                log.debug(time_err)
                continue
            v['cpath'] = dynamic_path
            v['timeslots'] = tlstr
            v['firstJobLaunch'] = firstJobLaunch

    def update_skytrack(self, sdata):
        try:
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
                    fjlDate = datetime.datetime.fromtimestamp(v['firstJobLaunch'], tz=pytz.timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S')
                    try:
                        sky_ins.update_skytrack((v['pipeline'],
                                                 v['queueitem'],
                                                 v['result'],
                                                 v['change'],
                                                 v['timeslots'],
                                                 v['cpath'],
                                                 v['subsystem'],
                                                 v['project'],
                                                 v['branch'],
                                                 "str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(tdate),
                                                 "str_to_date('{}','%Y-%m-%d %H:%i:%s')".format(str(fjlDate))))
                    except Exception as sky_err:
                        log.debug(sky_err)
                        continue
        except Exception as sky_err:
            log.debug(str(sky_err))
        finally:
            sky_ins._close()


sys.exit(Runner().run())
