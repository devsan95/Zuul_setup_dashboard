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


class Rest:
    def __init__(self, server, user, pwd):
        self.server = server
        self.user = user
        self.pwd = pwd

    def gerrit_rest_factory(self):
        rest = gerrit_rest.GerritRestClient(self.server, self.user, self.pwd)
        return rest


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
            return "Fail"
    print("heng " + str(dic["labels"]))
    if "approved" in dic["labels"]["Gatekeeper"]:
        return "Success"
    return "Ticket is running"


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
    sender = "dongsheng.xuan@nokia-sbell.com"
    receivers = "dongsheng.xuan@nokia-sbell.com"
    mail_msg = """
    <p>I am your GOD FATHER</p>
    <p><a href="http://10.181.36.136">Click this url to the ticket</a></p>
    """
    message = MIMEText(mail_msg, 'html', 'utf-8')
    subject = 'Ticket ' + str(ticket) + " fail, please check"
    message['Subject'] = subject
    message["CC"] = "dongsheng.xuan@nokia-sbell.com"
    message['From'] = "dongsheng.xuan@nokia-sbell.com"
    message['To'] = "dongsheng.xuan@nokia-sbell.com; zhiqi.xie@nokia.com"
    try:
        smtpObj = smtplib.SMTP('mail.emea.nsn-intra.net')
        smtpObj.sendmail(sender, receivers, message.as_string())
        print("Send email success")
    except smtplib.SMTPException:
        print("Error: Can not send email")


def _main(server, user, pwd, change_id):
    ticket_list = None
    rest = gerrit_rest.GerritRestClient(server, user, pwd)

    # if ticket_list is none
    while not ticket_list:
        detail_info = rest.get_detailed_ticket(change_id)
        ticket_list = get_ticket_id_list_in_commonts(detail_info)
        sys.stdout.flush()
        print("sleep 5 s")
        time.sleep(5)

    all_success = False
    while not all_success:
        print("@@@@@@@@@@@@@@@@@@@@^^^^" + str(ticket_list))
        for ticket in ticket_list:
            print("///////////////////ticket is " + str(ticket))
            result = get_ticket_status_via_labels(ticket, rest)
            if "Success" == result:
                print("Ticket {} success".format(ticket))
                # Remove success ticket
                ticket_list.remove(ticket)
            elif "Fail" == result:
                email_list = get_reviewer_email_list(ticket, rest)
                print("sending email...")
                send_mail(email_list, ticket)
            else:
                print("Ticket {} is running please waiting...".format(ticket))
        if not len(ticket_list):
            all_success = True
        else:
            time.sleep(30)


if __name__ == '__main__':
    try:
        param = _parse_args()

        _main(**param)
        # _main("https://gerrit.ext.net.nokia.com/gerrit/", "dxuan",
        # "1+Czg8LHYyXjG1U8Nzd+rVgBSd9909sj8WdEI904DA", "199778")
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
