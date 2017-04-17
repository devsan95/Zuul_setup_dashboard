#!/usr/bin/env bash
if [ $# -ne 1 ]; then
    (>&2 echo "Error: expect one argument of merger domain.")
    (>&2 echo "    (Got $@)")
    exit 1
fi

export GIT_SSL_NO_VERIFY=true
hostname=$1
script_pwd=update_merger_config
work_path=/tmp/zuul_tmp/${script_pwd}/
mkdir -p /tmp/zuul_tmp/${script_pwd}/
rm -rf /tmp/zuul_tmp/${script_pwd}/*
OLD_PATH="`pwd`"
cd ${work_path}
git clone http://gerrit.ext.net.nokia.com/gerrit/MN/SCMTA/zuul/conf
cp -rf ${work_path}/conf/http_conf/* /etc/httpd/
sed -i 's#domain.to.merger#$hostname#g' ${work_path}/conf/merger_conf/zuul/zuul.conf
cp -rf ${work_path}/conf/zuul_conf/* /etc/zuul/
cp -rf ${work_path}/conf/merger_conf/zuul/* /etc/zuul/
cp -rf ${work_path}/conf/merger_conf/superviosrd/* /etc/superviosrd/
supervisorctl reload
supervisorctl restart zuul-merger