from update_zuul_merger_auto import collect_mergers
import logging
import fire
import os

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')


def create_shell_script():
    with open('updateMergerCode.sh', 'w') as rsh:
        rsh.write('''#!/bin/bash
cd merger/
git reset --hard HEAD
git clean -fdx
git fetch --tags
latest_tag=$(git describe --tags `git rev-list --tags --max-count=1`)

git checkout $latest_tag
pip3 uninstall zuul -y
pip3 install .

status=$(supervisorctl status zuul-merger | awk '{print $2}')
if [[ $status = "RUNNING" ]]
then
   supervisorctl restart zuul-merger
fi
''')


def run(ip):
    for merger in collect_mergers():
        print(merger)
        print(os.popen('docker ps -a --filter "name=^/%s$" --format "{{.Status}}"' % merger).read().split(' ')[0])
        if os.popen('docker ps -a --filter "name=^/%s$" --format "{{.Status}}"' % merger).read().split(' ')[0] == "Up":
            logging.info("Upgrading {}'s code on instance {}".format(merger, ip))
            os.system("docker cp updateMergerCode.sh {}:/root".format(merger))
            os.system("sudo docker exec -i {} bash -c 'sh updateMergerCode.sh'".format(merger))
            logging.info("Upgrade {} done on instance {}!".format(merger, ip))
        else:
            logging.warning("{} is not running on instance {}, thus cannot be upgraded!".format(merger, ip))


if __name__ == '__main__':
    create_shell_script()
    fire.Fire(run)
