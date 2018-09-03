#!/bin/bash
#for job http://jenkins-prod.zuulqa.dynamic.nsn-net.net/view/zuul_tools/job/zuul-localrepo-cleaner/

set -x
function merger-loop-count(){
cd /var/fpwork/zuul_prod/log
grep -e "Got merge job" -e "CreateZuulRef" merger-debug.log|grep -B 1 "CreateZuulRef"|grep -A 1 "Got merge job"|awk '{print $2}{print $12}'|tr -s '\n'|sed 'N;N;s/\n//g'|sed 's/\/.git">$//'|sed 's/\"//g' > mergeloopcount.txt
cat mergeloopcount.txt|cut -c 45- > merge-repopath.txt
sort -k2n merge-repopath.txt|awk '{if ($0!=line) print;line=$0}' > merge-repopath1.txt
rm -f merge-repopath.txt

while read line1
do
    set i=0
	repo=$line1
	
	while read line2
    do
        localrepo=${line2:44}
	    Got=`echo $(date +%s -d ${line:0:12})`
	    Create=`echo $(date +%s -d ${line:12:12})`
        merloop=$(($Create-$Got))
		
	    if [ $merloop -gt 20 ]&&[ "$localrepo" -eq "$repo" ];then
	        let "i=i+1"
		fi
	done < mergeloopcount.txt
	echo $i
	if [ $i -gt 10 ];then
	    if [ "$repo" -eq "MN/5G/NB/gnb" ];then
                    docker exec zuul-server bash -c "cd /ephemeral/zuul/git/$repo;git prune&&git gc"
		    #cd /var/fpwork/zuul_prod/$repo
		    #cd ..
		    #mv gnb gnb-$(date -d "today" +"%Y%m%d_%H%M%S")
		    curl http://5g-cimaster-1.eecloud.dynamic.nsn-net.net:15080/job/CI/job/MAINTENANCE/job/WORKSPACE_CLEANUP/build?token=thereisnodana
		    exit 1
		else
                    docker exec zuul-server bash -c "cd /ephemeral/zuul/git/$repo;git prune&&git gc"
		    #cd /var/fpwork/zuul_prod/$repo
		    #cd ..
		    #re=`echo ${repo##*/}`
		    #mv $re $re-$(date -d "today" +"%Y%m%d_%H%M%S")
		    exit 1
	    fi
	fi
done < merge-repopath1.txt
}

merger-loop-count
