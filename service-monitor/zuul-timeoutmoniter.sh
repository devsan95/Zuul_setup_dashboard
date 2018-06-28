#! /bin/bash
#for job http://jenkins-prod.zuulqa.dynamic.nsn-net.net/view/zuul_tools/job/TimeOut-moniter/

set -x
cd /var/fpwork/zuul_prod/log

function timeout-moniter(){
timeoutNO=`grep "socket.timeout" server-debug.log | wc -l`
if [ $timeoutNO -le 30 ];then
	echo "TimeOut number is $timeoutNO for now, hope not growing."
else
	echo "[WARNING!] TimeOut issue happening over the cordon!!!"
	echo "$timeoutNO"
	exit 1
fi
}

timeout-moniter
