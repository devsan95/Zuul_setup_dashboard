import os
import yaml
import time
import json
import fire
import requests
import logging
import subprocess
from datetime import datetime
from requests.auth import HTTPBasicAuth
from pkg_resources import parse_version
from urlparse import urlparse
from api import file_api
import codecs
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from database import model

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')


def get_yaml_object(path):
    return yaml.safe_load(open(path))


def collect_mergers():
    merger_list = []
    containers = os.popen('docker ps -a --format "{{.Names}}"').read().split("\n")

    for obs in containers:
        seg = obs.split("_")
        if seg[0] == "merger" and seg[-1].isdigit() and "bak" not in obs:
            merger_list.append(obs)

    return merger_list


def get_latest_merger_version(path):
    obj = get_yaml_object(path)
    data = requests.get(obj["artifactory"]["url"],
                        auth=HTTPBasicAuth(obj["artifactory"]["user"], obj["artifactory"]["pass"])).text
    for v in reversed(json.loads(data)["tags"]):
        if '-' not in v:
            return v
    return None


def get_connection_string(path):
    obj = get_yaml_object(path)
    return "{}+{}://{}:{}@{}/{}".format(obj["sql"]["dialect"], obj["sql"]["driver"], obj["sql"]["user"],
                                        obj["sql"]["pass"], obj["sql"]["host"], obj["sql"]["db"])


def generate_port_mapping_string(merger):
    ports = os.popen("docker port {}".format(merger)).read().split("\n")
    # Get rid of the last empty element in the list
    ports.pop(-1)

    string = ""
    for idx, item in enumerate(ports):
        p = "{}:{}".format(item.split("/tcp -> 0.0.0.0:")[1], item.split("/tcp -> 0.0.0.0:")[0])
        string += "-p {} ".format(p)
    return string


def check_server_type():
    if "eslinb" in os.popen("hostname").read().rstrip("\n"):
        return "EELINSEE"
    return "Cloud es-si-os-ohn-64"


def get_docker_run_cmd(portMapStr, merger, latestVersion):
    if check_server_type() == "Cloud es-si-os-ohn-64":
        cmd = "docker run -itd --log-opt max-size=2g --log-opt max-file=1 --privileged {}-v /ephemeral/zuul_mergers/{}/log/:/ephemeral/log/zuul/ -v /ephemeral/zuul_mergers/{}/git/:/ephemeral/zuul/git/ -v /ephemeral/zuul_mergers/{}/etc/:/etc/zuul/ --name {} zuul-local.esisoj70.emea.nsn-net.net/zuul-images/zuul-merger:{}".format(
            portMapStr, merger, merger, merger, merger, latestVersion)
    else:
        cmd = "docker run -itd --log-opt max-size=2g --log-opt max-file=1 --privileged {}-v /var/fpwork/{}/etc:/etc/zuul/ -v /var/fpwork/{}/git/:/ephemeral/zuul/git/ -v /var/fpwork/{}/log/:/ephemeral/log/zuul/ --name {} zuul-local.esisoj70.emea.nsn-net.net/zuul-images/zuul-merger:{}".format(
            portMapStr, merger, merger, merger, merger, latestVersion)
    return cmd


def update_merger(merger, pm_str, latest_version, container_id, ip):
    # Check whether a docker image can be pulled
    res = subprocess.call(
        "docker pull zuul-local.esisoj70.emea.nsn-net.net/zuul-images/zuul-merger:{}".format(latest_version),
        shell=True)
    if res != 0:
        raise Exception("Cannot pull image at instance {}".format(ip))

    now = datetime.now()
    date = now.strftime("%Y") + now.strftime("%m") + now.strftime("%d")
    # Copy conf files inside the container to the host according to its server type
    # Before the old server is stopped and renamed
    temp_dirt = file_api.TempFolder().get_directory()
    os.system("docker cp {}:/etc/zuul/. {}".format(container_id, temp_dirt))
    os.system("docker stop {}; docker rename {} {}_bak_{}".format(merger, merger, merger, date))

    # Run docker run command according to server type
    os.system(get_docker_run_cmd(pm_str, merger, latest_version))

    os.system("docker cp {}/. {}:/etc/zuul/.".format(temp_dirt, merger))
    logging.info("Renamed to {}_bak_{}\t".format(merger, date))
    logging.info("Upgrade at %s\n", os.popen("date").read())


def update_sql_table(session, merger, table, ip, version, enable):
    mg_name = [codecs.encode(x[0], 'utf-8') for x in session.query(table.name).filter_by(ip=ip).all()]
    # Update table if merger exists in the sql database
    # Insert table if merger does not exist in the sql database
    if merger in mg_name:
        record = session.query(table).filter(table.name == merger).filter(table.ip == ip).one()
        record.version = version
        record.enable = enable

    else:
        # Retrieve zuul_url from sql database
        url_tmp = urlparse(codecs.encode(session.query(table.zuul_url).filter_by(ip=ip).first()[0], 'utf-8'))
        # Modify data retrieved above to form a new one for inserting
        url_port = str(url_tmp.port)[:3] + merger.split('_')[-1]
        new_mapping = url_port + ":80"
        new_url = url_tmp.scheme + "://" + url_tmp.hostname + ":{}".format(url_port) + url_tmp.path
        # Retrieve server_type from sql database
        sv_type = codecs.encode(session.query(table.server_type).filter_by(ip=ip).first()[0], 'utf-8')
        new_row = model.merger_info(more='NEW',
                                    name=merger,
                                    ip=ip,
                                    enable="%r" % enable,
                                    zuul_url=new_url,
                                    server_type=sv_type,
                                    port_mapping=new_mapping,
                                    version=version
                                    )
        session.add(new_row)
    session.commit()


def update_all(ip, path, session):
    for merger in collect_mergers():
        status = os.popen('docker ps -a --filter "name=^/%s$" --format "{{.Status}}"' % merger).read().split(' ')[0]
        logging.info("Merger name: {}, Initial status {}".format(str(merger), status))

        # Only consider two status: Up and Exited
        # Now we are considering the case where status is Exited
        enable_after_update = True

        if status == "Exited":
            os.system('docker start %s' % merger)
            enable_after_update = False
            # Give enough time for container to start running
            time.sleep(5)

        # If container status isn't "Up", skip the current iteration
        if os.popen('docker ps -a --filter "name=^/%s$" --format "{{.Status}}"' % merger).read().split(' ')[0] != "Up":
            logging.warning("Cannot run %s", merger)
            return

        container_id = os.popen('docker ps --filter "name=^/%s$" --format "{{.ID}}"' % merger).read().rstrip("\n")
        local_version = os.popen('docker ps --filter "name=^/%s$" --format "{{.Image}}"' % merger).read().split(':')[
            1].rstrip("\n")
        latest_version = get_latest_merger_version(path)
        pm_str = generate_port_mapping_string(merger)
        host_type = check_server_type()

        logging.info(
            "Current Version: {}, Latest Version: {}, Server type: {}".format(local_version, latest_version, host_type))

        # Perform actions only when container is not the latest one
        if parse_version(local_version) < parse_version(latest_version):
            update_merger(merger, pm_str, latest_version, container_id, ip)
            logging.info("Merger is updated to the latest version {}".format(latest_version))
        elif parse_version(local_version) == parse_version(latest_version):
            logging.info("Merger is already the latest version")

        if not enable_after_update:
            os.system("docker stop {}".format(merger))

        update_sql_table(session, merger, model.merger_info, ip, latest_version, enable_after_update)


def main(ip, path):
    engine = sa.create_engine(get_connection_string(path))
    engine.connect()
    Session = sessionmaker(bind=engine)
    session = Session()

    num_merger = len(collect_mergers())
    logging.info("Number of mergers in instance {}: {}".format(ip, num_merger))

    # We assume there is at least one merger in the current host
    # exit the program if no merger exists
    if num_merger == 0:
        logging.warning("No merger exists in instance {}, program exit".format(ip))
        exit(0)

    update_all(ip, path, session)


if __name__ == '__main__':
    fire.Fire(main)

# %%
