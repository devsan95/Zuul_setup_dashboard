import os
import paramiko
import codecs
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# %%
engine = sa.create_engine("mysql+mysqlconnector://root:hzscmzuul@10.159.11.27/doggy")
engine.connect()
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()


class merger_info(Base):
    __tablename__ = 'merger_info'

    id = sa.Column(sa.BIGINT, primary_key=True)

    more = sa.Column(sa.TEXT, server_default='')
    name = sa.Column(sa.VARCHAR(200), server_default='')
    ip = sa.Column(sa.VARCHAR(200), server_default='')
    enable = sa.Column(sa.VARCHAR(50), server_default='NO')
    zuul_url = sa.Column(sa.VARCHAR(500), server_default='')
    server_type = sa.Column(sa.VARCHAR(200), server_default='')
    last_update = sa.Column(sa.DATETIME, server_default=sa.func.current_timestamp())
    port_mapping = sa.Column(sa.VARCHAR(50), server_default='')
    version = sa.Column(sa.VARCHAR(100), server_default='')


hosts = [codecs.encode(x[0], 'utf-8') for x in session.query(merger_info.ip).distinct()]
print(hosts)

# %%

hosts = ['10.157.163.210', '10.159.10.139']
# hosts = ['10.157.163.210']
port = 22
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

for host in hosts:
    sv_type = codecs.encode(session.query(merger_info.server_type).filter_by(ip=host).first()[0], 'utf-8')

    if sv_type == "EELINSEE":
        os.system("scp -r /root/task1/ ca_5g_hz_scm@{}:~/".format(host))
        ssh.connect(host, port, "ca_5g_hz_scm")
    else:
        os.system("scp -r /root/task1/ root@{}:~/".format(host))
        ssh.connect(host, port, "root")

    channel = ssh.get_transport().open_session()
    channel.invoke_shell()

    while channel.recv_ready():
        channel.recv(1024)

    if sv_type == "EELINSEE":
        channel.sendall("source /home/ca_5g_hz_scm/mn_s/mn_scripts/pyenv.sh &> garytest_output.txt\n")
        channel.sendall("python /home/ca_5g_hz_scm/task1/testConnection.py {} &>> garytest_output.txt\n".format(host))
    else:
        channel.sendall("source /root/mn_scripts/pyenv.sh &> garytest_output.txt\n")
        channel.sendall("python /root/task1/testConnection.py {} &>> garytest_output.txt\n".format(host))

    ssh.close()
