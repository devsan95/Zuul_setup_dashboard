import traceback
import telnetlib


class TelnetClient(object):

    def __init__(self, host, port):
        self.client = telnetlib.Telnet(host, port)

    def run_cmd(self, cmd, end_str, start_str=None):
        if start_str:
            try:
                self.client.read_until(start_str + "\n", 2)
            except Exception:
                traceback.print_exc()
        print "run cmd %s" % cmd
        self.client.write(cmd + "\n")
        ret = self.client.read_until(end_str + "\n")
        return ret
