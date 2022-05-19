#!/usr/bin/python
# -*- coding: UTF-8 -*-
# =============================================================
# Copyright: 2012~2015 NokiaSiemensNetworks
# FullName: utils.mail
# Changes:
# ==============================================================
# Date: 2013-8-23
# Author:  klarke(miaoyun-klarke.guo@nsn.com)
# Comment:
# ==============================================================
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import logging
import os.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
sys.path.append(SCRIPT_DIR)


class mail(object):
    from_addr = "zuul.support@nokia-sbell.com"

    def __init__(self, subject, content, attachment=None, subtype='plain', to_addrs="I_EXT_MN_CDS_BTSSCM_ZUUL_SUPPORT@internal.nsn.com"):
        ''' get data to send the mail
        @param subject: str, subject for mail, title
        @param content: str, content of the mail
        @param attachment:  the files in attachment
        '''
        self.to_addrs = to_addrs
        self.smtp = None
        self.message = None
        self.init_smtp(subject)
        self.logger = logging.getLogger('error_statistic')
        if content:
            self.add_mail_content(content, subtype)
        if attachment:
            self.add_mail_attach(attachment)
        self.send_mail()
        self.close_smtp()

    def init_smtp(self, subject):
        self.smtp = smtplib.SMTP('mail.emea.nsn-intra.net')
        self.message = MIMEMultipart()
        self.message['Subject'] = subject
        self.message['From'] = self.from_addr
        self.message['To'] = self.to_addrs

    def send_mail(self):
        '''use to send mail
        @param from_addr: the sender's mail address
        @param to_addrs: the receivers
        @param cc_list: the cc list of the mail
        @param message: email.message.Message, include the content and the attachements
        '''
        # self.logger.info('From: '+self.from_addr+' To:'+self.to_addrs+' Message:'+self.message.as_string())
        self.smtp.sendmail(self.from_addr, self.to_addrs.split(";"), self.message.as_string())

    def close_smtp(self):
        self.smtp.close()

    def add_mail_content(self, content_str, subtype):
        ''' add mail content
        @param content_str: str, content of the mail
        '''
        mail_msg = MIMEText(content_str, subtype, 'utf-8')
        self.message.attach(mail_msg)

    def add_mail_attach(self, attach_list):
        ''' add attachment to mail
        @param attach_list: list, the files that want to be attached
        '''
        for filename in attach_list:
            source_file = open(filename, 'rb')
            attachment = MIMEApplication(source_file.read())
            attachment.add_header('Content-Disposition', 'attachment', filename=os.path.basename(filename))
            self.message.attach(attachment)
            self.logger.info('add %s as attachment', filename)


if __name__ == '__main__':
    mail('test adf', open('align_check.html').read(), None, 'html')
