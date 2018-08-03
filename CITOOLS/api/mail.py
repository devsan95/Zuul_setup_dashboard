#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import os
import smtplib
import string
import email
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText

import config

conf = config.ConfigTool()
conf.load('mail')


def SendHtmlMail(sender, recipents, ccrecipents, title, content,
                 attachments=[None]):
    msgRoot = MIMEMultipart('related')
    msgRoot['Subject'] = title
    msgRoot['From'] = sender
    msgRoot['To'] = recipents
    msgRoot['CC'] = ccrecipents

    msgAlternative = MIMEMultipart('mixed')
    msgRoot.attach(msgAlternative)
    attachContent = open(os.path.join(os.getcwd(), content), "r").read()
    msgHtml = MIMEText(attachContent, 'html')
    msgAlternative.attach(msgHtml)

    for attachment in attachments:
        if attachment:
            if os.path.isfile(attachment):
                contype = 'application/octet-stream'
                maintype, subtype = contype.split('/', 1)
                data = open(attachment, 'r')
                file_msg = email.MIMEBase.MIMEBase(maintype, subtype)
                file_msg.set_payload(data.read())
                data.close()
                email.Encoders.encode_base64(file_msg)
                basename = os.path.basename(attachment)
                file_msg.add_header('Content-Disposition', 'attachment',
                                    filename=basename)
                msgAlternative.attach(file_msg)
            else:
                raise Exception("Unable to find the specified mail attachment "
                                "at %s" % attachment)
    # Send the email (this example assumes SMTP authentication is required)
    smtp = smtplib.SMTP()
    server = conf.get("mail_server", "server")
    print("Connecting to mail server")
    try:
        smtp.connect(server)
    except Exception as ex:
        print('Exception occur: %s' % str(ex))
        server = conf.get("mail_server", "bkserver")
        smtp.connect(server)

    smtp.sendmail(sender, string.split(recipents, ";") +
                  string.split(ccrecipents, ","), msgRoot.as_string())
    print("Mail has been sent out.")
    smtp.quit()
