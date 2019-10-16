#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-
import fire
import ruamel.yaml as yaml
import smtplib
from email.mime.text import MIMEText


class MonitorStreams(object):
    def get_streams_in_yaml_file(self, config_yaml_path):
        data = yaml.load(open(config_yaml_path, 'r'), Loader=yaml.Loader)
        streams_in_yaml = []
        streams_list = data['streams']
        for stream in streams_list:
            streams_in_yaml.append(stream['name'])
        return streams_in_yaml

    def send_mail(self, need_update_streams, need_delete_streams):
        sender = "5g_hz.scm@nokia.com"
        receivers = ["I_HZ_5G_CB_SCM@internal.nsn.com"]
        mail_msg = """
        <p>Hello guys:</p>
        <p>when you receive this email, it means there is new stream added.</p>
        <p>below streams need to be added to yaml file</p>
        <p><b>{}</b></p>
        <p>below streams need to be deleted from yaml file</p>
        <p><b>{}</b></p>
        <p>yaml file:comp-deps/config/component-config.yaml</p>
        """.format(list(need_update_streams), list(need_delete_streams))
        message = MIMEText(mail_msg, 'html', 'utf-8')
        subject = "{} active, please update yaml file".format(list(need_update_streams))
        message['Subject'] = subject
        message['From'] = sender
        message['To'] = ";".join(receivers)
        try:
            smtpObj = smtplib.SMTP('mail.emea.nsn-intra.net')
            smtpObj.sendmail(sender, receivers, message.as_string())
            print("Send email success")
        except smtplib.SMTPException:
            print("Error: Can not send email")

    def compare(self, streams_info, config_yaml):
        yaml_streams = self.get_streams_in_yaml_file(config_yaml)
        update_streams = []
        delete_streams = []
        with open(streams_info, 'r') as f:
            active_streams = f.read().splitlines()
            for i in active_streams:
                if i.startswith('master_airph'):
                    active_streams.remove(i)
        for stream in active_streams:
            if stream not in yaml_streams:
                update_streams.append(stream)
        for stream in yaml_streams:
            if stream not in active_streams:
                delete_streams.append(stream)

        if update_streams:
            self.send_mail(update_streams, delete_streams)
            print('update_stream:{}'.format(update_streams))
            print('delete stream:{}'.format(delete_streams))


if __name__ == '__main__':
    fire.Fire(MonitorStreams)
