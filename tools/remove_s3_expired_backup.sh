#!/bin/bash

# ==============================================================
# Date: 2022-10-09
# Author: marwu
# Comment: remove s3 expired files
# parameters:
#   S3_BUCKET: s3 bucket absolute path, for example: s3://zuul-5g/logs/5g/
#   DAYS_TO_KEEP: the keep days of the file saved in s3 that

# ==============================================================

set -ex

S3_BUCKET=$1
DAYS_TO_KEEP=$2

s3cmd ls ${S3_BUCKET} | while read -r line; do

    createDate=`echo $line|awk {'print $1" "$2'}`
    createDate=`date -d"$createDate" +%s`
    olderThan=`date -d"-${DAYS_TO_KEEP}" +%s`
    if [[ $createDate -lt $olderThan ]]
        then 
        fileName=`echo $line|awk {'print $4'}`
        echo $fileName
        if [[ $fileName != "" ]]
            then
            s3cmd del "$fileName"
        fi
    fi
done