#!/bin/bash
#
# auto count the merger duration in zuul, and give warning
set -x
#ZUULSERVERS='eslinb40.emea.nsn-net.net eslinb34.emea.nsn-net.net zuulmergeres42.dynamic.nsn-net.net'
ZUULSERVICES='zuul-server zuul-merger merger_eslinb34_1 merger_eslinb34_2 merger_es42_1 merger_es42_2'
server=`hostname`

##################################################################################
# funcation name:   zuulmergerduration
# description:      auto count the merger duration in zuul, and give warning
# parameter1:
# parameter2:
# usage example:    zuulmergerduration
# return:           richard.1.hu@nokia-sbell.com
# author:           richard.1.hu@nokia-sbell.com
##################################################################################
function zuulmergerduration(){
	grep "zuul.MergeServer: Got merge job" ${service}-merger-debug.log | tail -2 | awk '{print $2}' > ${service}-merger-duration.txt
	got1=$(date +%s -d $(cat ${service}-merger-duration.txt | awk 'NR==1'))
	got2=$(date +%s -d $(cat ${service}-merger-duration.txt | awk 'NR==2'))
	#echo $got1 $got2
	grep "zuul.Repo: CreateZuulRef" ${service}-merger-debug.log | tail -1 | awk '{print $2}' >> ${service}-merger-duration.txt
	create1=$(date +%s -d $(cat ${service}-merger-duration.txt | awk 'NR==3'))
	#echo $create1
	#cat merger-duration.txt
	
	if [[ ${got1} -gt ${create1} ]];then
	    echo "[WARNING!]merger data uncorrect in ${service} of ${server}, rerun may needed, please ignore!" >> ${server}-mergerdur.txt
	elif [[ "${create1}" -gt "${got1}" ]] && [[ "${got2}" -gt "${create1}" ]];then
	    mer1=$((${create1}-${got1}))
	    echo ${mer1}
	    if [[ ${mer1} -le 30 ]];then
	        echo "Merge duration is ${mer1} sec in ${service} of ${server} now, seems OK then."
	    else
	        echo "[WARNING!]merge duration is ${mer1} sec in ${service} of ${server} now, not good! not good!" >> ${server}-mergerdur.txt
	    fi
	elif [[ ${create1} -gt ${got2} ]];then
	    mer2=$((${create1}-${got2}))
	    if [[ ${mer2} -le 30 ]];then
	        echo "Merge duration is ${mer2} sec in ${service} of ${server} now, seems OK then."
	    else
	        echo "[WARNING!]merge duration is ${mer2} sec in ${service} of ${server} now, not good! not good!" >> ${server}-mergerdur.txt
	    fi
	fi
}
for service in ${ZUULSERVICES}
do
#    cd /tmp/
#    cd merger_duration_tmp/
    pwd
    sudo docker exec ${service} bash -c "cd /ephemeral/log/zuul;cp merger-debug.log merger-debug-tmp.log;chmod 777 merger-debug-tmp.log"
    sudo docker cp ${service}:/ephemeral/log/zuul/merger-debug-tmp.log ${service}-merger-debug.log
    if [[ -s "${service}-merger-debug.log" ]];then
        zuulmergerduration
#        scp -r ${server}-mergerdur.txt root@10.157.164.203:/root/workspace/ZUUL_MERGER_DURATION
        rm -f ${service}-merger-debug.log
    else
        rm -f ${service}-merger-debug.log
        echo "no container called ${service} in ${server}, skip to try next in ZUULSERVICES list."
    fi
done
scp -r ${server}-mergerdur.txt root@10.157.164.203:/root/workspace/ZUUL_MERGER_DURATION
rm -f ${server}-mergerdur.txt
