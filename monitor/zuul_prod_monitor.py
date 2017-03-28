#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

"""
monitor the exception from logs of zuul-server ,zuul-merge
zuul-launcher and supervisord
"""
import re
import smtplib
import string
import commands

from api import file_watcher

from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText

_line_cache = {}
_max_line = 20
server = "mail.emea.nsn-intra.net"


def SendHtmlMail(sender, recipents, ccrecipents, title, content):
    msgRoot = MIMEMultipart('related')
    msgRoot['Subject'] = title
    msgRoot['From'] = sender
    msgRoot['To'] = recipents
    msgRoot['CC'] = ccrecipents

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
    ccrecipents = "5g_hz.scm@nokia.com"
    hostname = commands.getoutput("hostname")

    title = 'Found error in {}'.format(filename) + " @ " + hostname
    if filename not in _line_cache:
        _line_cache[filename] = []
    for line in lines:
        line = line.strip('\n')
        _line_cache[filename].append(line)
    if len(_line_cache[filename]) > _max_line:
        _line_cache[filename] = _line_cache[filename][
            len(_line_cache[filename]) - _max_line:]
    for content in lines:
        error = re.findall(r'ERROR|WARNING|Traceback|Exception',
                           content, flags=re.IGNORECASE)

        if error:
            mail_content = 'With Following error lines:<br>'
            for line in _line_cache[filename]:
                mail_content += '<br>'
                mail_content += line
            _line_cache[filename] = []
            SendHtmlMail(sender, receiver, ccrecipents, title,
                         mail_content)
        break


if __name__ == '__main__':

    watcher = file_watcher.FileWatcher(
        ['/tmp/supervisord.log', '/ephemeral/log/zuul/server-debug.log',
         '/ephemeral/log/zuul/merger-debug.log',
         '/ephemeral/log/zuul/launcher-debug.log',
         '/ephemeral/log/zuul/gearman-debug.log'],
        analyse_log, 0)
    watcher.loop()
