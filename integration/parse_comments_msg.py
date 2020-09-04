#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import sys
import traceback
import fire
import api.gerrit_rest


def run(change_id, gerrit_info_path):
    rest = api.gerrit_rest.init_from_yaml(gerrit_info_path)
    rest.init_cache(1000)
    print('parsing comments!')
    comment_list = rest.generic_get('/changes/{}/detail'.format(change_id), using_cache=True)

    for msg in comment_list['messages']:
        if 'update_component:' in msg['message']:
            print('there is update_component in {} change'.format(change_id))
            sys.exit(0)

    print('there is no update_component in {} change'.format(change_id))
    sys.exit(2)


if __name__ == '__main__':
    try:
        fire.Fire(run)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
