
import sys
import logging
import argparse
import pymysql
import collections

log = logging.getLogger(__file__)


class JobTreeOper(object):
    def __init__(self, host, username, password, test_db):
        self.host = host
        self.username = username
        self.password = password
        self.db = test_db
        self.connection = self._connect()

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

    def _get_queueitems(self, chps):
        with self.connection.cursor() as cursor:
            sql = "select queueitem from item_jobtree where changeitem='{}'".format(chps)
            cursor.execute(sql)
            result = cursor.fetchall()
            log.debug("Review queueitem and result:{}".format(result))
            log.debug("Queueitems: {}".format(result))
            try:
                frel = [res['queueitem'].split(',')[0] for res in result]
            except Exception as rel_err:
                log.debug("No review result, {}".format(str(rel_err)))
                frel = [res['queueitem'] for res in result]
            return frel

    def _get_builds(self, qitem):
        with self.connection.cursor() as cursor:
            sql = "select builds from item_jobtree where queueitem='{}'".format(qitem)
            cursor.execute(sql)
            result = cursor.fetchone()
            log.debug("Builds: {}".format(result))
            return result

    def _get_longest_build(self, qitem):
        binfo = self._get_builds(qitem)
        buildsinfo = eval(str(binfo['builds']).replace("defaultdict(<type 'list'>, ", '')[:-1])
        longest = max([vitem[-1] for vitem in buildsinfo.values() if vitem[-1]])
        lbuild = ''
        for k, v in buildsinfo.items():
            if v[-1] == longest:
                lbuild = k
                break
        return lbuild

    def _get_trees(self, qitem):
        self.connection.ping(reconnect=True)
        with self.connection.cursor() as cursor:
            sql = "select jobtree from item_jobtree where queueitem='{}'".format(qitem)
            cursor.execute(sql)
            result = cursor.fetchone()
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

    def get_layer_jobs(self, qitem):
        ljob = collections.defaultdict(list)
        dbt = self._get_trees(qitem)
        bt = eval(dbt.items()[0][1])
        tmpbt = bt
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

    def critical_path(self, qitem):
        cpath = list()
        lbuild = self._get_longest_build(qitem)
        btree = self._get_trees(qitem)
        btree = eval(btree.items()[0][1])
        allpaths = self.get_paths(btree)
        for p in allpaths:
            if p.endswith(lbuild):
                cpath.append(p)
        return cpath

    def get_final_cpath(self, qitem):
        binfo = self._get_builds(qitem)
        buildsinfo = eval(str(binfo['builds']).replace("defaultdict(<type 'list'>, ", '')[:-1])
        ljobs = self.get_layer_jobs(qitem)
        cpath = self.critical_path(qitem)
        fcpath = list()
        cpath_ls = cpath[0].split(' -> ')
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
                    # pl = 0
                    ttls = list()
                    for firstRun in range(i):
                        if p in ljobs[firstRun]:
                            # pl = firstRun
                            break
                    for h in range(firstRun + 1, i):
                        ttls.append(cpath_ls[h])
                    if ttls:
                        # st = buildsinfo[ttls[0]][1]
                        et = buildsinfo[ttls[-1]][3]
                        if buildsinfo[p][3] > et:
                            fcpath.append(p)
                            for m in ttls:
                                try:
                                    fcpath.remove(m)
                                except Exception as re_err:
                                    log.error(str(re_err))
                                    log.debug("Already removed {}".format(m))
        timeslots = list()
        total = int(buildsinfo[fcpath[-1]][3] - buildsinfo[fcpath[0]][1])
        timeslots.append(total)
        for n, fcp in enumerate(fcpath):
            if not n:
                t1 = int(buildsinfo[fcp][2] - buildsinfo[fcp][1])
                t2 = int(buildsinfo[fcp][3] - buildsinfo[fcp][2])
            else:
                t1 = int(buildsinfo[fcp][2] - buildsinfo[fcpath[n - 1]][3])
                t2 = int(buildsinfo[fcp][3] - buildsinfo[fcp][2])
            timeslots.append(t1)
            timeslots.append(t2)
        cp_builds = list()
        for cpat in fcpath:
            cp_builds.append(buildsinfo[cpat])
        fcp = ' -> '.join(fcpath)
        tls = ','.join([str(tls) for tls in timeslots])
        return cp_builds, fcp, tls


class Runner(object):
    def __init__(self):
        self.parser = self.get_parser()
        self.jto_args = None
        self.other_args = None
        self.parse_arguments()

    def get_parser(self):
        parser = argparse.ArgumentParser(description='Used for job find critical path')
        parser.add_argument('-s', '--patchset', dest='ps', help='change and patch-set')
        parser.add_argument('-q', '--queueitem', dest='qitem', help='queue item of change')
        parser.add_argument('-o', '--host', dest='host', help='DB host')
        parser.add_argument('-u', '--username', dest='usr', help='DB username')
        parser.add_argument('-p', '--password', dest='passwd', help='DB password')
        parser.add_argument('-t', '--table', dest='table', help='DB test table')
        parser.add_argument('-d', '--debug', dest='debug', action='store_true', help="logging level ")
        return parser

    def parse_arguments(self):
        self.jto_args, self.other_args = self.parser.parse_known_args()

    def run(self):
        if self.jto_args.debug:
            logging.basicConfig(level=logging.DEBUG,
                                format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                                datefmt='%a, %d %b %Y %H:%M:%S')

        if not self.jto_args.ps:
            raise Exception("Please input change and patchset.")
        if not self.jto_args.host or not self.jto_args.usr or \
                not self.jto_args.passwd or not self.jto_args.table:
            raise Exception("Please input database information.")
        jto_ins = JobTreeOper(self.jto_args.host, self.jto_args.usr,
                              self.jto_args.passwd, self.jto_args.table)
        log.debug("connection {0} to db {1}".format(jto_ins.connection,
                                                    self.jto_args.table))
        queueitems = jto_ins._get_queueitems(self.jto_args.ps)
        results = list()
        if self.jto_args.qitem in queueitems:
            try:
                jto_ins.get_layer_jobs(self.jto_args.qitem)
                res = jto_ins.get_final_cpath(self.jto_args.qitem)
                results.append(res)
            except Exception as c_err:
                log.error(str(c_err))
                jto_ins._close()
        else:
            for qitem in queueitems:
                try:
                    jto_ins.get_layer_jobs(qitem)
                    res = jto_ins.get_final_cpath(qitem)
                    results.append(res)
                except Exception as c_err:
                    log.error(str(c_err))
                    jto_ins._close()

        for result in results:
            print("Builds info: {}".format(result[0]))
            print("Critical Path: {}".format(result[1]))
            print("Timeslots : {}".format(result[2]))


sys.exit(Runner().run())
