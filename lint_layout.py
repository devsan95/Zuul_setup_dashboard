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


def main(repo_path, file_path, flake8_conf, pylint_conf):
    log = log_api.get_console_logger('Linting')
    log.info('Start linting %s', repo_path)
    log.info('Using %s and %s', flake8_conf, pylint_conf)
    log.info('==============================')
    if not file_path.endswith('.py'):
        exit(1)
    total_ret = 0
    log.info('Linting [%s]', file_path)
    log.info('----flake8----')
    total_ret += run_command("flake8 --config={} {}".format(flake8_conf, os.path.join(repo_path, file_path)), log)
    log.info('----pylint----')
    total_ret += run_command("pylint --rcfile={} {}".format(pylint_conf, os.path.join(repo_path, file_path)), log)
    log.info('==============================')

    exit(total_ret)


if __name__ == '__main__':
    fire.Fire(main)
