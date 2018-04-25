#!/bin/bash

set -x
lessspace = 2097152

function moniter(){
diskspace=`df -t ext4 | awk 'NR==2{print $4}'`
if [ $diskspace -gt $lessspace ];then
	echo "$hostname disk space looks well for now."
else
	echo "[WARNING] SPACE ALARM!!!"
	df -lh
	exit 1
fi
}

moniter
