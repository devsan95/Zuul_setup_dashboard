"""
This script is created for independent gearman server setup
support Python2 and Python3, gear==0.13.0
"""

import os
import gear
import signal
import logging
import extras

log = logging.getLogger()
pid_file_module = extras.try_imports(['daemon.pidlockfile', 'daemon.pidfile'])
MASS_DO = 101


def logging_setup(level='debug'):
    _mapping = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'error': logging.ERROR,
        'warning': logging.WARNING
    }
    logging.basicConfig(level=_mapping.get(level),
                        format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                        filename='/tmp/test.log',
                        datefmt='%a, %d %b %Y %H:%M:%S')


class GearServer(gear.Server):
    def handlePacket(self, packet):
        if packet.ptype == MASS_DO:
            # self.log.info("Received packet from %s: %s" % (str(packet.connection), packet))
            self.handleMassDo(packet)
        else:
            super(GearServer, self).handlePacket(packet)

    def handleMassDo(self, packet):
        packet.connection.functions = set()
        for name in packet.data.split(b'\x00'):
            # self.log.debug("Adding function %s to %s" % (name, str(packet.connection)))
            packet.connection.functions.add(name)
            self.functions.add(name)


class Server(object):
    def __init__(self):
        self.gear_server_pid = None
        self.gear_pipe_write = None

    def exit_handler(self, sig):
        signal.signal(signal.SIGUSR1, sig)
        self.stop_gear_server()

    def term_handler(self):
        self.stop_gear_server()
        os._exit(0)

    def start_gear_server(self):
        pipe_read, pipe_write = os.pipe()
        child_pid = os.fork()
        if child_pid == 0:
            os.close(pipe_write)
            GearServer(4730,
                       host="0.0.0.0",
                       statsd_host=None,
                       statsd_port=8125,
                       statsd_prefix='zuul.geard',
                       keepalive=True,
                       tcp_keepidle=10,
                       tcp_keepintvl=60,
                       tcp_keepcnt=9)
            # Keep running until the parent dies:
            pipe_read = os.fdopen(pipe_read)
            pipe_read.read()
            os._exit(0)
        else:
            os.close(pipe_read)
            self.gear_server_pid = child_pid
            self.gear_pipe_write = pipe_write

    def stop_gear_server(self):
        if self.gear_server_pid:
            os.kill(self.gear_server_pid, signal.SIGKILL)

    def main(self):
        self.start_gear_server()
        signal.signal(signal.SIGUSR1, self.exit_handler)
        signal.signal(signal.SIGTERM, self.term_handler)
        while True:
            try:
                signal.pause()
            except KeyboardInterrupt:
                print("Ctrl + C: asking scheduler to exit nicely...\n")
                self.exit_handler(signal.SIGINT)


def main():
    server = Server()
    pid_fn = '/var/run/zuul/zuul.pid'
    pid_file_module.TimeoutPIDLockFile(pid_fn, 10)
    server.main()


if __name__ == "__main__":
    main()
