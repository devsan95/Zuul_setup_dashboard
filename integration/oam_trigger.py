#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

import traceback
import sys
import argparse
import requests
import time
import json


def _parse_args():
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('jenkins_url', type=str,
                        help='')
    parser.add_argument('job_name', type=str,
                        help='')
    parser.add_argument('token', type=str,
                        help='')
    parser.add_argument('change_ids', type=str,
                        help='')
    parser.add_argument('retry_times', type=int, default=3,
                        help='')

    parser.add_argument('stream', type=str, default='',
                        help='')
    args = parser.parse_args()
    return vars(args)


def print_flush(strs):
    print(strs)
    sys.stdout.flush()


def form_url(change_ids, stream):
    change_ids_url = change_ids.replace(',', '-')
    change_id_slices = change_ids_url.split(' ')
    change_id_slices = sorted(change_id_slices)
    change_ids_url = '_'.join(change_id_slices)
    if stream:
        change_ids_url = '{}_{}'.format(change_ids_url, stream)
    s3_url = 'https://s3-china-1.eecloud.nsn-net.net/' \
             '5g-cb/integration/{}/pkg_info'
    url = s3_url.format(change_ids_url)
    return url


def get_qcow2_from_content(content):
    lines = content.split('\n')
    for line in lines:
        if 'es' in line and 'Virtualized' in line and '.qcow2' in line:
            return line
    raise Exception('No proper line for qcow2')


def get_last_job_status(jenkins_url, job_name, qcow2_url, min_no=None):
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
                    for param in action['parameters']:
                        if param['name'] == 'QCOW_URL' and\
                                param['value'] == qcow2_url:
                            return build_no, build_obj['result']
    except Exception as ex:
        print_flush(str(ex))
    return None, None


def trigger_job(jenkins_url, job_name, qcow2_url, token):
    url = '{}/job/{}/buildWithParameters'.format(jenkins_url, job_name)
    data = {'token': token,
            'QCOW_URL': qcow2_url}
    res = requests.post(url, data=data)
    return res.ok


def _main(change_ids, retry_times, jenkins_url, job_name, token, stream):
    content = None
    qcow2_url = None
    min_no = None

    for i in range(0, retry_times):
        print_flush('Execute No {}'.format(i + 1))
        try:
            if not qcow2_url:
                if not content:
                    url = form_url(change_ids, stream)
                    print(url)
                    request = requests.get(url)
                    if not request.ok:
                        raise Exception('Get s3 file failed!')
                    content = request.content

                if not content:
                    raise Exception('s3 content is empty!')

                qcow2_url = get_qcow2_from_content(content)

            if not qcow2_url:
                raise Exception('no qcow2 url!')

            last_no, last_result = \
                get_last_job_status(jenkins_url, job_name, qcow2_url)
            if last_result == 'SUCCESS':
                print_flush('Image has been tested and succeed.')
                sys.exit(0)

            if last_no:
                min_no = last_no

            if not trigger_job(jenkins_url, job_name, qcow2_url, token):
                raise Exception('trggier job failed')

            while True:
                build_no, result = \
                    get_last_job_status(jenkins_url, job_name,
                                        qcow2_url, min_no)
                print_flush(
                    'job is {} and status is {}'.format(build_no, result))
                if result is None:
                    print_flush('Waiting for job to complete...')
                    time.sleep(60)
                    continue
                if result == 'FAILURE':
                    print_flush('Test failed, retry')
                    print_flush('{}/job/{}/{}/'.format(
                        jenkins_url, job_name, build_no))
                    min_no = build_no
                    break
                elif result == 'SUCCESS':
                    print_flush('Test succeed')
                    print_flush('{}/job/{}/{}/'.format(
                        jenkins_url, job_name, build_no))
                    sys.exit(0)
                else:
                    print_flush('Test unknown, retry')
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

        _main(**param)
    except Exception as e:
        print_flush("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
