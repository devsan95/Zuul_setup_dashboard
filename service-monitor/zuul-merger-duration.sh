#!/bin/bash
#for job http://jenkins-prod.zuulqa.dynamic.nsn-net.net/job/zuul-merger-duration/

set -x
cd /var/fpwork/zuul_prod/log

function zuul-merger-duration(){

grep "zuul.MergeServer: Got merge job" merger-debug.log | tail -2 | awk '{print $2}' > merger-duration.txt
got1=$(date +%s -d $(cat merger-duration.txt | awk 'NR==1'))
got2=$(date +%s -d $(cat merger-duration.txt | awk 'NR==2'))
#echo $got1 $got2
grep "zuul.Repo: CreateZuulRef" merger-debug.log | tail -1 | awk '{print $2}' >> merger-duration.txt
create1=$(date +%s -d $(cat merger-duration.txt | awk 'NR==3'))
#echo $create1
#cat merger-duration.txt

if [ $got1 -gt $create1 ];then
    echo "[WARNING!]merger seems meeting error now!!!" > mergerdur.txt
	exit 1
elif [ "$create1" -gt "$got1" ] && [ "$got2" -gt "$create1" ];then
    mer1=$(($create1-$got1))
    echo $mer1
    if [ $mer1 -le 20 ];then
	    echo "Merge duration is $mer1 sec now, seems OK then." > mergerdur.txt
	else
	    echo "[WARNING!]merge duration is $mer1 sec now, not good! not good!" > mergerdur.txt
		exit 1
	fi
elif [ $create1 -gt $got2 ];then
    mer2=$(($create1-$got2))
	if [ $mer2 -le 20 ];then
	    echo "Merge duration is $mer2 sec now, seems OK then." > mergerdur.txt
	else
	    echo "[WARNING!]merge duration is $mer2 sec now, not good! not good!" > mergerdur.txt
		exit 1
	fi
fi
}
zuul-merger-duration
