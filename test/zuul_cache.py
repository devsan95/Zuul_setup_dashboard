#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import os
import sys
import threading

import fire
import monotonic
import requests
from twisted.internet import reactor
from twisted.internet.threads import deferToThread
from twisted.python import log
from twisted.python import threadable
from twisted.python.logfile import DailyLogFile
from twisted.web.resource import Resource, EncodingResourceWrapper
from twisted.web.server import NOT_DONE_YET
from twisted.web.server import Site, GzipEncoderFactory

zuul_time = monotonic.monotonic()
zuul_content = None
zuul_lock = threading.Lock()

status_url = ''


class NotFound(Resource):
    def getChild(self, name, request):
        return self

    def render_GET(self, request):
        return '404 Not Find'


def render_data(request, source):
    if not request.finished and not request._disconnected:
        request.setHeader('Content-Length', len(str(source)))
        request.setHeader('Content-Type', 'application/json')
        request.setHeader('Content-Encoding', 'gzip')
        request.setHeader('Access-Control-Allow-Origin', '*')
        # cache(request)
        request.write(str(source))
        request.finish()
    else:
        request.notifyFinish()


class ZuulHandler(Resource):
    def getChild(self, path, request):
        try:
            if path == "status.json":
                return EncodingResourceWrapper(ZuulStatusHandler(), [GzipEncoderFactory()])
            else:
                return NotFound()
        except Exception as e:
            log.err(u'invalid url，[%s]' % e)


class ZuulStatusHandler(Resource):
    def fetch_status(self):
        global zuul_time
        global zuul_content
        try:
            print('get zuul status')
            res = requests.get(status_url)
            print('done get zuul status')
            with zuul_lock:
                zuul_time = monotonic.monotonic()
                zuul_content = res.content
        except Exception as e:
            print(e)

    def get_status(self, request):
        global zuul_time
        global zuul_content
        new_time = monotonic.monotonic()
        need_fetch = False
        delta_time = new_time - zuul_time
        print(delta_time)
        if delta_time > 5.0 or not zuul_content:
            need_fetch = True
        if need_fetch and not zuul_lock.locked():
            self.fetch_status()

        content = ''
        if zuul_content:
            content = zuul_content

        return content

    def render_GET(self, request):
        d = deferToThread(self.get_status, request)
        d.addBoth(lambda x: render_data(request, x))
        return NOT_DONE_YET


class ServerHandle(Resource):
    def getChild(self, path, request):
        try:
            if path == "zuul":
                return ZuulHandler()
            else:
                return NotFound()
        except Exception as e:
            log.err(u'invalid url，[%s]' % e)


def main(port=8888, timeout=60, url='http://zuule1.dynamic.nsn-net.net/status.json', log_path='/root/server_log'):
    global status_url
    # build dir for log
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    # init the thread
    threadable.init(1)

    # start logging
    log.startLogging(sys.stdout)
    log.startLogging(DailyLogFile('zuul-proxy.log', log_path))

    reactor.suggestThreadPoolSize(20000)

    status_url = url
    root = ServerHandle()
    factory = Site(root, timeout=timeout)

    reactor.listenTCP(port, factory)
    reactor.run()


if __name__ == '__main__':
    fire.Fire(main)
