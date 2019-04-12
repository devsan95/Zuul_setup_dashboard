#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
this is a scripts to send different type of email
the configuration is in properties/mail.properties
it use templates and fill it with parameters get from options
"""

import re
import os
import sys
import copy
import logging
from api import mail
from api import config

conf = config.ConfigTool()
mailConfig = conf.load("mail")
logging.basicConfig(level=logging.DEBUG)


class TemplateMail(object):

    def __init__(self, mail_object, mail_type, title):
        self.mail_object = mail_object
        self.mail_type = mail_type
        self.title = title
        self.receiver = ''

    def getDictFromFile(self, replaceFile):
        """
        get dict from a file contains lines like 'key : value'
        """
        dt = {}
        with open(replaceFile, "r") as fi:
            for line in fi.readlines():
                key = line.split(":")[0].strip()
                dt[line.split(":")[0].strip()] = line.split(
                    key)[1].strip(" :\n")
        return dt

    def createContentByTemplate(self, outfile=None):
        """
        replace in template {key} to value
        write the replace string to file if outfile set
        """
        logging.debug("____MailObj____:\n%s", self.mail_object)
        content = self.contentFromObject(self.mail_object)
        newcontent = self.createHtmlFromTemplate('content', content)
        logging.debug("new: %s", newcontent)
        if outfile:
            with open(outfile, "w") as of:
                of.write(newcontent)
        return newcontent

    def setValue(self, key_list, val, mailObject=None):
        if not val:
            return
        if mailObject is None:
            mailObject = self.mail_object
        logging.debug("*** key_list is %s", key_list)
        key_str = key_list[0]
        if len(key_list) == 1 or isinstance(key_list, basestring):
            self.setContent(mailObject, key_str, val)
        else:
            logging.debug("**** trying to find key %s", key_str)
            if isinstance(mailObject, dict):
                logging.debug("**** keys %s", mailObject.keys())
                logging.debug("*** key list %s", key_list)
                if key_str in mailObject.keys():
                    logging.debug("**** find %s", key_str)
                    new_key_list = copy.copy(key_list)
                    new_key_list.pop(0)
                    self.setValue(new_key_list, val, mailObject[key_str])
                else:
                    for k, v in mailObject.items():
                        self.setValue(key_list, val, v)
            if isinstance(mailObject, list):
                for idx, obj in enumerate(mailObject):
                    if (isinstance(obj, tuple) and
                        len(mailObject) > 1 and
                            mailObject[0] == key_str):
                        mailObject[idx] = (obj[0], val)
                    else:
                        self.setValue(key_list, val, obj)
            logging.debug(mailObject)

    def replaceValue(self, str_dict, mailObject=None):
        for k, v in str_dict.items():
            self.replaceStr(k, v, mailObject)

    def replaceStr(self, key_str, val, mailObject=None):
        k_replace_str = '{' + key_str + '}'
        if mailObject is None:
            logging.debug("init mailobj %s", key_str)
            mailObject = self.mail_object
        logging.debug(
            'key str is %s, mailObject: %s', k_replace_str, mailObject)
        if k_replace_str not in '{}'.format(mailObject):
            return
        if isinstance(mailObject, dict):
            logging.debug('replace string: {%s}', key_str)
            for k, v in mailObject.items():
                k_replaced = k
                if isinstance(val, basestring):
                    k_replaced = k.replace('{%s}' % key_str, val)
                    logging.debug('replace key: %s to %s', k, k_replaced)
                if k != k_replaced:
                    mailObject[k_replaced] = v
                    mailObject.pop(k)
                if v:
                    if isinstance(v, basestring) and v == k_replace_str:
                        mailObject[k] = val
                    self.replaceStr(key_str, val, v)
        if isinstance(mailObject, list):
            i = 0
            for obj in mailObject:
                logging.debug("start replace %s ", key_str)
                logging.debug(obj)
                if isinstance(obj, tuple):
                    logging.debug("tuple # replace")
                    mailObject[i] = (
                        obj[0],
                        obj[1].replace(
                            "{%s}" %
                            key_str,
                            val))
                else:
                    if isinstance(obj, basestring):
                        logging.debug("str # replace")
                        if obj == k_replace_str:
                            mailObject[i] = val
                        else:
                            mailObject[i] = obj.replace("{%s}" % key_str, val)
                    else:
                        if obj:
                            self.replaceStr(key_str, val, obj)
                i = i + 1

    def getFunctions(self, fun_dict={}, mailObject=None):
        if mailObject is None:
            mailObject = self.mail_object
        if isinstance(mailObject, dict):
            for k, v in mailObject.items():
                logging.debug("get fun for k:%s v:%s", k, v)
                if isinstance(v, basestring):
                    logging.debug("get fun from string v:%s", v)
                    m = re.match(r'\[function\](.*)', v)
                    if m:
                        logging.info("add function to %s", k)
                        fun_dict[k] = m.group(1)
                else:
                    self.getFunctions(fun_dict, v)
        if isinstance(mailObject, list):
            for obj in mailObject:
                if obj:
                    self.getFunctions(fun_dict, obj)
        if isinstance(mailObject, tuple) and len(mailObject) > 1:
            m = re.match(r'\[function\](.*)', mailObject[1])
            if m:
                logging.info("add function to %s", mailObject[0])
                fun_dict[mailObject[0]] = m.group(1)
        return fun_dict

    def getKeyFunctions(self, fun_dict={}, mailObject=None):
        if mailObject is None:
            mailObject = self.mail_object
        if isinstance(mailObject, dict):
            for k, v in mailObject.items():
                logging.debug("get fun for key:%s", k)
                m = re.search(r'{\[function\](.*)}', k)
                if m:
                    logging.info("add key function to %s", k)
                    fun_dict[k] = m.group(1)
                if v and not isinstance(v, basestring):
                    self.getKeyFunctions(fun_dict, v)
        if isinstance(mailObject, list):
            for obj in mailObject:
                if obj:
                    self.getKeyFunctions(fun_dict, obj)
        return fun_dict

    def setContent(self, mailObject, key_str, val):
        if isinstance(mailObject, dict):
            if key_str in mailObject.keys():
                mailObject[key_str] = val
                logging.info("replaced content of %s", key_str)
            else:
                for k, v in mailObject.items():
                    self.setContent(v, key_str, val)
        if isinstance(mailObject, list):
            i = 0
            for obj in mailObject:
                if isinstance(obj, tuple) and obj[0] == key_str:
                    mailObject[i] = (key_str, val)
                    logging.info("replaced content of %s", key_str)
                    return True
                self.setContent(obj, key_str, val)
                i = i + 1
        return False

    def contentFromObject(self, mailObject, level=0):
        # global bodyhtml
        bodyhtml = ""
        logging.debug(
            "bodyhtml: %s \n level: %d ,Object: %s",
            bodyhtml, level, mailObject)
        logging.debug("level: %d ,Object: %s", level, mailObject)
        section_value = mailObject
        if isinstance(mailObject, dict):
            logging.debug("object is dict")
            if level == 0:
                logging.debug("add Title")
                bodyhtml = self.createHtmlFromTemplate(
                    "title",
                    mailObject.keys()[0])
            if level == 1:
                bodyhtml = bodyhtml + self.createHtmlFromTemplate(
                    "section_title",
                    mailObject.keys()[0],
                    level)
            if level > 1:
                keyhtml = self.createHtmlFromTemplate(
                    "key",
                    self.createHtmlFromTemplate(
                        "text",
                        mailObject.keys()[0],
                        level))
                bodyhtml = bodyhtml + \
                    self.createHtmlFromTemplate("line", keyhtml)
            section_value = mailObject.values()[0]
        if isinstance(section_value, tuple):
            logging.debug("vaule is tuple")
            keyhtml = self.createHtmlFromTemplate(
                "key",
                self.createHtmlFromTemplate(
                    "text",
                    "%s:" %
                    section_value[0],
                    level))
            valhtml = self.createHtmlLeaf(
                section_value[1],
                level,
                withspace=False)
            bodyhtml = bodyhtml + \
                self.createHtmlFromTemplate("line", keyhtml + valhtml, level)
        if isinstance(section_value, basestring):
            logging.debug("get leaf string %s", section_value)
            bodyhtml = bodyhtml + \
                self.createHtmlLeaf(section_value, with_line=True, level=level)
        else:
            if isinstance(section_value, list):
                logging.debug("object/vaule is list")
                level = level + 1
                for section in section_value:
                    bodyhtml = bodyhtml + \
                        self.contentFromObject(section, level)
        return bodyhtml

    def createHtmlLeaf(
            self,
            section_value,
            level=0,
            with_line=False,
            withspace=True):
        logging.debug("with_line # %s", with_line)
        strhtml = ""
        if section_value.startswith('[link]'):
            # rep_value = re.sub(r"\[link\]", "", section_value)
            rep_value = section_value.replace('[link]', '')
            strhtml = self.createHtmlFromTemplate(
                "link",
                rep_value,
                level,
                withspace)
        else:
            if section_value.startswith('[mail]'):
                # rep_value = re.sub("\[mail\]", "", section_value)
                rep_value = section_value.replace('[mail]', '')
                strhtml = self.createHtmlFromTemplate(
                    "mail",
                    rep_value,
                    level,
                    withspace)
            else:
                if section_value.startswith('[bold]'):
                    section_value = self.createHtmlFromTemplate(
                        "key",
                        # re.sub("\[bold\]", "", section_value),
                        section_value.replace('[bold]', ''),
                        level,
                        withspace)
                logging.debug(
                    "##### template text for ### %s ####with_line# %s",
                    section_value, with_line)
                strhtml = self.createHtmlFromTemplate(
                    "text",
                    section_value,
                    level,
                    withspace)
        if with_line:
            return self.createHtmlFromTemplate("line", strhtml, level)
        logging.debug("##### template text is ### %s #####", strhtml)
        return strhtml

    def createHtmlFromTemplate(
            self,
            template,
            replace_value,
            level=0,
            withspace=True):
        htmlTemplate = os.path.join(config.get_config_path(),
                                    "template",
                                    "%s.html" % template)
        is_red_font = False
        if replace_value.startswith('[red]'):
            is_red_font = True
            replace_value = replace_value.split('[red]', 1)[1]
        newcontent = ""
        levelspace = ""
        if level > 0:
            space_number = level * 2
            if withspace:
                levelspace = '&nbsp;' * space_number
        with open(htmlTemplate, "r") as ft:
            content = ft.read()
            newcontent = content.replace("{%s}" % template, replace_value)
        if level > 1:
            font_size = 11 - level * 0.5
            font_style = 'style="font-size:%fpt"' % font_size
            if is_red_font:
                font_style = 'style="color:red;font-size:%fpt"' % font_size
        else:
            font_style = ''
            if is_red_font:
                font_style = 'style="color:red"'

        newcontent = newcontent.replace("{font_style}", font_style)
        return newcontent.replace("{levelspace}", levelspace)

    def set_receiver(self, pdict):
        if 'receiver' in pdict:
            self.receiver = pdict['receiver']
        else:
            if mailConfig.has_option(self.mail_type, "receiver"):
                self.receiver = mailConfig.get(
                    self.mail_type,
                    "receiver")
            else:
                logging.error("Please check the mail_type and receiver!")
                sys.exit(1)

    def send_mail(self):
        mailfile = os.path.join(os.getcwd(), "mailbody.html")
        self.createContentByTemplate(mailfile)

        recipents = self.receiver
        try:
            ccrecipents = mailConfig.get(self.mail_type, "cc_receiver")
        except config.NoOptionError as e:
            logging.warning(
                "Can't find %s.cc_receiver, for %s",
                self.mail_type, str(e))
        sender = mailConfig.get("mail_content", "sender")

        mail.SendHtmlMail(
            sender,
            recipents,
            ccrecipents,
            self.title,
            mailfile,
            attachments=[None])
