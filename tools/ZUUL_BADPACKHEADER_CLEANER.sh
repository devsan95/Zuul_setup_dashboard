#!/bin/bash
#
# auto find bad pack header error and do local repo clean
set -xeo
GNBCOUNT=0
OTHERCOUNT=0
ZUULSERVERS='eslinb40.emea.nsn-net.net eslinb34.emea.nsn-net.net zuulmergeres42.dynamic.nsn-net.net'
ZUULSERVICES='zuul-server zuul-merger merger_eslinb34_1 merger_eslinb34_2 merger_es42_1 merger_es42_2'

##################################################################################
# funcation name:   zuul_badpackheader_cleaner
# description:      auto find bad pack header error and do local repo clean
# parameter1:
# parameter2:
# usage example:    zuul_badpackheader_cleaner
# return:           richard.1.hu@nokia-sbell.com
# author:           richard.1.hu@nokia-sbell.com
##################################################################################
function zuul_badpackheader_cleaner(){
grep -B 10 "fatal: protocol error: bad pack header" ${service}-merger-debug.log | grep "MN/5G" | grep "ref" | awk '{print $2}' > allbadpackheadertime-${service}.txt
BPH1=`grep -B 10 "fatal: protocol error: bad pack header" ${service}-merger-debug.log | tail -10 | grep "MN/5G" | grep "ref" | awk '{print $2}'`
BPH2=`grep -w "${BPH1}" lastbadpackheadertime-${service}.txt`

if [[ -s "allbadpackheadertime-${service}.txt" ]];then
    if [[ -n "${BPH2}" ]];then
        echo "no new bad pack header error in ${service}-zuul-merger for now."
    else
        if [[ -s "lastbadpackheadertime-${service}.txt" ]];then
            BPH3=`tail -1 lastbadpackheadertime-${service}.txt`
            echo ${BPH3}
            echo ${BPH1} > lastbadpackheadertime-${service}.txt
            while read line1
            do
                L3=`date +%s -d "${line1}"`
                B3=`date +%s -d "${BPH3}"`
                if [[ ${L3} -le ${B3} ]];then
                    echo "not a new bad pack header issue in ${service}."
                else
                    echo "new bad pack header issue happening in ${service}, checking if cleanation is necessary."
                    issuerepo=`grep -B 10 "fatal: protocol error: bad pack header" ${service}-merger-debug.log | grep "${line1}" | awk '{print $11}'`
                    awk -vRS="${BPH1}" '{t=$0;}END{print "${BPH1}"t }' ${service}-merger-debug.log > ${service}-tmp1.log #cut out a part of log from BPH1 to end
                    if grep -q "${issuerepo}" ${service}-tmp1.log ;then
                        echo "gc already done by gerrit team."
                    else
                        echo "${issuerepo}" >> issue-repos-${service}.list
                    fi
                fi
            done < allbadpackheadertime-${service}.txt
        else
            echo ${BPH1} > lastbadpackheadertime-${service}.txt
            echo "new bad pack header issue happening in ${service}, checking if cleanation is necessary."
            while read line2
            do
                issuerepo=`grep -B 10 "fatal: protocol error: bad pack header" ${service}-merger-debug.log | grep "${line2}" | awk '{print $11}'`
                awk -vRS="$BPH1" '{t=$0;}END{print "$BPH1"t }' ${service}-merger-debug.log > ${service}-tmp1.log
                if grep -q "${issuerepo}" ${service}-tmp1.log ;then
                    echo "gc already done by gerrit team."
                else
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
while read line3
do
    finalrepo=${line3}
    if [[ "${finalrepo}" == "MN/5G/NB/gnb" ]];then
        sudo docker exec ${service} bash -c "cd /ephemeral/zuul/git/MN/5G/NB;mv gnb gnb-$(date -d "today" +"%Y%m%d_%H%M%S")"
        echo "bad packer header happening in MN/5G/NB/gnb of ${service}"
        let "GNBCOUNT=GNBCOUNT+1"
    else
        re=`echo ${finalrepo##*/}`
        sudo docker exec ${service} bash -c "cd /ephemeral/zuul/git/${finalrepo};cd ..;mv ${re} ${re}-$(date -d "today" +"%Y%m%d_%H%M%S")"
        echo "bad packer header happening in ${finalrepo} of ${service}"
        let "OTHERCOUNT=OTHERCOUNT+1"
    fi
done < issue-finalrepos-${service}.list
}

##################################################################################
# main actions
##################################################################################
for server in ${ZUULSERVERS}
do
    I=`echo ${server:0:6}`
    if [[ "${I}"=="eslinb" ]];then
        ssh ca_5g_hz_scm@${server}
        for service in ${ZUULSERVICES}
        do
            pwd
            sudo docker cp ${service}:/ephemeral/log/zuul/merger-debug.log ${service}-merger-debug.log
            if [[ -s "${service}-merger-debug.log" ]];then
                zuul_badpackheader_cleaner
                cat issue-finalrepos-${service}.list
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
                zuul_badpackheader_cleaner
                cat issue-finalrepos-${service}.list
                rm -f ${service}-merger-debug.log
            else
                rm -f ${service}-merger-debug.log
                echo "no container called ${service} in ${server}, skip to try next in ZUULSERVICES list."
            fi
        done
    fi
done

echo "GNBCOUNT = ${GNBCOUNT}"
echo "OTHERCOUNT = ${OTHERCOUNT}"
if [[ ${GNBCOUNT} -gt 0 ]];then
    curl https://ece-ci.dynamic.nsn-net.net/job/CI_TOOLS/job/OPERATIONS/job/WORKSPACE_CLEANUP/build?token=thereisnodana
    exit 1
fi
if [[ ${OTHERCOUNT} -gt 0 ]];then
    exit 1
fi
