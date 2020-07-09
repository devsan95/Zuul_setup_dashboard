# %%
import os
import sys
import time
import json

# ATTENTION: urlparse is not valid in python version 3
from urlparse import urlparse
from api import file_api
import codecs
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# %%

f = open('update_log.txt', 'w')

engine = sa.create_engine("mysql+mysqlconnector://root:hzscmzuul@10.159.11.27/doggy")
engine.connect()
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()


class merger_info(Base):
    __tablename__ = 'merger_info'

    id = sa.Column(sa.BIGINT, primary_key=True, autoincrement=True)

    more = sa.Column(sa.TEXT, server_default='')
    name = sa.Column(sa.VARCHAR(200), server_default='')
    ip = sa.Column(sa.VARCHAR(200), server_default='')
    enable = sa.Column(sa.VARCHAR(50), server_default='False')
    zuul_url = sa.Column(sa.VARCHAR(500), server_default='')
    server_type = sa.Column(sa.VARCHAR(200), server_default='')
    last_update = sa.Column(sa.DATETIME, server_default=sa.func.current_timestamp())
    port_mapping = sa.Column(sa.VARCHAR(50), server_default='')
    version = sa.Column(sa.VARCHAR(100), server_default='')


# %% Get the latest merger version from JFrog Artifactory

data = os.popen('curl -u ca_zuul_qa:Welcome567 -X GET https://artifactory-espoo1.int.net.nokia.com/artifactory/api'
                '/docker/zuul-local/v2/zuul-images/zuul-merger/tags/list').read()

s = json.loads(data)

for V in reversed(s["tags"]):
    if '-' not in V:
        latest_version = V
        break

# %%
mergers = []
containers = os.popen('docker ps -a --format "{{.Names}}"').read().split("\n")

for obs in containers:
    seg = obs.split("_")
    if seg[0] == "merger" and seg[-1].isdigit():
        mergers.append(obs)

f.write("Number of mergers in the host: %d\n" % len(mergers))

# We assume there is at least one merger in the current host
# exit the program if no merger exists
if len(mergers) == 0:
    f.write("No merger exists in the host, program exit.\n")
    f.close()
    exit(0)

print(len(mergers))

# %%
for merger in mergers:

    status = os.popen('docker ps -a --filter "name=%s" --format "{{.Status}}"' % merger).read().split(' ')[0]
    f.write("Merger name: " + str(merger) + "\t")
    f.write("Initial Status: %s\t" % status)

    # Only consider two status: Up and Exited
    # Now we are considering the case where status is Exited
    enable_after_update = True

    if status == "Exited":
        os.system('docker start %s' % merger)
        enable_after_update = False
        # Give enough time for container to start running
        time.sleep(5)

    # If container status isn't "Up", skip the current iteration
    if os.popen('docker ps -a --filter "name=%s" --format "{{.Status}}"' % merger).read().split(' ')[0] != "Up":
        f.write("Cannot run %s\n" % merger)
        continue

    local_version = os.popen('docker ps --filter "name=%s" --format "{{.Image}}"' % merger).read().split(':')[
        1].rstrip("\n")
    container_id = os.popen('docker ps --filter "name=%s" --format "{{.ID}}"' % merger).read().rstrip("\n")

    f.write("Current Version: %s\t" % local_version)
    f.write("Latest Version: %s\t" % latest_version)

    ports = os.popen("docker port {}".format(merger)).read().split("\n")

    # Get rid of the last empty element in the list
    ports.pop(-1)

    pm_str = ""

    for idx, item in enumerate(ports):
        p = "{}:{}".format(item.split("/tcp -> 0.0.0.0:")[1], item.split("/tcp -> 0.0.0.0:")[0])
        pm_str += "-p {} ".format(p)

    print(pm_str)

    # Check server type
    if "eslinb" in os.popen("hostname").read().rstrip("\n"):
        hostType = "EELINSEE"
    else:
        hostType = "Cloud"

    f.write("Server type: %s\t" % hostType)

    # copy conf files inside the container to the host according to its server type
    if hostType == "Cloud":
        os.system("docker cp {}:/etc/zuul/. /ephemeral/zuul_mergers/{}/etc/".format(container_id, merger))
    elif hostType == "EELINSEE":
        temp_dirt = file_api.TempFolder().get_directory()
        os.system("docker cp {}:/etc/zuul/. {}/".format(container_id, temp_dirt))

    if float(local_version.lstrip('v')) < float(latest_version.lstrip('v')):
        os.system("docker stop {}; docker rename {} old_merger_{}".format(merger, merger, merger.split('_')[-1]))

        # Run docker run command according to server type
        if hostType == "Cloud":
            os.system("docker run -itd --log-opt max-size=2g --log-opt max-file=1 --privileged {}-v"
                      "/ephemeral/zuul_mergers/{}/log/:/ephemeral/log/zuul/ -v "
                      "/ephemeral/zuul_mergers/{}/git/:/ephemeral/zuul/git/ -v "
                      "/ephemeral/zuul_mergers/{}/etc/:/etc/zuul/ --name {} "
                      "zuul-local.esisoj70.emea.nsn-net.net/zuul-images/zuul-merger:{}"
                      .format(pm_str, merger, merger, merger, merger,
                              latest_version))

        elif hostType == "EELINSEE":
            os.system("docker run -itd --log-opt max-size=2g --log-opt max-file=1 --privileged {}-v "
                      "/var/fpwork/{}/etc:/etc/zuul/ -v "
                      "/var/fpwork/{}/git/:/ephemeral/zuul/git/ -v "
                      "/var/fpwork/{}/log/:/ephemeral/log/zuul/ --name {} "
                      "zuul-local.esisoj70.emea.nsn-net.net/zuul-images/zuul-merger:{}"
                      .format(pm_str, merger, merger, merger, merger,
                              latest_version))

            os.system("docker cp {}/. {}:/etc/zuul/.".format(temp_dirt, merger))

        f.write("Renamed to old_merger_%s\t" % merger.split('_')[-1])
        f.write("Upgrade at %s\n" % os.popen("date").read())

    if not enable_after_update:
        os.system("docker stop {}".format(merger))

    # %% Update SQL database
    mg_name = [codecs.encode(x[0], 'utf-8') for x in session.query(merger_info.name).filter_by(ip=sys.argv[1]).all()]

    # Update table if merger exists in the sql database
    # Insert table if merger does not exist in the sql database
    if merger in mg_name:

        record = session.query(merger_info) \
            .filter(merger_info.name == merger) \
            .filter(merger_info.ip == sys.argv[1]).one()

        record.version = latest_version
        record.enable = enable_after_update

    else:
        # Retrieve zuul_url from sql database
        url_tmp = urlparse(
            codecs.encode(session.query(merger_info.zuul_url).filter_by(ip=sys.argv[1]).first()[0], 'utf-8'))

        # Modify data retrieved above to form a new one for inserting
        url_port = str(url_tmp.port)[:3] + merger.split('_')[-1]
        new_mapping = url_port + ":80"
        new_url = url_tmp.scheme + "://" + url_tmp.hostname + ":{}".format(url_port) + url_tmp.path

        # Retrieve server_type from sql database
        sv_type = codecs.encode(session.query(merger_info.server_type).filter_by(ip=sys.argv[1]).first()[0], 'utf-8')

        newObj = merger_info(more='TESTONLY',
                             name=merger,
                             ip=sys.argv[1],
                             enable="%r" % enable_after_update,
                             zuul_url=new_url,
                             server_type=sv_type,
                             port_mapping=new_mapping,
                             version=latest_version
                             )

        session.add(newObj)

    session.commit()

f.close()
