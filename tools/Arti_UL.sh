#!/bin/sh
if test -f "jf" ; then
 echo "Jfrog binary exist"
else
 s3cmd get --acl-public s3://zuul-5g/logs/jf . ; chmod 777 jf
fi

./jf rt dl $1 --url=http://artifactory-espoo1.ext.net.nokia.com/artifactory/ --password=AKCp5fUhzkiwCThFrJYaGkNJ3xrBS8EntU9a21WUVbLCpyyeSxbLnKPetFvtzvXS7Kj5YbA3u --flat
s3cmd put --acl-public -v $2 s3://zuul-5g/$3
