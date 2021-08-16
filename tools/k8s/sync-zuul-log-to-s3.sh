#!/bin/bash



while true;
do
    log_dir="/ephemeral/log/zuul/"

    # Revmove 2 days ago first
    find ${log_dir} -type f -mtime +0 | xargs rm -rf &>/dev/null

    # yeserdasy string
    yesterday=$(date -d '-1 day' '+%Y-%m-%d' | xargs echo -n)


    echo "================================================== [ $(date|xargs echo -n) ] sync start for ${yesterday} ===================================================================="


    # Sync file only for yesterday
    ls ${log_dir} > zuul_id.list

    while read -r zuul_id;
    do
            for file in `find ${log_dir} -type f | grep "${yesterday}"  | grep $zuul_id`;
            do
                zuul_container_id=$( echo "${file}" | awk -F'/' '{print $(NF-1)}' | xargs echo -n  )

                set -x
                s3cmd sync --acl-public ${file} s3://zuul-5g/logs/zuul/${zuul_id}/${zuul_container_id}/
                set +x

            done 
    done < zuul_id.list

    echo "====================================================================[ $(date|xargs echo -n) ] end ===================================================================="

    sleep 3600

done
