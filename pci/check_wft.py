#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date    : 2018-02-28 16:14:45
# @Author  : robin (robin.zhu@nokia-sbell.com)
# @site    : HangZhou

import fire
from scm_tools.wft.build_content import BuildContent


def check_release_status(package):
    assert package != "", "package must have value!"
    build_content = BuildContent.get(package)
    if build_content.get_state() == "not_released":
        raise SystemError("failed this job because of not_released")


if __name__ == '__main__':
    fire.Fire(check_release_status)
