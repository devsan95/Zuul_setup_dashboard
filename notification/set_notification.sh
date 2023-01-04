#!/bin/bash -x
title=$1
content=$2
alert_type=$3
icon=$4
label=$5
label_type=$6
set +e
rm -rf  zuul_notification
git clone ssh://ca_zuul_qa@gerrit.ext.net.nokia.com:29418/MN/SCMTA/zuul/zuul_notification
result=$?
cd ${WORKSPACE}
if [ -d "script" ];then
        cd script
    git reset --hard
    git pull --rebase
else
        git clone "ssh://ca_zuul_qa@gerrit.ext.net.nokia.com:29418/MN/SCMTA/zuul/mn_scripts" script
fi

cd ${WORKSPACE}
if [ -d "info" ];then
        cd info
    git reset --hard
    git pull --rebase
else
    git clone "ssh://ca_zuul_qa@gerrit.ext.net.nokia.com:29418/MN/SCMTA/zuul/inte_info" info
fi
cd ${WORKSPACE}/script
. ${WORKSPACE}/script/pyenv.sh
if [ $result == 0 ]; then
        echo "gerrit is ok"
    python html/generate_notification.py --title "${title}" --content "${content}" --author "${BUILD_USER}" --alert-type "${alert_type}" --icon "${icon}" --label "${label}" --label-type "${label_type}" --gerrit-path "${WORKSPACE}/info/ext_gerrit.yaml" --zuul-server-name "zuul-server" --project MN/SCMTA/zuul/zuul_notification --branch master --file-path index.html --history-path history.html --list-path list.yaml --archiving-path achive/archving --history-count 5 --archiving-threshold 100  
else
    echo "gerrit is down"
    python html/generate_notification.py --title "${title}" --content "${content}" --author "${BUILD_USER}" --alert-type "${alert_type}" --icon "${icon}" --label "${label}" --label-type "${label_type}" --gerrit-available False --zuul-server-name "zuul-server" --gerrit-path "${WORKSPACE}/info/ext_gerrit.yaml" --project MN/SCMTA/zuul/zuul_notification --branch master --file-path index.html --history-path history.html --list-path list.yaml --archiving-path achive/archving --history-count 5 --archiving-threshold 100
fi
