
class ErrCheck(object):

    def __init__(self):
        self.err_msgs = []
        self.check_dict = {}
        self.err_num = 0
        self.pass_num = 0

    def add_check(self, title, fun, err_msg):
        check_elem = {}
        check_elem['fun'] = fun
        check_elem['err_msg'] = err_msg
        check_elem['result'] = None
        self.check_dict[title] = check_elem

    def check(self):
        for key, obj in self.check_dict.items():
            try:
                obj['result'] = obj['fun']()
            except:
                print "check function for %s get exception" % key
                obj['result'] = False
            if obj['result']:
                self.pass_num = self.pass_num + 1
            else:
                print 'Check Failed: %s' % obj['err_msg']
                self.err_num = self.err_num + 1
                self.err_msgs.append(obj['err_msg'])
        return self.err_msgs, self.err_num, self.pass_num
