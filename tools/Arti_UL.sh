#!/bin/sh
cd /home/ca_5g_hz_scm/jfrog_files/artifact
 rm -rf /home/ca_5g_hz_scm/jfrog_files/artifact/$artifact
 /home/ca_5g_hz_scm/jfrog_files/jf rt dl $Repo_path --url=http://artifactory-espoo1.ext.net.nokia.com/artifactory/ --password=AKCp5fUhzkiwCThFrJYaGkNJ3xrBS8EntU9a21WUVbLCpyyeSxbLnKPetFvtzvXS7Kj5YbA3u --flat
 s3cmd put --acl-public -v /home/ca_5g_hz_scm/jfrog_files/artifact/$artifact s3://zuul-5g/$s3_path
