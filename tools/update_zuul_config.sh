#!/usr/bin/env bash
export GIT_SSL_NO_VERIFY=true
script_pwd=update_zuul_config
work_path=/tmp/zuul_tmp/${script_pwd}/
mkdir -p /tmp/zuul_tmp/${script_pwd}/
rm -rf /tmp/zuul_tmp/${script_pwd}/*
OLD_PATH="`pwd`"
cd ${work_path}
git clone http://gerrit.app.alcatel-lucent.com/gerrit/MN/SCMTA/zuul/conf
cp -rf ${work_path}/conf/http_conf/* /etc/httpd/
cp -rf ${work_path}/conf/zuul_conf/* /etc/zuul/
supervisorctl restart zuul-server
supervisorctl restart zuul-merger
supervisorctl restart zuul-launcher