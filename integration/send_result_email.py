import jinja2
import json
import codecs
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def generate_html(info_index):
    template_content = None
    template_path = info_index['meta']['template']
    if not os.path.exists(template_path):
        template_path = 'email_templates/' + template_path
    if not os.path.exists(template_path):
        raise Exception('Path {} not exist!'.format(template_path))
    with open(template_path) as f:
        template_content = f.read()
    template_content = codecs.decode(template_content, 'utf8')
    template = jinja2.Template(template_content)
    content = {'meta': info_index['meta'],
               'scm_changes': [],
               'user_changes': []}
    for name, node in info_index['nodes'].iteritems():
        if 'type' in node and \
                (node['type'] == 'root' or node['type'] == 'integration'):
            content['scm_changes'].append(node)
        else:
            content['user_changes'].append(node)
    return template.render(content)


def send_email(info_index, content):
    title = '{}, {}'.format(info_index['meta']['version_name'],
                            info_index['meta']['title'])
    to = []
    cc = []
    bcc = []
    if 'to' in info_index['meta']['email']:
        to = info_index['meta']['email']['to']
    if 'cc' in info_index['meta']['email']:
        cc = info_index['meta']['email']['cc']
    if 'bcc' in info_index['meta']['email']:
        bcc = info_index['meta']['email']['bcc']

    sender = '5g_hz.scm@nokia.com'

    msg = MIMEMultipart('alternative')
    msg['Subject'] = title
    msg['From'] = sender
    msg['To'] = ','.join(to)
    msg['CC'] = ','.join(cc)

    # Create the body of the message (a plain-text and an HTML version).
    html = codecs.encode(content, 'utf8')

    # Record the MIME types of both parts - text/plain and text/html.
    part = MIMEText(html, 'html')

    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.
    msg.attach(part)

    # Send the message via local SMTP server.
    s = smtplib.SMTP('mail.emea.nsn-intra.net')
    s.sendmail(sender, to + cc + bcc, msg.as_string())
    s.quit()


def run(info_index):
    content = generate_html(info_index)
    with open('result.html', 'w') as f:
        f.write(codecs.encode(content, 'utf8'))
    send_email(info_index, content)


if __name__ == '__main__':
    dict1 = None
    with open('info_index.json') as f:
        dict1 = json.load(f)
    run(dict1)
