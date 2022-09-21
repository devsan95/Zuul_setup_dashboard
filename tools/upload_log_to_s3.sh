#!/bin/bash

set -xe

HOSTNAME=$1
container_name=$2
ORG=$3
container_log_dir=$4

s3_log_dir="s3://zuul-5g/logs/${ORG}/${HOSTNAME}/${container_name}/"
#s3_log_dir="s3://zuul-5g/logs/zuul/Deepak/${ORG}/${HOSTNAME}/${container_name}/"
Log_File="*.log.*"

# Check how many files to upload
count=$(find ${container_log_dir} -maxdepth 1 -type f -name "${Log_File}" | wc -l)
if [[ ${count} > 0 ]]; then
    echo "Uploading log files to S3..."
    s3cmd put --acl-public -v ${container_log_dir}/${Log_File} ${s3_log_dir}
    echo "Upload completed."
else
    echo "Nothing to upload..."
    exit 1
fi

# create ./old_logs direcorty if do not exist
mkdir -p ${container_log_dir}/old_logs
# Delete old logs
rm -rf ${container_log_dir}/old_logs/*
# Move log files older than 10 day to old_logs directory
find ${container_log_dir} -maxdepth 1 -type f -name "${Log_File}" -mtime +10 -exec mv {} ${container_log_dir}/old_logs/ \;