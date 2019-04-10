#!/bin/bash
set -x
A=0
B=0

function localref-prune(){
cd /var/fpwork/zuul_prod/log
#collect all problem repos to list
grep -B 1 "zuul.Merger: Unable to reset repo" merger-debug.log | awk '{print $8}' > localreftemp.txt
sort -k2n localreftemp.txt | awk '{if ($0!=line) print;line=$0}' | awk '/ephemeral/' > localreftemp1.list
cat localreftemp1.list
#do git command to every repo
while read line
do
    pwd
    localrepopath=`echo ${line:16}`
	sudo docker exec zuul-server bash -c "cd /ephemeral/zuul/$localrepopath;git remote prune origin"
done < localreftemp1.list
rm -rf localreftemp.txt
}

function localref-prune2(){
cd /home/ca_5g_hz_scm
sudo docker cp zuul-merger:/ephemeral/log/zuul/merger-debug.log merger2-debug.log
#collect all problem repos to list
grep -B 1 "zuul.Merger: Unable to reset repo" merger2-debug.log | awk '{print $8}' > localreftemp.txt
sort -k2n localreftemp.txt | awk '{if ($0!=line) print;line=$0}' | awk '/ephemeral/' > localreftemp2.list
cat localreftemp2.list
#do git command to every repo
while read line
do
    pwd
    localrepopath=`echo ${line:16}`
	sudo docker exec zuul-merger bash -c "cd /ephemeral/zuul/$localrepopath;git remote prune origin"
done < localreftemp2.list
rm -rf localreftemp.txt
}

function bad-pack-header-moniter(){
cd /var/fpwork/zuul_prod/log
cp merger-debug.log /home/ca_5g_hz_scm/
cd /home/ca_5g_hz_scm
pwd

grep -B 10 "fatal: protocol error: bad pack header" merger-debug.log | grep "MN/5G" | grep "ref" | awk '{print $2}' > allbadpackheadertime.txt
BPH1=`grep -B 10 "fatal: protocol error: bad pack header" merger-debug.log | tail -10 | grep "MN/5G" | grep "ref" | awk '{print $2}'`
BPH2=`grep -w "$BPH1" lastbadpackheadertime.txt`

if [ -s "allbadpackheadertime.txt" ];then
    if [ -n "$BPH2" ];then
        echo "no new bad pack header error in main-zuul-merger for now."
    else
        if [ -n "$BPH1" ];then
	        if [ -s "lastbadpackheadertime.txt" ];then
	            BPH3=`tail -1 lastbadpackheadertime.txt`
		        echo $BPH3
                echo $BPH1 > lastbadpackheadertime.txt
		        while read line1
		        do
		            L3=`date +%s -d "$line1"`
			        B3=`date +%s -d "$BPH3"`
		            if [ $L3 -le $B3 ];then
			            echo "not a new bad pack header issue in main-zuul-merger."
			        else
				        echo "new bad pack header issue happening in main-zuul-merger, checking if cleanation is necessary."
			            issuerepo=`grep -B 10 "fatal: protocol error: bad pack header" merger-debug.log | grep "$line1" | awk '{print $11}'`
						awk -vRS="$BPH1" '{t=$0;}END{print "$BPH1"t }' merger-debug.log > tmp.log
						if grep -q "$issuerepo" tmp.log ;then
						    echo "gc already done by gerrit team."
						else
						    let "A=A+1"
						    echo "$issuerepo" >> issue-repos.list
						fi
					fi
		        done < allbadpackheadertime.txt
		    else
		        echo $BPH1 > lastbadpackheadertime.txt
			    echo "new bad pack header issue happening in main-zuul-merger, checking if cleanation is necessary."
			    while read line2
		        do
			        issuerepo=`grep -B 10 "fatal: protocol error: bad pack header" merger-debug.log | grep "$line2" | awk '{print $11}'`
					awk -vRS="$BPH1" '{t=$0;}END{print "$BPH1"t }' merger-debug.log > tmp.log
					if grep -q "$issuerepo" tmp.log ;then
						echo "gc already done by gerrit team."
					else
						let "A=A+1"
						echo "$issuerepo" >> issue-repos.list
					fi
			    done < allbadpackheadertime.txt
		    fi
	    else
	        echo "no new bad pack header error in main-zuul-merger for now."
	    fi
    fi
else
    echo "no bad pack header error in main-zuul-merger for now."
fi

sort -k2n issue-repos.list|awk '{if ($0!=line) print;line=$0}' > issue-finalrepos.list
rm -f issue-repos.list
rm -f tmp.log
}

function bad-pack-header-moniter2(){
cd /home/ca_5g_hz_scm
sudo docker cp zuul-merger:/ephemeral/log/zuul/merger-debug.log merger2-loop-count.log

grep -B 10 "fatal: protocol error: bad pack header" merger2-loop-count.log | grep "MN/5G" | grep "ref" | awk '{print $2}' > allbadpackheadertime2.txt
BPH1=`grep -B 10 "fatal: protocol error: bad pack header" merger2-loop-count.log | tail -10 | grep "MN/5G" | grep "ref" | awk '{print $2}'`
BPH2=`grep -w "$BPH1" lastbadpackheadertime2.txt`

if [ -s "allbadpackheadertime2.txt" ];then
    if [ -n "$BPH2" ];then
        echo "no new bad pack header error in sec-zuul-merger for now."
    else
        if [ -n "$BPH1" ];then
	        if [ -s "lastbadpackheadertime2.txt" ];then
	            BPH3=`tail -1 lastbadpackheadertime2.txt`
		        echo $BPH3
                echo $BPH1 > lastbadpackheadertime2.txt
		        while read line1
		        do
		            L3=`date +%s -d "$line1"`
			        B3=`date +%s -d "$BPH3"`
		            if [ $L3 -le $B3 ];then
			            echo "not a new bad pack header issue in sec-zuul-merger."
			        else
                        echo "new bad pack header issue happening in main-zuul-merger, checking if cleanation is necessary."
			            issuerepo=`grep -B 10 "fatal: protocol error: bad pack header" merger2-loop-count.log | grep "$line1" | awk '{print $11}'`
						awk -vRS="$BPH1" '{t=$0;}END{print "$BPH1"t }' merger2-loop-count.log > tmp1.log
						if grep -q "$issuerepo" tmp1.log ;then
						    echo "gc already done by gerrit team."
						else
						    let "B=B+1"
						    echo "$issuerepo" >> issue-repos2.list
						fi
			        fi
		        done < allbadpackheadertime2.txt
		    else
		        echo $BPH1 > lastbadpackheadertime2.txt
                echo "new bad pack header issue happening in main-zuul-merger, checking if cleanation is necessary."
			    while read line2
		        do
			        issuerepo=`grep -B 10 "fatal: protocol error: bad pack header" merger2-loop-count.log | grep "$line2" | awk '{print $11}'`
					awk -vRS="$BPH1" '{t=$0;}END{print "$BPH1"t }' merger2-loop-count.log > tmp1.log
					if grep -q "$issuerepo" tmp1.log ;then
						echo "gc already done by gerrit team."
					else
						let "B=B+1"
						echo "$issuerepo" >> issue-repos2.list
					fi
			    done < allbadpackheadertime2.txt
		    fi
	    else
	        echo "no new bad pack header error in sec-zuul-merger for now."
	    fi
    fi
else
    echo "no bad pack header error in sec-zuul-merger for now."
fi

sort -k2n issue-repos2.list|awk '{if ($0!=line) print;line=$0}' > issue-finalrepos2.list
rm -f issue-repos2.list
rm -f tmp1.log
}

localref-prune
localref-prune2
bad-pack-header-moniter
bad-pack-header-moniter2

cd /home/ca_5g_hz_scm

echo "A = $A"
cat issue-finalrepos.list
echo "B = $B"
cat issue-finalrepos2.list
if [ $A -gt 0 ];then
	exit 1
fi
if [ $B -gt 0 ];then
    exit 1
fi
