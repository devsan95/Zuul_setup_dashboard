'''
this is a scripts to create/update manager changes
it is based on a topic name
topic change will attached a change with real modfication
after topic finished, topic change also be merged
topic_change -> pci_change_mgr(repo)
real_chagne -> meta-5g-poc(repo)
functions:
    renew() -> update or create change for <issue_name>
    release() -> merge topoic change for <issue_name>
'''

import sys
import argparse
import traceback
from api import config
from mod import gitlab_tools


CONF = config.ConfigTool()
CONF.load('repo')


def getParamsDict(options, filterlist=[]):
    """
    get a dict from paramater options
    """
    paramDict = {}
    if options:
        for line in options:
            key = line.split("=")[0]
            value = line.split("=")[1]
            if key not in filterlist:
                paramDict[key] = value
    return paramDict


def _main(action, params):
    gitlab_obj = None
    if 'config' in params and params['config']:
        gitlab_obj = gitlab_tools.Gitlab_Tools(path=params['config'])
    elif 'url' in params and 'token' in params:
        gitlab_obj = gitlab_tools.Gitlab_Tools(
            url=params['url'],
            token=params['token'])
    else:
        print('Error config file is not given')
        sys.exit(2)
    if hasattr(gitlab_obj, action):
        getattr(gitlab_obj, action)(params)
    else:
        print('Error action:{} is not supported yet'.format(params['action']))
        sys.exit(2)


def _parse_args():
    parser = argparse.ArgumentParser(
        description="this is the help usage of %(prog)s",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        "--options",
        nargs='*',
        help="options , now support "
             "project/branch/title/ref",
        dest="options")

    parser.add_argument(
        "--action",
        required=True,
        help="action: create_mr/merge_mr",
        dest="action")

    parser.add_argument(
        "--config",
        required=False,
        default='',
        help="config file path",
        dest="config")

    args = parser.parse_args()
    options = args.options
    params = getParamsDict(options)
    return args.action, params


if __name__ == '__main__':
    try:
        action, params = _parse_args()
        _main(action, params)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
