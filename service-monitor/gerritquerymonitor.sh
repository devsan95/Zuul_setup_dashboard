#!/bin/bash
#run agaist gerrit timeout issue for monit, should run on the zuule1 server.

set -x
set i=1
for((i=1;i>0;))
do
    let "i=i+1"
    (time ssh -p 29418 scmtaci@gerrit.ext.net.nokia.com gerrit query --format json --all-approvals --comments --commit-message --current-patch-set --dependencies --files --patch-sets --submit-records 298703) 2>> query.log
    sleep 2
done
