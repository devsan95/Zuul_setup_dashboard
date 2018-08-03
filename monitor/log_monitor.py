#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

"""
monitor the exception from logs of zuul-server ,zuul-merge
zuul-launcher and supervisord
"""
import re
import time
import os
import smtplib
import string
import commands

from api import file_watcher

from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText


def SendHtmlMail(sender, recipents, ccrecipents, title, content):
    msgRoot = MIMEMultipart('related')
    msgRoot['Subject'] = title
    msgRoot['From'] = sender
    msgRoot['To'] = recipents
    msgRoot['CC'] = ccrecipents
    server = "mail.emea.nsn-intra.net"

    msgAlternative = MIMEMultipart('mixed')
    msgRoot.attach(msgAlternative)
    attachContent = content
    msgHtml = MIMEText(attachContent, 'html')
    msgAlternative.attach(msgHtml)

    # Send the email (this example assumes SMTP authentication is required)
    smtp = smtplib.SMTP()
    print("Connecting to mail server")
    try:
        smtp.connect(server)
    except Exception as ex:
        print('Exception occur: %s' % str(ex))
        smtp.connect(server)

    smtp.sendmail(sender, string.split(recipents, ";") +
                  string.split(ccrecipents, ","), msgRoot.as_string())
    print("Mail has been sent out.")
    smtp.quit()


def analyse_log(filename, lines):
    sender = "5g_hz.scm@nokia.com"
    receiver = "I_5G_HZ_SCM@internal.nsn.com"
    ccrecipents = " "
    hostname = commands.getoutput("cat /etc/hostname")
    title = 'Found error in {}'.format(filename) + " @ " + hostname

    if filename not in _mail_content:
        _mail_content[filename] = ''
    if filename not in _time_flag:
        _time_flag[filename] = int(time.time())
    for line in lines:
        error = re.findall(r'ERROR|WARNING |Traceback|Exception',
                           line, flags=re.IGNORECASE)
        if error:
            _mail_content[filename] += '<br>With following errors:<br>'
            _mail_content[filename] += line
            _mail_content[filename] += '<br>'
    time_curr = int(time.time())
    if time_curr - _time_flag[filename] >= _time_slice:
        if _mail_content[filename]:
            SendHtmlMail(sender, receiver, ccrecipents, title,
                         _mail_content[filename])
            _time_flag[filename] = time_curr
            _mail_content[filename] = ''


if __name__ == '__main__':
    _mail_content = {}
    _time_slice = 60
    if 'time_slice' in os.environ.keys():
        _time_slice = int(os.environ["time_slice"]) * 60
    _time_flag = {}
    watcher = file_watcher.FileWatcher(
        ['/tmp/supervisord.log', '/ephemeral/log/zuul/server-debug.log',
         '/ephemeral/log/zuul/merger-debug.log',
         '/ephemeral/log/zuul/launcher-debug.log',
         '/ephemeral/log/zuul/gearman-debug.log'],
        analyse_log, 0)
    watcher.loop()
