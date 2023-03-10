#!/bin/bash -x

#sleep 15m
#echo "compare th time stamp of MN/SCMTA/zuul/layout in git and zuul status file"

#udo docker exec zuul-server bash

x=`curl http://zuule1.dynamic.nsn-net.net/status.json | jq .last_reconfigured`
z=`expr $x / 1000`

cd /root/script/layout

git pull --rebase
git fetch origin refs/notes/review:refs/notes/review

#y=`git log -n 1 --pretty=format:"%cd" --date=raw | cut -d" " -f1`

w=`git log  --show-notes=review  | grep -m 1  "Submitted-at" | cut -d":" -f 2,3,4`
y=`date "+%s" -d "$w"`

git log -n 3 > /root/script/gitlog.txt

diff_time=`expr $z - $y`


#docker cp 26a8715e6824:/root/script/gitlog.txt /var/fpwork/zuul_jenkins/jenkins-qa/workspace/Zuul_layout_validate/ws/

tdiff=`expr $diff_time / 60`

echo -e  "\n Difference in  timestamp $tdiff  minutes"

if test $tdiff -ge "720" ; then
   echo -e "\n There is server upgrade in weekend, please check "
   exit 0
fi

if test $tdiff -le "20" ; then

  echo "No issue in the synch"
   exit 0
else
   echo -e  "\n Check there is issue with synch, Sent the latest 3 commits of layout repo to research. \n ( This diff may also happens becuase of zuul down time upgrdes, As thers is a last_recongigured time change in zuul dashboard )\n "
    exit 1
fi
