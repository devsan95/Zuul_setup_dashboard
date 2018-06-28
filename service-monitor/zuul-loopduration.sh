#! /bin/bash
#for job http://jenkins-prod.zuulqa.dynamic.nsn-net.net/job/zuul-loop-duration/

set -x
cd /var/fpwork/zuul_prod/log
function loop-duration(){
grep "Run handler sleeping" server-debug.log|tail -2 | awk '{print $2}' > loop.txt
t1=$(cat loop.txt | awk 'NR==1')
t2=$(cat loop.txt | awk 'NR==2')
duration=$(($(date +%s -d $t2) - $(date +%s -d $t1)))
#echo "$duration sec now!" 
if [ $duration -le 300 ];then
    echo "zuul loop time is $duration sec now, faster faster faster!"
else
    echo "[WARNING!]zuul loop time is $duration sec now, TOO SLOW!!!" > loopduration.txt
	#export long duration log-lines out of the log to one txt
    sed -n "/${t1}/,/${t2}/p" server-debug.log > /var/fpwork/zuul_jenkins/jenkins-qa/workspace/zuul-loop-duration/long-loop-$BUILD_NUMBER.txt
	echo "please check long duration logs in the job workspace"
    exit 1
fi
}

loop-duration
