#!/bin/bash
#
# moniter gerrit branch diff error and bad pack header error.
set -xe

B=0
ZUULSERVICES='zuul-server zuul-merger'
cd /home/ca_5g_hz_scm

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
grep -B 1 "zuul.Merger: Unable to reset repo" $i-merger-debug.log | awk '{print $8}' > localreftemp.txt #collect all problem repos to list
sort -k2n localreftemp.txt | awk '{if ($0!=line) print;line=$0}' | awk '/ephemeral/' > localreftemp2.list
cat localreftemp2.list
rm -rf localreftemp.txt
while read line #do git command to every repo
do
    pwd
    local localrepopath=`echo ${line:16}`
    sudo docker exec $i bash -c "cd /ephemeral/zuul/$localrepopath;git remote prune origin"
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
grep -B 10 "fatal: protocol error: bad pack header" $i-merger-debug.log | grep "MN/5G" | grep "ref" | awk '{print $2}' > allbadpackheadertime-$i.txt
local bph1=`grep -B 10 "fatal: protocol error: bad pack header" $i-merger-debug.log | tail -10 | grep "MN/5G" | grep "ref" | awk '{print $2}'`
local bph2=`grep -w "$bph1" lastbadpackheadertime-$i.txt`

if [ -s "allbadpackheadertime-$i.txt" ];then
    if [ -n "$bph2" ];then
        echo "no new bad pack header error in sec-zuul-merger for now."
    else
        if [ -n "$bph1" ];then
	        if [ -s "lastbadpackheadertime-$i.txt" ];then
	            local bph3=`tail -1 lastbadpackheadertime-$i.txt`
		        echo $bph3
                echo $bph1 > lastbadpackheadertime-$i.txt
		        while read line1
		        do
		            local L3=`date +%s -d "$line1"`
			        local B3=`date +%s -d "$bph3"`
		            if [ $L3 -le $B3 ];then
			            echo "not a new bad pack header issue in $i."
			        else
                        echo "new bad pack header issue happening in $i, checking if cleanation is necessary."
			            local issuerepo=`grep -B 10 "fatal: protocol error: bad pack header" $i-merger-debug.log | grep "$line1" | awk '{print $11}'`
						awk -vRS="$bph1" '{t=$0;}END{print "$bph1"t }' $i-merger-debug.log > tmp1.log
						if grep -q "$issuerepo" tmp1.log ;then
						    echo "gc already done by gerrit team."
						else
						    let "B=B+1"
						    echo "$issuerepo" >> issue-repos-$i.list
						fi
			        fi
		        done < allbadpackheadertime-$i.txt
		    else
		        echo $bph1 > lastbadpackheadertime-$i.txt
                echo "new bad pack header issue happening in $i, checking if cleanation is necessary."
			    while read line2
		        do
			        local issuerepo=`grep -B 10 "fatal: protocol error: bad pack header" $i-merger-debug.log | grep "$line2" | awk '{print $11}'`
					awk -vRS="$bph1" '{t=$0;}END{print "$bph1"t }' $i-merger-debug.log > tmp1.log
					if grep -q "$issuerepo" tmp1.log ;then
						echo "gc already done by gerrit team."
					else
						let "B=B+1"
						echo "$issuerepo" >> issue-repos-$i.list
					fi
			    done < allbadpackheadertime-$i.txt
		    fi
	    else
	        echo "no new bad pack header error in $i for now."
	    fi
    fi
else
    echo "no bad pack header error in $i for now."
fi

sort -k2n issue-repos-$i.list|awk '{if ($0!=line) print;line=$0}' > issue-finalrepos-$i.list
rm -f issue-repos-$i.list
rm -f tmp1.log
cat issue-finalrepos-$i.list
}

##################################################################################
# main actions
##################################################################################
for i in $ZUULSERVICES
    do
        sudo docker cp $i:/ephemeral/log/zuul/merger-debug.log $i-merger-debug.log
        localref_prune
        bad_pack_header_moniter
done

echo "B = $B"
if [ $B -gt 0 ];then
    exit 1
fi
