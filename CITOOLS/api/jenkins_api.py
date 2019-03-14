#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
a class to package jenkins api operation
via jenkins api
"""
from jenkinsapi.jenkins import Jenkins
from jenkins import Jenkins as Jen


class JenkinsRest(object):
    def __init__(self, host, user, password):
        self.host = host
        self.user = user
        self.password = password
        print("create jenkins api connection...")
        self.jenkins_api = Jenkins(self.host, self.user, self.password)
        print("create jenkins connection...")
        self.jenkins = Jen(self.host, self.user, self.password)

    def create_job(self, name, config):
        if not self.jenkins.job_exists(name):
            self.jenkins.create_job(name, config)
            print("INNER creating job {}...".format(name))

    def copy_job(self, from_name, to_name):
        if self.jenkins_api.has_job(from_name):
            self.jenkins_api.copy_job(from_name, to_name)

    def get_job(self, name):
        if self.jenkins_api.has_job(name):
            job = self.jenkins_api.get_job(name)
            return job
        return None

    def get_first_level_jobs(self):
        return self.jenkins.get_all_jobs()

    def get_all_jobs(self):
        print("Running")
        return self.jenkins_api.get_jobs()

    def get_job_config(self, name):
        if self.jenkins.job_exists(name):
            config = self.jenkins.get_job_config(name)
            return config
        return None

    def define_shell_command_in_xml(self, xml, command):
        pass

    def delete_job(self, name):
        if self.jenkins.job_exists(name):
            self.jenkins.delete_job(name)
            print("Done deleting {}. ".format(name))

    def delete_all_jobs(self, name):
        self.jenkins.delete_job(name)

    def set_node(self, name, node):
        if self.jenkins.job_exists(name):
            print(node)

    def is_exists(self, name):
        return self.jenkins.job_exists(name)

    def has_job(self, name):
        return self.jenkins.job_exists(name)

    def update_job(self, name, config):
        self.jenkins.reconfig_job(name, config)

    def build_job(self, name, parameters):
        if self.is_exists(name):
            self.jenkins.build_job(name, parameters)
