import fire
import configparser
import os
from api import aes
from api import gerrit_rest


def main(config_path):
    parser = configparser.ConfigParser()
    parser.read(os.path.expanduser(config_path))
    user = parser.get('gerrit', 'user_rest')
    pwd = parser.get('gerrit', 'pwd_rest')
    url = parser.get('gerrit', 'url_rest')
    auth = parser.get('gerrit', 'auth_rest')

    pwd = aes.AESCipher('hz5gscm').decrypt(pwd)

    rest = gerrit_rest.GerritRestClient(url=url, user=user, pwd=pwd, auth=auth)

    print(rest.list_account_emails())


if __name__ == '__main__':
    fire.Fire(main)
