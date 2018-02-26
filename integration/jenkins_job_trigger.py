#! /usr/bin/env python2.7
# -*- coding:utf8 -*-

import traceback
import sys
import argparse
import requests
import time
import json


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
        help="data options , we can put token and job parameters here\n"
        "e.g.: token=*** param1=*** param2=***",
        dest="data")

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
            key, value = line.split('=')[:2]
            data_dict[key] = value
        pdict['data'] = data_dict
    return pdict


def print_flush(strs):
    print(strs)
    sys.stdout.flush()


def get_last_job_status(jenkins_url, job_name, data, min_no=None):
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
            for action in build_obj['actions']:
                if 'parameters' in action:
                    data_nomatch = data.keys()
                    for param in action['parameters']:
                        if param['name'] in data.keys() and \
                                param['value'] == data[param['name']]:
                            data_nomatch.remove(param['name'])
                    if not data_nomatch:
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


def _main(params):
    retry_times = params['retry_times']
    jenkins_url = params['jenkins_url']
    job_name = params['job_name']
    data = params['data']
    min_no = 0
    for i in range(0, retry_times):
        print_flush('Execute No {}'.format(i + 1))
        try:
            last_no, last_result = \
                get_last_job_status(jenkins_url, job_name, data)
            if last_result == 'SUCCESS':
                print_flush('Image has been tested and succeed.')
                sys.exit(0)

            if last_no:
                min_no = last_no

            if not trigger_job(jenkins_url, job_name, data):
                raise Exception('trggier job failed')

            while True:
                build_no, result = \
                    get_last_job_status(jenkins_url, job_name, data, min_no)
                print_flush(
                    'job is {} and status is {}'.format(build_no, result))
                if result is None:
                    print_flush('Waiting for job to complete...')
                    time.sleep(60)
                    continue
                if result == 'FAILURE':
                    print_flush('Job Build failed, retry')
                    print_flush('{}/job/{}/{}/'.format(
                        jenkins_url, job_name, build_no))
                    min_no = build_no
                    break
                elif result == 'SUCCESS':
                    print_flush('Job Build succeed')
                    print_flush('{}/job/{}/{}/'.format(
                        jenkins_url, job_name, build_no))
                    sys.exit(0)
                else:
                    print_flush('Job Build unknown, retry')
                    print_flush('{}/job/{}/{}/'.format(
                        jenkins_url, job_name, build_no))
                    min_no = build_no
                    break

        except Exception as e:
            print_flush('Exception met: {}'.format(str(e)))

    sys.exit(2)


if __name__ == '__main__':
    try:
        param = _parse_args()
        _main(param)
    except Exception as e:
        print_flush("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
