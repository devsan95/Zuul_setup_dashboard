#!/bin/sh
 rm -rf /var/jenkins_home/jobs/Artifacts_backup_to_S3/workspace/tools/$1
 /home/ca_5g_hz_scm/jfrog_files/jf rt dl $2 --url=http://artifactory-espoo1.ext.net.nokia.com/artifactory/ --password=AKCp5fUhzkiwCThFrJYaGkNJ3xrBS8EntU9a21WUVbLCpyyeSxbLnKPetFvtzvXS7Kj5YbA3u --flat
/var/jenkins_home/jobs/Artifacts_backup_to_S3/workspace/tools/s3cmd put --acl-public -v /home/ca_5g_hz_scm/jfrog_files/artifact/$1 s3://zuul-5g/$3
