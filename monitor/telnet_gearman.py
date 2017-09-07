import sys
import time
import traceback
import telnetlib


class TelnetClient(object):

    def __init__(self, host, port):
        self.client = telnetlib.Telnet(host, port)



    def run_cmd(self, cmd, end_str, start_str = None):
        if start_str:
            try:
                self.client.read_until(start_str + "\n", 2)
            except:
                traceback.print_exc()
        print "run cmd %s" % cmd
        self.client.write(cmd + "\n")
        ret = self.client.read_until(end_str + "\n")
        return ret

tobj = TelnetClient('zuule1.dynamic.nsn-net.net', '4730')
ret = tobj.run_cmd('workers', '.')
ret2 = tobj.run_cmd('status', '.')
print ret
print ret2
