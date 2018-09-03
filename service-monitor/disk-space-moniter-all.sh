#!/bin/bash

set -x
rm -f servername*
hostname=`hostname`
#exceptlist="except.list"
#lessspace=2097152
lessspace=90
df -h | awk '{print $5$6}' > used.list
cat used.list
sed -i '1d' used.list
while read line
do
    Mounted=`echo ${line#*%}`
    Use=`echo ${line%%%*}`
    if [ -f "diskexcept.list" ];then
        let "i=0"
        while read line1
        do
            #set i=0
            if [ "$line1" == "$Mounted" ];then
                let "i=i+1"
            fi
        done < diskexcept.list
        echo $i
        if [ $i -gt 0 ];then
            echo "Exception, no need to monit this $Mounted disk."
        else
            echo "$Mounted Monitering!"
            if [ $Use -le $lessspace ];then
                echo "This $Mounted disk space looks well for now."
            else
                echo "[WARNING] $Mounted disk space on $hostname SPACE ALARM, more than 90%!!!"
                df -h
                echo $Mounted >> servername_$hostname
                #scp servername_$hostname root@10.157.164.206:/ephemeral/workspace/workspace/SERVERS_DISK_MONITOR/
            fi
        fi
    else
        echo "no exception list."
        if [ $Use -le $lessspace ];then
            echo "This $Mounted disk space looks well for now."
        else
            echo "[WARNING] $Mounted disk space on $hostname SPACE ALARM, more than 90%!!!"
            df -h
            echo $Mounted >> servername_$hostname
            #scp servername_$hostname root@10.157.164.206:/ephemeral/workspace/workspace/SERVERS_DISK_MONITOR/
        fi
    fi
done < used.list
rm -f used.list
if [ -f "servername_$hostname" ];then
    scp servername_$hostname root@10.157.164.206:/ephemeral/workspace/workspace/SERVERS_DISK_MONITOR/
fi
