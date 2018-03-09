import sys
import traceback

import fire

import jenkins_job_trigger
from api import wft_api


def get_last_baseline(baseline_prefix, access_key):
    auth = wft_api.WftAuth(access_key)
    build_query = wft_api.WftBuildQuery(auth)
    build_query.set_sorting('baseline')
    build_query.add_filter('baseline', 'start', baseline_prefix)
    build_query.set_result_number(1)
    result = build_query.query()
    if result['count'] < 1:
        return None
    return result['items'][0]['baseline']


def _main(baseline_prefix, access_key, version_file=None,
          structure_yaml='5G18A_PS_integration.yaml', streams='4.11',
          using_backup=True, retry_time=3,
          jenkins_url='http://5g-cimaster-4.eecloud.dynamic.nsn-net.net:8080',
          jenkins_job='F_SCMTA_SERVICES/ZUUL_PROXY/create_integration_change',
          token=None):
    baseline = get_last_baseline(baseline_prefix, access_key)
    print('The latest baseline is [{}]'.format(baseline))
    # compare with older version
    if version_file:
        try:
            with open(version_file) as f:
                comparing_version = f.read()
                print('Older version is [{}]'.format(comparing_version))
                if baseline <= comparing_version:
                    raise Exception('The baseline is not latest, abort')
        except IOError as ie:
            print('Open file {} failed, for {}'.format(version_file, str(ie)))
    # form parameter
    build = wft_api.WftBuild.get_build(baseline)
    urls = build.find_items('./repository_url')
    if not urls:
        raise Exception('Can not find repository_url in build info')
    url = urls[0].text
    tags = build.find_items('./repository_branch')
    if not tags:
        raise Exception('Can not find repository_branch in build info')
    tag = tags[0].text
    ecl_string = '{}/{}/ECL;HEAD'.format(url, tag)
    print('ECL is [{}]'.format(ecl_string))
    baselines = build.find_items('./content/baseline')
    lfs_string = None
    if not baselines:
        raise Exception('Can not find conetnt/baseline in build info')
    for ele in baselines:
        if 'sc' in ele.attrib and ele.attrib['sc'] == 'PS_LFS_REL':
            lfs_string = ele.text
    if not lfs_string:
        raise Exception('Can not find LFS version')
    env_change = 'ENV_PSREL_PS_REL_ASIK={}\n' \
                 'ENV_PSREL_PS_REL_ECL_ASIK={}\n' \
                 'ENV_PSREL_PS_LFS_REL_ASIK={}'.format(baseline,
                                                       ecl_string, lfs_string)
    print('env_change is:')
    print(env_change)
    jenkins_param = {
        'structure_yaml': structure_yaml,
        'env_change': env_change,
        'streams': streams,
        'using_backup': '1' if using_backup else '0',
    }
    if token:
        jenkins_param['token'] = token

    print('jenkins_url')
    print(jenkins_url)
    print('retry_time')
    print(retry_time)
    print('jenkins_job')
    print(jenkins_job)
    print('jenkins_param')
    print(jenkins_param)

    print('begin to launch job')
    jenkins_job_trigger.run({
        'retry_times': retry_time,
        'jenkins_url': jenkins_url,
        'job_name': jenkins_job,
        'data': jenkins_param,
    })
    if version_file:
        print('Writing baseline to {}'.format(version_file))
        with open(version_file, 'w') as f:
            f.write(baseline)
    print('Version: {}'.format(baseline))


if __name__ == '__main__':
    try:
        fire.Fire(_main)
    except Exception as e:
        print('Exception: {}'.format(str(e)))
        traceback.print_exc()
        sys.exit(2)
