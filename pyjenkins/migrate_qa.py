#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
This script used to migrate zuul qa env from cloud to linsee or linsee to cloud
we use this to call the jenkins job in logical order
"""
import fire
from api import jenkins_api


def cloud_to_lin(data):
    jenkins = jenkins_api.JenkinsRest(data['host'], data['user'], data['password'])

    # close jenkins-prod jenkins-qa on cloud
    print("start to close jenkins-prod and jenkins-qa on cloud...")
    jenkins.build_job("cloud_jenkins", {'operation': 'close'})

    # change domain name from cloud to linsee
    print("start to switch domain name from cloud to linsee...")
    jenkins.build_job("change_domain", {'operation': 'ctl'})

    # open jenkins on linsee
    print("start to open jenkins-prod and jenkins-qa on linsee...")
    jenkins.build_job("linsee_jenkins", {'operation': 'open'})

    # open zuul qa on linsee
    print("start to open zuul-qa on linsee...")
    jenkins.build_job("linsee_zuul", {'operation': 'open'})
    # close zuul-qa on cloud
    print("start to close zuul-qa on cloud...")
    jenkins.build_job("cloud_zuul", {'operation': 'close'})
    # open gerrit qa on linsee
    print("start to open gerrit-qa on linsee...")
    jenkins.build_job("linsee_gerrit", {'operation': 'open'})
    # close gerrit qa on cloud
    print("start to close gerrit-qa on cloud...")
    jenkins.build_job("cloud_gerrit", {"a": "b"})

    print("Done")


def lin_to_cloud(data):
    jenkins = jenkins_api.JenkinsRest(data['host'], data['user'], data['password'])

    # close jenkins on linsee
    print("start to close jenkins-prod and jenkins-qa on linsee")
    jenkins.build_job("linsee_jenkins", {'operation': 'close'})
    # change domain name from linsee to cloud
    print("start to switch domain name from linsee to cloud...")
    jenkins.build_job("change_domain", {'operation': 'ltc'})
    # open jenkins on cloud
    print("start to open jenkins-prod and jenkins-qa on cloud...")
    jenkins.build_job("cloud_jenkins", {'operation': 'open'})
    # open zuul qa on cloud
    print("start to open zuul-qa on cloud...")
    jenkins.build_job("cloud_zuul", {'operation': 'open'})
    # close zuul qa on linsee
    print("start to close zuul-qa on linsee...")
    jenkins.build_job("linsee_zuul", {'operation': 'close'})
    # close gerrit qa on cloud
    print("start to close gerrit-qa on cloud...")
    jenkins.build_job("cloud_gerrit", {'operation': 'close'})
    # open gerrit qa on linsee
    print("start to open gerrit-qa on linsee")
    jenkins.build_job("linsee_gerrit", {'operation': 'open'})

    print('Done!')


def run(host="", user="", password="", operation="ctl"):
    if host == "":
        host = "http://5g-cimaster-4.eecloud.dynamic.nsn-net.net:8080/job/zuul/"
        user = "dxuan"
        password = "ee8ba4c1855dfb79baf979ca600f1fd8"

    user_data = {
        'host': host,
        'user': user,
        'password': password
    }
    print operation
    if operation.lower() == "ctl":
        print("start...")
        cloud_to_lin(user_data)
    else:
        lin_to_cloud(user_data)


if __name__ == "__main__":
    fire.Fire(run)
