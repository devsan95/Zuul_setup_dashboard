import subprocess
from api import gerrit_rest
import fire
import os
from api import log_api
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def run_command(command_line, log):
    ret = subprocess.Popen(command_line,
                           shell=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ret_code = ret.wait()
    log.info('return: %s', ret_code)
    ret_std = ret.stdout.read()
    ret_err = ret.stderr.read()
    if ret_std:
        log.info('stdout:\n%s', ret_std)
    if ret_err:
        log.error('stderr:\n%s', ret_err)
    return ret_code


def main(repo_path, gerrit_path, flake8_conf, pylint_conf):
    log = log_api.get_console_logger('Linting')
    rest = gerrit_rest.init_from_yaml(gerrit_path)
    zuul_changes = os.environ.get('ZUUL_CHANGE_IDS').split(' ')
    file_set = set()
    for change in zuul_changes:
        rest_id, rev_id = change.split(',')
        ret_list = rest.get_file_list(rest_id, rev_id)
        for ret in ret_list:
            file_set.add(ret)
    total_ret = 0
    for file_name in file_set:
        if file_name == '/COMMIT_MSG':
            continue
        if not file_name.endswith('.py'):
            continue
        log.info('Linting %s', file_name)
        log.info('----flake8----')
        total_ret += run_command("flake8 --config={} {}".format(flake8_conf, os.path.join(repo_path, file_name)), log)
        log.info('----pylint----')
        total_ret += run_command("pylint --rcfile={} {}".format(pylint_conf, os.path.join(repo_path, file_name)), log)
        log.info('==============================')


if __name__ == '__main__':
    fire.Fire(main)
