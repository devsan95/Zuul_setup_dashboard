#!/usr/bin/env bash
export GIT_SSL_NO_VERIFY=true
SCRIPT_DIR="`dirname \"${BASH_SOURCE[0]}\"`"
SCRIPT_DIR="`( cd \"$SCRIPT_DIR/..\" && pwd )`"  # absolutized and normalized
if [ -z "$$SCRIPT_DIR" ] ; then
  # error; for some reason, the path is not accessible
  # to the script (e.g. permissions re-evaled after suid)
  echo "Can't find CIHOME Path"
  exit 1  # fail
fi
script_pwd=update_zuul_layout
work_path=/tmp/zuul_tmp/${script_pwd}/
mkdir -p /tmp/zuul_tmp/${script_pwd}/
rm -rf /tmp/zuul_tmp/${script_pwd}/*
OLD_PATH="`pwd`"
cd ${work_path}
git clone ssh://ca_zuul_qa@gerrit.ext.net.nokia.com:29418//MN/SCMTA/zuul/layout-lte layout
git clone ssh://ca_zuul_qa@gerrit.ext.net.nokia.com:29418//MN/SCMTA/zuul/conf

. ${SCRIPT_DIR}/pyenv.sh
python ${SCRIPT_DIR}/layout/layout_handler_new.py -i "${work_path}/layout/layout.yaml" \
 -z "${work_path}/conf/zuul_conf/zuulte.conf" merge -o "/etc/zuul/layout.yaml"
kill -SIGHUP `supervisorctl pid zuul-server`