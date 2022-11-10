#!/usr/bin/env bash
export GIT_SSL_NO_VERIFY=true
script_pwd=update_zuul_config
work_path=/tmp/zuul_tmp/${script_pwd}/
mkdir -p /tmp/zuul_tmp/${script_pwd}/
rm -rf /tmp/zuul_tmp/${script_pwd}/*
OLD_PATH="`pwd`"
cd ${work_path}
wget http://zuule1.dynamic.nsn-net.net/zuul_log/layout.yaml
git clone ssh://ca_zuul_qa@gerrit.ext.net.nokia.com:29418/MN/SCMTA/zuul/conf
cp -rf ${work_path}/conf/http_conf/* /etc/httpd/
cp -rf ${work_path}/conf/zuul_conf/* /etc/zuul/
cp -rf ${work_path}/conf/validate_code_conf/* /etc/zuul/
cp -rf layout.yaml /etc/zuul/

supervisorctl restart zuul-server
supervisorctl restart zuul-merger
supervisorctl restart zuul-launcher