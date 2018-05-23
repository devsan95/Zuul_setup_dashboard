#! /bin/bash
set -x
cd /var/fpwork/zuul_prod/log

function loop-duration(){

grep "Run handler sleeping" server-debug.log | tail -2 | awk '{print $2}' > loop.txt

t1=$(cat loop.txt | awk 'NR==1')
t2=$(cat loop.txt | awk 'NR==2')
duration=$(($(date +%s -d $t2) - $(date +%s -d $t1)))
if [ $duration -le 300 ];then
    echo "zuul loop time is $duration sec now, faster faster faster!"
else
    echo "[WARNING!]zuul loop time is $duration sec now, TOO SLOW!!!"
	exit1
fi
}

loop-duration
