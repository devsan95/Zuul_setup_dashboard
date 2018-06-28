#!/bin/bash
#for job http://jenkins-prod.zuulqa.dynamic.nsn-net.net/view/zuul_tools/job/gerrit-error-moniter/
#two gerrit error moniter and deal: bad pack header, Unable to reset repo

set -x

function localref-prune(){
cd /var/fpwork/zuul_prod/log
#collect all problem repos to list
grep -B 1 "zuul.Merger: Unable to reset repo" merger-debug.log | awk '{print $8}' > localreftemp.txt
sort -k2n localreftemp.txt | awk '{if ($0!=line) print;line=$0}' | awk '/ephemeral/' > localreftemp1.list
cat localreftemp1.list
#do git command to every repo
while read line
do
    pwd
    localrepopath=`echo ${line:16}`
    cd /var/fpwork/zuul_prod/$localrepopath
    git remote prune origin
done < localreftemp1.list
rm -rf localreftemp.txt
}

function bad-pack-header-moniter(){
cd /var/fpwork/zuul_prod/log
badheader=`grep -B 30 "fatal: protocol error: bad pack header" merger-debug.log | tail -30`
echo $badheader > badheader.txt
if [ -n "$badheader" ];then
    echo "[WARNING!] Need gc now!!!Please check detail log"
    echo "$badheader"
    exit 1
fi
}

localref-prune
bad-pack-header-moniter
