import sys
import logging
import argparse
import pymysql

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
            log.debug("Queueitems: {}".format(result))
            return [res['queueitem'] for res in result]

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
                        paths.append('-'.join([k, inv]))
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
        except:
            totaltime = 'N/A'
            log.debug('Unvalid time exist. ')
        for i, ts in enumerate(timeslots):
            try:
                base = int(timeslots[i - 1][2]) if i else int(ts[0])
            except:
                base = 'N/A'
            try:
                waittime = str(int(ts[1]) - base)
            except:
                waittime = 'N/A'
            timeinfo.append(waittime)
            try:
                runtime = str(int(ts[2]) - int(ts[1]))
            except:
                runtime = 'N/A'
            timeinfo.append(runtime)
        timeinfo.append(totaltime)
        return ','.join(timeinfo)

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
        if self.jto_args.qitem in queueitems:
            try:
                cpath = jto_ins.critical_path(self.jto_args.qitem)
                binfo = jto_ins._get_builds(self.jto_args.qitem)
                builds = eval(str(binfo['builds']).replace("defaultdict(<type 'list'>, ", '')[:-1])
                timeinfo = self.get_buildtime(cpath[0], builds)
                print cpath
                print timeinfo
            except:
                jto_ins._close()
        else:
            for qitem in queueitems:
                try:
                    cpath = jto_ins.critical_path(qitem)
                    binfo = jto_ins._get_builds(qitem)
                    builds = eval(str(binfo['builds']).replace("defaultdict(<type 'list'>, ", '')[:-1])
                    timeinfo = self.get_buildtime(cpath[0], builds)
                    print cpath
                    print timeinfo
                except:
                    jto_ins._close()


sys.exit(Runner().run())
