#!/usr/bin/env bash

set -x

JENKINS_HOME=$1
BK_DIR=${JENKINS_HOME}_$(date +%F_%H-%M)
S3_STORE=s3://zuul-jenkins-backup

cd ~
rm -f ${BK_DIR}*.gz.tar
echo "***** compress jenkins home start *****"
sudo tar -czf ${BK_DIR}.gz.tar ${JENKINS_HOME}
echo "***** compress jenkins home end *****"
if [[ $? -ne 0 ]]; then
  error "!!! create tar file FAIL"
else
  sh remove_expired_backup.sh "s3://zuul-jenkins-backup" "90 days"
  echo "***** upload jenkins backup file start *****"
  s3cmd put --acl-public --skip-existing ${BK_DIR}.gz.tar ${S3_STORE}
  echo "***** upload jenkins backup file end *****"
  if [[ $? -ne 0 ]]; then
    error "!!! s3 upload FAIL"
  else
    sudo rm -rf ${BK_DIR}.gz.tar
  fi
fi

