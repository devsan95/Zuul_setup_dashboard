#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-


def get_env_repo_info(rest, change_no):
    env_repo = 'MN/5G/COMMON/integration'
    env_path = 'env/env-config.d/ENV'
    config_yaml_file = 'config.yaml'

    try:
        rest.get_file_content(env_path, change_no)
    except Exception as e:
        print('env file not in integration repo, reason:')
        print(str(e))
        try:
            rest.get_file_content(config_yaml_file, change_no)
            env_path = ''
        except Exception as e:
            print('config yaml file not in integration repo, reason:')
            print(str(e))
            env_path = 'env-config.d/ENV'
            env_repo = 'MN/5G/COMMON/env'

    return (env_repo, env_path)
