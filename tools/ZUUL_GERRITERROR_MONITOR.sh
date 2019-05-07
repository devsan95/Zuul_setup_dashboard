#!/bin/bash
#
# moniter gerrit branch diff error and bad pack header error.
set -xeo

COUNT=0
ZUULSERVERS='eslinb40.emea.nsn-net.net eslinb34.emea.nsn-net.net zuulmergeres42.dynamic.nsn-net.net'
ZUULSERVICES='zuul-server zuul-merger merger_eslinb34_1 merger_eslinb34_2 merger_es42_1 merger_es42_2'


##################################################################################
# funcation name:   localref-prune
# description:      run git command to currect local branch
# parameter1:
# parameter2:
# usage example:    localref-prune
# return:           richard.1.hu@nokia-sbell.com
# author:           richard.1.hu@nokia-sbell.com
##################################################################################
function localref_prune(){
grep -B 1 "zuul.Merger: Unable to reset repo" ${service}-merger-debug.log | awk '{print $8}' > localreftemp.txt #collect all problem repos to list
sort -k2n localreftemp.txt | awk '{if ($0!=line) print;line=$0}' | awk '/ephemeral/' > localreftemp2.list
cat localreftemp2.list
rm -rf localreftemp.txt
while read line #do git command to every repo
do
    pwd
    local localrepopath=`echo ${line:16}`
    sudo docker exec ${service} bash -c "cd /ephemeral/zuul/${localrepopath};git remote prune origin"
done < localreftemp2.list
}


##################################################################################
# funcation name:   bad-pack-header-moniter
# description:      moniter bad pack header error to give a warning
# parameter1:
# parameter2:
# usage example:    bad-pack-header-moniter
# return:           richard.1.hu@nokia-sbell.com
# author:           richard.1.hu@nokia-sbell.com
##################################################################################
function bad_pack_header_moniter(){
grep -B 10 "fatal: protocol error: bad pack header" ${service}-merger-debug.log | grep "MN/5G" | grep "ref" | awk '{print $2}' > allbadpackheadertime-${service}.txt
local bph1=`grep -B 10 "fatal: protocol error: bad pack header" ${service}-merger-debug.log | tail -10 | grep "MN/5G" | grep "ref" | awk '{print $2}'`
local bph2=`grep -w "${bph1}" lastbadpackheadertime-${service}.txt`

if [[ -s "allbadpackheadertime-${service}.txt" ]];then
    if [[ -n "${bph2}" ]];then
        echo "no new bad pack header error in sec-zuul-merger for now."
    else
        if [[ -s "lastbadpackheadertime-${service}.txt" ]];then
            local bph3=`tail -1 lastbadpackheadertime-${service}.txt`
            echo ${bph3}
            echo ${bph1} > lastbadpackheadertime-${service}.txt
            while read line1
            do
                local L3=`date +%s -d "${line1}"`
                local B3=`date +%s -d "${bph3}"`
                if [[ ${L3} -le ${B3} ]];then
                    echo "not a new bad pack header issue in ${service}."
                else
                    echo "new bad pack header issue happening in ${service}, checking if cleanation is necessary."
                    local issuerepo=`grep -B 10 "fatal: protocol error: bad pack header" ${service}-merger-debug.log | grep "${line1}" | awk '{print $11}'`
                    awk -vRS="${bph1}" '{t=$0;}END{print "$bph1"t }' ${service}-merger-debug.log > ${service}-tmp1.log
                    if grep -q "${issuerepo}" ${service}-tmp1.log ;then
                        echo "gc already done by gerrit team."
                    else
                        let "COUNT=COUNT+1"
                        echo "${issuerepo}" >> issue-repos-${service}.list
                    fi
                fi
            done < allbadpackheadertime-${service}.txt
        else
            echo ${bph1} > lastbadpackheadertime-${service}.txt
            echo "new bad pack header issue happening in ${service}, checking if cleanation is necessary."
            while read line2
            do
                local issuerepo=`grep -B 10 "fatal: protocol error: bad pack header" ${service}-merger-debug.log | grep "${line2}" | awk '{print $11}'`
                awk -vRS="${bph1}" '{t=$0;}END{print "$bph1"t }' ${service}-merger-debug.log > ${service}-tmp1.log
                if grep -q "${issuerepo}" ${service}-tmp1.log ;then
                    echo "gc already done by gerrit team."
                else
                    let "COUNT=COUNT+1"
                    echo "${issuerepo}" >> issue-repos-${service}.list
                fi
            done < allbadpackheadertime-${service}.txt
        fi
    fi
else
    echo "no bad pack header error in ${service} for now."
fi

sort -k2n issue-repos-${service}.list|awk '{if ($0!=line) print;line=$0}' > issue-finalrepos-${service}.list
rm -f issue-repos-${service}.list
rm -f ${service}-tmp1.log
cat issue-finalrepos-${service}.list
}


##################################################################################
# main actions
##################################################################################
for server in ${ZUULSERVERS}
do
    I=`echo ${server:0:6}`
    if [[ "$I"=="eslinb" ]];then
        ssh ca_5g_hz_scm@${server}
        for service in $[ZUULSERVICES]
        do
            pwd
            sudo docker cp ${service}:/ephemeral/log/zuul/merger-debug.log ${service}-merger-debug.log
            if [[ -s "${service}-merger-debug.log" ]];then
                localref_prune
                bad_pack_header_moniter
                rm -f ${service}-merger-debug.log
            else
                rm -f ${service}-merger-debug.log
                echo "no container called ${service} in ${server}, skip to try next in ZUULSERVICES list."
            fi
        done
    else
        ssh -i /root/.ssh/5gscm.pem root@${server}
        for service in ${ZUULSERVICES}
        do
            pwd
            sudo docker cp ${service}:/ephemeral/log/zuul/merger-debug.log ${service}-merger-debug.log
            if [[ -s "${service}-merger-debug.log" ]];then
                localref_prune
                bad_pack_header_moniter
                rm -f ${service}-merger-debug.log
            else
                rm -f ${service}-merger-debug.log
                echo "no container called ${service} in ${server}, skip to try next in ZUULSERVICES list."
            fi
        done
    fi
done

echo "COUNT = ${COUNT}"
if [[ ${COUNT} -gt 0 ]];then
    exit 1
fi
