#! /bin/bash
#for job http://jenkins-prod.zuulqa.dynamic.nsn-net.net/job/zuul-loop-duration/

set -x
set i=0
listB="bigpatchsetlist.txt"
loopf="loopduration.txt"
tempf="search-temp.txt"

function big-patchset(){
cd /var/fpwork/zuul_jenkins/jenkins-qa/workspace/zuul-loop-duration
rm -f $listB
rm -f $loopf
rm -f $tempf
grep -e "Received data from Gerrit query" -e "Getting git-dependent change" long-loop-$BUILD_NUMBER.txt|grep -B 1 "Getting git-dependent change"|grep -A 1 "Received data from Gerrit query"|awk '{print $2}{print $9}'|tr -s '\n' > a.txt
sed -i '/Gerrit/d' a.txt
cat a.txt|sed 's/>:$//'|sed 'N;N;s/\n//g' > $tempf
rm -f a.txt
while read line
do
	query1=`echo ${line:0:12}`
	dependent1=`echo ${line:12:12}`
	if [ "$query1" != "$dependent1" ];then
		lineNO=`sed -n "/${query1}/,/${dependent1}/p" long-loop-$BUILD_NUMBER.txt | wc -l`
		if [ $lineNO -gt 5000 ];then
		    let "i=i+1"
		    echo ${line:24} >> $listB
		fi
	fi
done < $tempf
}

function loop-duration(){
cd /var/fpwork/zuul_prod/log
grep "Run handler sleeping" server-debug.log|tail -2|awk '{print $2}' > loop.txt
t1=$(cat loop.txt | awk 'NR==1')
t2=$(cat loop.txt | awk 'NR==2')
if [ -n "$t1" ] && [ -n "$t2" ];then
    duration=$(($(date -d $t2 +%s) - $(date -d $t1 +%s)))
    #echo "$duration sec now!" 
    if [ $duration -le 300 ];then
        echo "zuul loop time is $duration sec now, faster faster faster!"
    else
        sed -n "/${t1}/,/${t2}/p" server-debug.log > /var/fpwork/zuul_jenkins/jenkins-qa/workspace/zuul-loop-duration/long-loop-$BUILD_NUMBER.txt
		echo "[WARNING!]zuul loop time is $duration sec now!"
		cd /var/fpwork/zuul_jenkins/jenkins-qa/workspace/zuul-loop-duration
		let "buildB=$BUILD_NUMBER-1"
		echo $buildB
		if [ ! -f "/var/fpwork/zuul_jenkins/jenkins-qa/workspace/zuul-loop-duration/long-loop-*.txt" ] || [ $(cat long-loop-$BUILD_NUMBER.txt | wc -l) -ne $(cat long-loop-$buildB.txt | wc -l) ];then
            big-patchset
		    echo $i
            if [ $i -gt 0 ];then
                cat $listB
			    echo "[WARNING!]zuul loop time is $duration sec now, $i BIG PATCHSET on gerrit may cause SLOWNESS!!!" > $loopf
	            exit 1
			fi
	    fi
	fi
fi
}

loop-duration
