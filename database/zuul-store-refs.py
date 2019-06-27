#!/usr/bin/env python

"""
Zuul references store&restore.

Store: storeall of zuul refs into args.gitrepo. run the following command. e.g.
$ python zuul-store-refs.py --db-str mysql+mysqlconnector://"user":"p@ssword"@10.159.11.27/stored_refs -v /ephemeral/zuul/git/MN/5G/NB/gnb

Restroe: restore refs to an exact merger. run the following command in the dest merger server. e.g.
$ python zuul-store-refs.py -r --db-str mysql+mysqlconnector://"user":"p@ssword"@10.159.11.27/stored_refs -v
 -s http://zuule1.dynamic.nsn-net.net:8081/p/MN/5G/NB/gnb /ephemeral/zuul/git/MN/5G/NB/gnb

"""
import errno
import os
from sqlalchemy.orm import sessionmaker
from api import log_api
from model import IntegrationRefs
import argparse
import git
import logging
import time
import sys
import traceback
import sqlalchemy as sa
import configparser


def fetch_codes(repos, refs, mergerN, arguments, mergerurl):
    # Add a new remote name
    if not git.remote.Remote(repos, mergerN).exists():
        git.remote.Remote.add(repos, mergerN, arguments.source)

    for stored_data in refs:
        try:
            # fetch codes
            repos.remote(mergerN).fetch(refspec=stored_data.zuul_ref)

            ref_path = arguments.gitrepo + "/.git/" + stored_data.zuul_ref

            if os.path.exists(os.path.dirname(ref_path)):
                if os.path.exists(ref_path):
                    print("{} in repo {} from merger {} exists.".format(stored_data.zuul_ref, arguments.gitrepo,
                                                                        mergerN))
                    continue
            else:
                try:
                    os.makedirs(os.path.dirname(ref_path))
                except OSError as exc:
                    if exc.errno != errno.EEXIST:
                        raise

                with open(ref_path, 'w') as f:
                    f.write(repos.git.rev_parse("FETCH_HEAD"))
                    f.close()

                print(
                    "{} in repo {} from merger {} succeed.".format(stored_data.zuul_ref, arguments.gitrepo, arguments.merger))
                print "#" * 80
        except Exception as repo_exc:
            log.exception("Error for ref: {} in merger: {}. {}".format(stored_data.zuul_ref, mergerurl, str(repo_exc)))
            continue


class DbHandler(object):
    def __init__(self, db_str):
        self.engine = sa.create_engine(db_str)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.RescheduleAnalyze = None

    def init_db(self, table_name=None):
        if table_name:
            self.RescheduleAnalyze = IntegrationRefs(table_name)
        else:
            self.RescheduleAnalyze = IntegrationRefs()

    def collect_refs_from_merger(self, zuul_url, zuul_project, enable):
        query = self.session.query(IntegrationRefs).filter(
            IntegrationRefs.zuul_url == zuul_url,
            IntegrationRefs.project == zuul_project,
            IntegrationRefs.enable == enable).distinct()
        print(zuul_url, zuul_project, enable)
        return query.all()

    def collect_mergers(self, enable):
        query = self.session.query(IntegrationRefs.zuul_url).filter(IntegrationRefs.enable == enable).distinct()
        return query.all()

    def rollback(self):
        self.session.rollback()


log = log_api.get_console_logger('ZUUL_LOG_INTEGRATION_REFS')

if __name__ == '__main__':
    try:
        NOW = int(time.time())
        ZUUL_REF_PREFIX = 'refs/zuul/'

        parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                            help='set log level from info to debug')
        parser.add_argument('-m', '--merger', dest='merger', type=str,
                            help='set the url of merger, e.g. zuulmergeres42.dynamic.nsn-net.net:8882/p')
        parser.add_argument('--db-str', dest='db_str', type=str, required=True,
                            help='set the str of database, e.g. mysql+mysqlconnector://$USER:$PASSWD@$IP/zuul')
        parser.add_argument('-r', '--restore', dest='restore', action='store_true', help='restore mode')
        parser.add_argument('-s', '--source', dest='source', type=str,
                            help='ref source, if source url needed when restore mode. e.g. '
                                 'http://zuule1.dynamic.nsn-net.net:8081/p/MN/5G/NB/gnb')
        parser.add_argument('gitrepo', help='path to a Zuul git repository')

        args = parser.parse_args()

        logging.basicConfig()
        log = logging.getLogger('zuul-store-refs')
        if args.verbose:
            log.setLevel(logging.DEBUG)
        else:
            log.setLevel(logging.INFO)

        try:
            repo = git.Repo(args.gitrepo)
        except git.exc.InvalidGitRepositoryError:
            error_info = "Invalid git repo: {}".format(args.gitrepo)
            log.error(error_info)
            sys.exit(1)

        if args.db_str:
            db = DbHandler(args.db_str)
            try:
                db.init_db()
            except Exception as ex:
                log.debug('Exception occurs:')
                log.debug(ex)
                log.debug('rollback')
                db.rollback()
                traceback.print_exc()
                raise ex

        mergers = db.collect_mergers(1)

        config = configparser.ConfigParser()
        config.read('/etc/zuul/zuul.conf')
        gitDir = config['merger']['git_dir']
        currentMergerUrl = config['merger']['zuul_url']
        repoDir = args.gitrepo[len(gitDir):]
        print(repoDir[1:])

        if args.restore:
            stored_refs = db.collect_refs_from_merger(currentMergerUrl.replace("http://", ""), repoDir[1:], 1)
            print(stored_refs)
            remoteName = args.source.replace("/", "").replace(":", "")

            fetch_codes(repo, stored_refs, remoteName, args, mergerurl=currentMergerUrl)
            sys.exit(0)

        for merger in mergers:
            print("merger is {}".format(merger.zuul_url))
            mergerName = merger.zuul_url.replace("/p", "").replace(":", "")

            # Backup the stored references in one workspace
            if args.merger:
                merger.zuul_url = args.merger

            stored_refs = db.collect_refs_from_merger(merger.zuul_url, repoDir[1:], 1)

            fetch_codes(repo, stored_refs, mergerName, args, merger)
        sys.exit(0)

    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
