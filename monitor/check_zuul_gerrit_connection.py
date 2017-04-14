#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

from sh import ssh
import api.config
import sys
import traceback


def _main():
    conf = api.config.ConfigTool()
    conf.load('/etc/zuul/zuul.conf', absolute=True)
    server = conf.get('gerrit', 'server')
    port = conf.get('gerrit', 'port')
    user = conf.get('gerrit', 'user')
    ssh_key = conf.get('gerrit', 'sshkey')
    print('Testing connect...')
    print('Server: {}'.format(server))
    print('Port: {}'.format(port))
    print('User: {}'.format(user))
    print('SSH key path: {}'.format(ssh_key))

    try:
        result = ssh('-p', port, '-i', ssh_key, user + '@' + server, 'gerrit',
                     'ls-groups')
        print('Test completes. Result is: \n{}'.format(result))
    except Exception as ex:
        print('an exception occurred, test failed.')
        raise ex


if __name__ == '__main__':
    try:
        _main()
        sys.exit(0)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
