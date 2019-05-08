#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import traceback
import sys
import argparse
import requests
import time
import json
import copy


def _parse_args():
    parser = argparse.ArgumentParser(
        description="this is the help usage of %(prog)s",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        "--jenkins_url",
        required=True,
        default='',
        help="e.g.: http://fiveci.emea.nsn-net.net:8080",
        dest="jenkins_url")

    parser.add_argument(
        "--job_name",
        required=True,
        default='',
        help="jenkins job name",
        dest="job_name")

    parser.add_argument(
        "--data",
        nargs='*',
        help="data options , now support "
        "token/base_pkg/knife_json/integration_tag",
        dest="data")

    parser.add_argument(
        "--key_params",
        required=False,
        default='',
        help="key params to check job build, like INTEGRATION_TAG,ZUUL_BRANCH,PRODUCT_NAME",
        dest="key_params")

    parser.add_argument(
        '--retry_times',
        type=int,
        default=1,
        help='',
        dest="retry_times")

    args = parser.parse_args()
    pdict = vars(args)
    if pdict['data']:
        data_dict = {}
        for line in pdict['data']:
            key, value = line.split('=', 1)[:2]
            data_dict[key] = value
        pdict['data'] = data_dict
    return pdict


def print_flush(strs):
    print(strs)
    sys.stdout.flush()


def get_last_build_no(jenkins_url, job_name):
    try:
        url = '{}/job/{}/api/json'.format(jenkins_url, job_name)
        # get all build nos
        res = requests.get(url)
        if not res.ok:
            raise Exception('Fetch job builds failed')
        res_obj = json.loads(res.content)
        # find corresponding build no
        if 'lastBuild' in res_obj and 'number' in res_obj['lastBuild']:
            return res_obj['lastBuild']['number']
    except Exception:
        return 0
    return 0


def get_last_job_status(jenkins_url, job_name, data, min_no=None, key_params=[]):
    try:
        url = '{}/job/{}/api/json'.format(jenkins_url, job_name)
        # get all build nos
        res = requests.get(url)
        if not res.ok:
            raise Exception('Fetch job builds failed')
        res_obj = json.loads(res.content)
        # find corresponding build no
        for build in res_obj['builds']:
            build_no = build['number']
            if min_no and int(build_no) <= int(min_no):
                continue
            url_build = '{}/job/{}/{}/api/json'.format(jenkins_url, job_name,
                                                       build_no)
            res_build = requests.get(url_build)
            if not res_build.ok:
                raise Exception('Fetch job build failed')
            build_obj = json.loads(res_build.content)
            # print 'build obj: {}'.format(build_obj)
            for action in build_obj['actions']:
                if 'parameters' in action:
                    match_params = data.keys()
                    if ''.join(key_params):
                        match_params = key_params
                        print "key_params has value, will match the key_param"
                    data_nomatch = copy.copy(match_params)
                    if 'token' in data_nomatch:
                        data_nomatch.remove('token')
                    print 'find params: {}'.format(data_nomatch)
                    # print 'data: {}'.format(data)
                    for param in action['parameters']:
                        if param['name'] in match_params:
                            if param['value'] == data[param['name']]:
                                print 'param: {} matched'.format(param['name'])
                                data_nomatch.remove(param['name'])
                    print 'data_nomatch: {}'.format(data_nomatch)
                    if not data_nomatch:
                        if 'building' in build_obj and build_obj['building']:
                            return build_no, None
                        return build_no, build_obj['result']
    except Exception as ex:
        print_flush(str(ex))
    return None, None


def trigger_job(jenkins_url, job_name, data):
    url = '{}/job/{}/buildWithParameters'.format(jenkins_url, job_name)
    print 'url:{} job_name:{} data:{}'.format(jenkins_url,
                                              job_name,
                                              data)
    res = requests.post(url, data=data)
    print 'res:{}'.format(res.text)
    return res.ok


def jenkins_job_trigger(params):
    _main(params)


def _main(params):
    print "Parameters is {}".format(params)
    retry_times = params['retry_times']
    jenkins_url = params['jenkins_url']
    job_name = params['job_name']
    key_params = params['key_params'].split(',')
    data = params['data']
    min_no = 0
    for i in range(0, retry_times):
        print_flush('Execute No {}'.format(i + 1))
        try:
            min_no = get_last_build_no(jenkins_url, job_name)

            if not trigger_job(jenkins_url, job_name, data):
                raise Exception('trggier job failed')

            while True:
                build_no, result = \
                    get_last_job_status(jenkins_url,
                                        job_name,
                                        data,
                                        min_no,
                                        key_params=key_params)
                print('key params is {}'.format(key_params))
                print_flush(
                    'job is {} and status is {}'.format(build_no, result))
                if result is None:
                    print_flush('Waiting for job to complete...')
                    print_flush('You can check the build link here:')
                    print_flush('{}/job/{}/{}/'.format(
                        jenkins_url, job_name, build_no))
                    time.sleep(60)
                    continue
                if result == 'FAILURE':
                    print_flush('Job Build failed, please retry:')
                    print_flush('{}/job/{}/{}/'.format(
                        jenkins_url, job_name, build_no))
                    min_no = build_no
                    break
                elif result == 'SUCCESS':
                    print_flush('Job Build succeed, the build link is:')
                    print_flush('{}/job/{}/{}/'.format(
                        jenkins_url, job_name, build_no))
                    sys.exit(0)
                else:
                    print_flush('Job Build unknown, please retry:')
                    print_flush('{}/job/{}/{}/'.format(
                        jenkins_url, job_name, build_no))
                    min_no = build_no
                    break

        except Exception as e:
            print_flush('Exception met: {}'.format(str(e)))

    sys.exit(2)


if __name__ == '__main__':
    try:
        parameters = _parse_args()
        _main(parameters)
    except Exception as e:
        print_flush("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
