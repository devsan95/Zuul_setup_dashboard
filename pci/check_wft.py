#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date    : 2018-02-28 16:14:45
# @Author  : robin (robin.zhu@nokia-sbell.com)
# @site    : HangZhou

import fire
import time
import sys
from scm_tools.wft.build_content import BuildContent


class UnstableExit(SystemError):
    pass


class ErrorExit(SystemError):
    pass


def check_release_status(package, wait_minute=20):
    assert package != "", "package must have value!"
    while True:
        build_content = BuildContent.get(package)
        status = build_content.get_state()
        print "package {0} status is {1}".format(package, status)
        if status == "not_released":
            print "status is not_released, make this job failed"
            raise ErrorExit()
        elif status == "released":
            print "status is released, make this job success"
            break
        elif status == "released_with_restrictions":
            print "status is released_with_restrictions, make job to unstable "
            raise UnstableExit()
        else:
            print "package {0} status is {1},waitting for released or not released".format(package, status)
            time.sleep(int(wait_minute) * 60)


if __name__ == '__main__':
    try:
        fire.Fire(check_release_status)
    except ErrorExit:
        sys.exit(1)
    except UnstableExit:
        sys.exit(2)
