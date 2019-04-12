#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
this is a scripts to send different type of email
the configuration is in properties/mail.properties
it use templates and fill it with parameters get from options
"""


import os
import sys
import logging

from api import config
from mod import templateMail

CONF = config.ConfigTool()
MAIL_CONFIG = CONF.load('mail')
logging.basicConfig(level=logging.INFO)


class MailGenerator(object):
    def __init__(self, mail_type, param_dict, module_list):
        self.mail_type = mail_type
        self.param_dict = param_dict
        self.module_list = module_list
        if 'title' not in self.param_dict:
            self.param_dict['title'] = self.mail_type
        self.tmail_obj = self.get_mailtp_obj(MAIL_CONFIG.get(
            mail_type,
            "template_file"))

    def get_mailtp_obj(self, template_file):
        tpl_file = os.path.join(config.get_config_path(),
                                'template',
                                template_file)
        mail_object = None
        mandatory_params = []
        with open(tpl_file, 'r') as fi:
            exec fi.read()
        self.checkTemplateParams(locals(), self.param_dict)
        self.mandatory_params = mandatory_params
        return templateMail.TemplateMail(mail_object,
                                         self.mail_type,
                                         self.param_dict['title'])

    def generate(self):
        self.check_mandatory_params()
        if self.module_list:
            self.run_functions()
        self.tmail_obj.replaceValue(self.param_dict)
        logging.debug(
            "########### mail obj ##########\n%s", self.tmail_obj.mail_object)
        self.tmail_obj.set_receiver(self.param_dict)
        self.tmail_obj.send_mail()

    def run_functions(self):
        for module_name in self.module_list:
            exec("from %s import *" % module_name)
        local_items = locals()
        fun_dict = self.tmail_obj.getFunctions()
        for k, v in fun_dict.items():
            logging.info('replace value by result of %s', v)
            self.tmail_obj.setValue([k], local_items[v](self.param_dict))
        fun_key_dict = self.tmail_obj.getKeyFunctions()
        logging.info(" function dict %s", fun_dict)
        print local_items
        for k, v in fun_key_dict.items():
            if v in local_items:
                logging.info("*** running function %s ***", v)
                self.tmail_obj.replaceStr('[function]%s' % v,
                                          local_items[v](self.param_dict))
            else:
                logging.error("*** Error: not found function %s ***", v)

    def check_mandatory_params(self):
        for k in self.mandatory_params:
            if k not in self.param_dict:
                logging.error('Error, Mandatory Parameter %s not set', k)
                sys.exit(2)
                return False
        return True

    def show_mandatory_params(self):
        print "### Mandatory Parameters:\n %s\n###" % self.mandatory_params

    def checkTemplateParams(self, local_pdict, pdict):
        template_params = MAIL_CONFIG.get(
            'mail_template',
            'template_params').split(',')
        option_params = MAIL_CONFIG.get(
            'mail_template',
            'option_params').split(',')
        for param_name in template_params:
            if param_name not in local_pdict:
                logging.error("%s not set in mail template ***", param_name)
                sys.exit(2)
        for param_name in option_params:
            if param_name in local_pdict:
                logging.debug("add param %s to param dict", param_name)
                pdict.update(local_pdict[param_name])
                logging.debug("pdict is now: %s", pdict)
