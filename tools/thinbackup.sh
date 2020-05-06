#!/bin/sh

cd /home/ca_zuuler/thinbackup_eslinb34/

docker exec -it -u root jenkins-prod bash -c "rm -rf /tmp/back.tar ; cd /tmp/backup/ ; tar -cvf  /tmp/back.tar FULL-*"

rm -rf back.tar

docker cp jenkins-prod:/tmp/back.tar . ; tar -xvf back.tar


find . -type d -ctime +30 -exec rm -rf {} \;

