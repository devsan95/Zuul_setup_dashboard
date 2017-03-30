#!/usr/bin/env bash

# update known hosts
# echo '[gerrit.zuulqa.dynamic.nsn-net.net]:29418,[10.181.54.157]:29418 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAAgQCrU2RQq8bq4DT9Rixebtt/BksVCauQECaBQmtO83ffkWzbHA18pgqRd6/EpSI3wLilUWUQ5ET4k4oNicQDv3bBrOkG0ZADHZ9vE2WMG2y4IqQLNf72gF5IHpxrnapU+EmEEALbHtuDzHJusO6z6C/yyJFRiEDs4KNsEMfFckQLOQ==' >> ~/.ssh/known_hosts

# update git name
git config --global user.email '5g_hz.scm@nokia.com'
git config --global user.name 'admin'

# run validation
. /root/mn_scripts/pyenv.sh
python /root/mn_scripts/pipeline/validate_pipeline.py -p dummy-project-docker