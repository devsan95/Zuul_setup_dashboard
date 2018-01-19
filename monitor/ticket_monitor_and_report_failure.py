#! /usr/bin/env python2.7
# -*- coding:utf8 -*-
import argparse
import traceback
import sys
from api import gerrit_rest
import json
import re
import time
import smtplib
from email.mime.text import MIMEText


def _parse_args():
    parser = argparse.ArgumentParser(description='Monitor ticket status')
    parser.add_argument('server', type=str,
                        help='server url of gerrit')
    parser.add_argument('user', type=str,
                        help='user of gerrit')
    parser.add_argument('pwd', type=str,
                        help='Http password of the user')
    parser.add_argument('change_id', type=str,
                        help='change id')

    args = parser.parse_args()

    return vars(args)


def get_ticket_id_list_in_commonts(dic):
    json_re = re.compile(r'Tickets-List: ({.*})')
    for item in reversed(dic['messages']):
        result_list = json_re.findall(item['message'])
        if len(result_list) > 0:
            ticket_dic = json.loads(result_list[0])
            ticket_list = []
            for key in ticket_dic:
                if type(ticket_dic[key]) == list:
                    for i in ticket_dic[key]:
                        ticket_list.append(i)
                else:
                    ticket_list.append(ticket_dic[key])
            print(ticket_list)
            return ticket_list
    return None


def get_ticket_status_via_labels(ticket, rest):
    dic = rest.get_detailed_ticket(ticket)
    for key in dic["labels"]:
        if "rejected" in dic["labels"][key]:
            return 0
    if "approved" in dic["labels"]["Gatekeeper"]:
        return 1
    return 2


def get_reviewer_email_list(ticket, rest):
    dic = rest.get_detailed_ticket(ticket)
    email_list = []
    print(type(dic["reviewers"]["REVIEWER"]))
    reviewer_lists = dic["reviewers"]["REVIEWER"]
    for reviewer_list in reviewer_lists:
        print(reviewer_list)
        if "email" in reviewer_list:
            email_list.append(reviewer_list["email"])
    print("Email list : " + str(email_list))
    return email_list


def send_mail(email_list, ticket):
    sender = "5g_hz.scm@nokia.com"
    receivers = email_list
    print(receivers)
    mail_msg = """
    <p>Ticket Fail</p>
    <p><a href="https://gerrit.ext.net.nokia.com/gerrit/#/c/{}">
    Please fix it! <br>
    Click this url to the ticket</a></p>
    """.format(ticket)
    message = MIMEText(mail_msg, 'html', 'utf-8')
    subject = 'Ticket ' + str(ticket) + " fail, please check"
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = ";".join(receivers)
    try:
        smtpObj = smtplib.SMTP('mail.emea.nsn-intra.net')
        smtpObj.sendmail(sender, receivers, message.as_string())
        print("Send email success")
    except smtplib.SMTPException:
        print("Error: Can not send email")


def _main(server, user, pwd, change_id):
    ticket_list = None
    rest = gerrit_rest.GerritRestClient(server, user, pwd)

    while not ticket_list:
        detail_info = rest.get_detailed_ticket(change_id)
        ticket_list = get_ticket_id_list_in_commonts(detail_info)
        sys.stdout.flush()
        print("sleep 5 s")
        time.sleep(5)

    all_success = False
    fail_ticket_list = []
    while not all_success:
        print("ticket list: " + str(ticket_list))
        for ticket in ticket_list:
            print("ticket is " + str(ticket))
            result = get_ticket_status_via_labels(ticket, rest)
            if 1 == result:
                print("Ticket {} success".format(ticket))
                # Remove success ticket
                ticket_list.remove(ticket)
                if ticket in fail_ticket_list:
                    fail_ticket_list.remove(ticket)
            elif 0 == result:
                if ticket not in fail_ticket_list:
                    fail_ticket_list.append(ticket)
                    email_list = get_reviewer_email_list(ticket, rest)
                    send_mail(email_list, ticket)
            else:
                print("Ticket {} is running please waiting...".format(ticket))
        if not ticket_list:
            all_success = True
        else:
            time.sleep(30)


if __name__ == '__main__':
    try:
        param = _parse_args()
        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
