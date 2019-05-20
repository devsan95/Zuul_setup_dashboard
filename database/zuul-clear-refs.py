#!/usr/bin/env python
# Copyright 2014-2015 Antoine "hashar" Musso
# Copyright 2014-2015 Wikimedia Foundation Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

# pylint: disable=locally-disabled, invalid-name

"""
Zuul references cleaner.

Clear up references under /refs/zuul/ by inspecting the age of the commit the
reference points to.  If the commit date is older than a number of days
specificed by --until, the reference is deleted from the git repository.

Use --dry-run --verbose to finely inspect the script behavior.

e.g. python zuul-clear-refs.py --until 30 --db-str mysql+mysqlconnector://"xxx":"xxx"@10.159.11.27/stored_refs -n -v /ephemeral/zuul/git/gnb

"""

from api import log_api
from model import IntegrationRefs
import argparse
import git
import logging
import time
import sys
import traceback
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

log = log_api.get_console_logger('ZUUL_LOG_INTEGRATION_REFS')


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

    def check_ref_in_db(self, zuul_ref):
        query = self.session.query(IntegrationRefs).filter(
            IntegrationRefs.zuul_ref == zuul_ref)
        if query.count() != 0:
            return True
        return False

    def rollback(self):
        self.session.rollback()


if __name__ == '__main__':
    try:
        NOW = int(time.time())
        DEFAULT_DAYS = 360
        ZUUL_REF_PREFIX = 'refs/zuul/'

        # start to clear refs
        parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument('--until', dest='days_ago', default=DEFAULT_DAYS, type=int,
                            help='references older than this number of day will '
                                 'be deleted. Default: %s' % DEFAULT_DAYS)
        parser.add_argument('-n', '--dry-run', dest='dryrun', action='store_true',
                            help='do not delete references')
        parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                            help='set log level from info to debug')
        parser.add_argument('--db-str', dest='db_str', type=str, required=True,
                            help='set the str of database, e.g. mysql+mysqlconnector://$USER:$PASSWD@$IP/zuul')
        parser.add_argument('gitrepo', help='path to a Zuul git repository')

        args = parser.parse_args()

        logging.basicConfig()
        log = logging.getLogger('zuul-clear-refs')
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

        for ref in repo.references:
            if not ref.path.startswith(ZUUL_REF_PREFIX):
                continue

            # if type(ref) is not git.refs.reference.Reference:
            if not isinstance(ref, git.refs.reference.Reference):
                # Paranoia: ignore heads/tags/remotes ..
                continue

            try:
                commit_ts = ref.commit.committed_date
            except LookupError:
                # GitPython does not properly handle PGP signed tags
                log.exception("Error in commit: %s, ref: %s. Type: %s",
                              ref.commit, ref.path, type(ref))
                continue

            commit_age = int((NOW - commit_ts) / 86400)  # days
            log.debug(
                "%s at %s is %3s days old",
                ref.commit,
                ref.path,
                commit_age,
            )
            if commit_age > args.days_ago:
                # skip the stored_refs
                if args.db_str and db.check_ref_in_db(str(ref.path)):
                    print("{} will be skipped.".format(str(ref.path)))
                    continue
                elif args.dryrun:
                    log.info("Would delete old ref: %s (%s)", ref.path, ref.commit)
                else:
                    log.info("Deleting old ref: %s (%s)", ref.path, ref.commit)
                    ref.delete(repo, ref.path)

    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
