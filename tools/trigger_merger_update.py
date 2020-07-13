import os
import paramiko
import codecs
import fire
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from database import model
from update_zuul_merger_auto import get_connection_string


def get_all_ip_from_db(session, table):
    return [codecs.encode(x[0], 'utf-8') for x in session.query(table.ip).distinct()]


def get_server_type_by_ip(session, table, ip):
    return codecs.encode(session.query(table.server_type).filter_by(ip=ip).first()[0], 'utf-8')


def get_ssh_port(session, table, ip):
    return codecs.encode(session.query(table.ssh_port).filter_by(ip=ip).first()[0], 'utf-8')


def trigger_script(session, table, host, ssh, port, folder):
    sv_type = get_server_type_by_ip(session, table, host)

    if sv_type == "EELINSEE":
        os.system("scp -r {} ca_5g_hz_scm@{}:/tmp/".format(folder, host))
        ssh.connect(host, port, "ca_5g_hz_scm")
    else:
        os.system("scp -r {} root@{}:///tmp/".format(folder, host))
        ssh.connect(host, port, "root")

    channel = ssh.get_transport().open_session()
    channel.invoke_shell()

    while channel.recv_ready():
        channel.recv(1024)

    channel.sendall('git clone "https://gerrit.ext.net.nokia.com/gerrit/MN/SCMTA/zuul/mn_scripts" {}/mn &> '
                    'garytest_output.txt\n'.format(folder))
    channel.sendall("source {}/mn/pyenv.sh &>> garytest_output.txt\n".format(folder))
    channel.sendall("python {}/update_zuul_merger_auto.py --ip {} --path {}/param.yaml "
                    "&>> garytest_output.txt\n".format(folder, host, folder))

    ssh.close()


def apply_for_all(session, table, folder):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    for host in get_all_ip_from_db(session, table):
        port = get_ssh_port(session, table, host)
        trigger_script(session, table, host, ssh, int(port), folder)

    # for host in ["10.157.4.246"]:
    #     port = get_ssh_port(session, table, host)
    #     trigger_script(session, table, host, ssh, int(port), folder)


def main(yaml_path, folder):
    engine = sa.create_engine(get_connection_string(yaml_path))
    engine.connect()
    Session = sessionmaker(bind=engine)
    session = Session()

    apply_for_all(session, model.merger_info, folder)


if __name__ == '__main__':
    fire.Fire(main)
