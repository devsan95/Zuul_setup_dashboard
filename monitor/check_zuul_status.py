import os
import sys
import socket

import citools
import api.mail
import api.config
import api.error_check
import api.telnet_client
import gearman_status

conf = api.config.ConfigTool()
conf.load('zuul')
conf.load('mail')


class ZuulCheck(object):

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.gearman_status = gearman_status.GearmanStatus(host, port)
        self.jenkins_list = conf.get('Monitor', 'jenkins_list')
        self.exec_list = self.gearman_status.get_workers_bytype('exec')
        self.exec_name_list = self.get_key_list(self.exec_list, 'host')
        self.warn_msgs = []

    def warn_msg(self, msg):
        self.warn_msgs.append(msg)

    def get_key_list(self, dt_list, key):
        key_list = []
        for dt in dt_list:
            if dt[key]:
                key_list.append(dt[key])
        return key_list

    def check_jenkins_exists(self):
        ret = True
        for jenkins in self.jenkins_list.splitlines():
            if socket.gethostbyname(jenkins) not in self.exec_name_list:
                self.warn_msg('jenkins %s not in worker list' % jenkins)
                ret = False
        return ret

    def check_extra_jenkins(self):
        ret = True
        for worker_obj in self.exec_list:
            if worker_obj['host'] not in self.jenkins_list:
                self.warn_msg(
                    'external jenkins %s connect to gearman server %s:%s' %
                    (worker_obj['host'], self.host, self.port))
                ret = False
        return ret

    def check_jenkins_jobs(self):
        ret = True
        for worker_obj in self.exec_list:
            if not worker_obj['jobs']:
                self.warn_msg(
                    'jenkins %s job list is empty' %
                    worker_obj['host'])
                ret = False
        return ret

    def check(self):
        err_check_obj = api.error_check.ErrCheck()
        err_check_obj.add_check(
            'check_jenkins_exits',
            self.check_jenkins_exists,
            'there is jenkins not in worker list')
        err_check_obj.add_check(
            'check_extra_jenkins',
            self.check_extra_jenkins,
            'not known jenkins connect to gearman server %s:%s' %
            (self.host,
             self.port))
        err_check_obj.add_check(
            'check_extra_jenkins',
            self.check_jenkins_jobs,
            'there is jenskins job list is empty')
        err_msgs, err_num, pass_num = err_check_obj.check()
        head_msg = "Errors: %s <br>Passed check: %d" % (err_msgs, pass_num)
        mail_content = head_msg + '<br>' + '<br>'.join(self.warn_msgs)
        print mail_content
        if err_num > 0:
            self.send_warn_msg(mail_content)
            sys.exit(2)

    def send_warn_msg(self, content):
        mailfile = os.path.join(os.getcwd(), "mailbody.html")
        with open(mailfile, "w") as fi:
            fi.write(content)
        sender = conf.get("mail_content", "sender")
        recipents = conf.get("zuul_monitor", "receiver")
        ccrecipents = conf.get("zuul_monitor", "cc_receiver")
        title = "[WARN] someting abnormal in zuul"
        api.mail.SendHtmlMail(
            sender,
            recipents,
            ccrecipents,
            title,
            mailfile,
            attachments=[None])

if __name__ == "__main__":
    zuul_check_obj = ZuulCheck(
        conf.get(
            'Monitor', 'gearman_server'), conf.get(
            'Monitor', 'gearman_port'))
    zuul_check_obj.check()
