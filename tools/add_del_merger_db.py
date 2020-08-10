from update_zuul_merger_auto import collect_mergers
from update_zuul_merger_auto import check_server_type
from update_zuul_merger_auto import get_connection_string
from trigger_merger_update import get_all_ip_from_db
from database import model
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
import logging
import os
import fire
import StringIO
import configparser
import codecs
from urlparse import urlparse

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')


def get_port_mapping(merger):
    ports = os.popen("docker port {}".format(merger)).read().split("\n")
    ports.pop(-1)

    for port in ports:
        if "80/tcp" in port:
            return "{}:{}".format(port.split("/tcp -> 0.0.0.0:")[1], port.split("/tcp -> 0.0.0.0:")[0])
    return "None"


def get_merger_version(merger):
    return os.popen('docker ps -a --filter "name=^/%s$" --format "{{.Image}}"' % merger).read().split(':')[1].rstrip("\n")


def check_merger_status(merger):
    status = os.popen('docker ps -a --filter "name=^/%s$" --format "{{.Status}}"' % merger).read().split(' ')[0]
    if status != "Up":
        return False
    return True


def get_zuul_url(merger):
    conf = os.popen('docker exec -t {} bash -c "cat /etc/zuul/zuul.conf"'.format(merger)).read()
    buf = StringIO.StringIO(conf)
    config = configparser.ConfigParser()
    config.read_file(buf)
    return config.get('merger', 'zuul_url')


def del_from_db(session, ip, table):
    if ip in get_all_ip_from_db(session, table):
        session.query(table).filter(table.ip == ip).delete(synchronize_session=False)
        session.commit()
    else:
        logging.info("IP does not exist in the sql database.")


def result_mergers(session, ip, table):
    mergers = collect_mergers()
    if ip in get_all_ip_from_db(session, table):
        exist_merger = [codecs.encode(x[0], 'utf-8') for x in session.query(table.name).filter_by(ip=ip).all()]
        for e in exist_merger:
            logging.info("{} already exists in the database!".format(e))
        return list(set(mergers) - set(exist_merger))
    return mergers


def add_into_db(session, ip, table):
    serverType = check_server_type()
    for m in result_mergers(session, ip, table):
        enable = check_merger_status(m)
        version = get_merger_version(m)

        if enable:
            portMapping = get_port_mapping(m)
            zuul_url = get_zuul_url(m)
            new_row = model.merger_info(more="TEST",
                                        name=m,
                                        ip=ip,
                                        enable=str(int(enable)),
                                        zuul_url=zuul_url,
                                        server_type=serverType,
                                        port_mapping=portMapping,
                                        version=version)
            session.add(new_row)
            session.commit()
        else:
            # As long as there exits one merger of the same ip in the database
            # zuul_url and port_mapping of other mergers can be generated directly
            if ip in get_all_ip_from_db(session, table):
                url_tmp = urlparse(codecs.encode(session.query(table.zuul_url).filter_by(ip=ip).first()[0], 'utf-8'))
                url_port = str(url_tmp.port)[:3] + m.split('_')[-1]
                new_mapping = url_port + ":80"
                new_url = url_tmp.scheme + "://" + url_tmp.hostname + ":{}".format(url_port) + url_tmp.path
                new_row = model.merger_info(more="TEST",
                                            name=m,
                                            ip=ip,
                                            enable=str(int(enable)),
                                            zuul_url=new_url,
                                            server_type=serverType,
                                            port_mapping=new_mapping,
                                            version=version)
                session.add(new_row)
                session.commit()
            else:
                logging.warning("All merger containers are closed on instance {}, please run the container and try again!.".format(ip))


def run(session, ip, option):
    if option == "del":
        del_from_db(session, ip, model.merger_info)
    elif option == "add":
        add_into_db(session, ip, model.merger_info)


def main(ip, path, option):
    engine = sa.create_engine(get_connection_string(path))
    engine.connect()
    Session = sessionmaker(bind=engine)
    session = Session()

    run(session, ip, option)


if __name__ == '__main__':
    fire.Fire(main)
