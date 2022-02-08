#!/bin/bash

set -x

# Note: Set ORG value in server's environment variable as shwon below.
# Step1: open .bash_profile
# vi .bash_profile
# Step2: Add the below line in .bash_profile (example for 5g).
# export ORG=5g
# Step3: Apply the change to bash_profile.
# source ~/.bash_profile

# If this script run in cron job then below line is required to load the environment variable.
. ~/.bash_profile > /dev/null 2>&1

# /opt/zuul/script/upload_log_to_s3.sh script is required and should be available inside docker container
# https://gerrit.ext.net.nokia.com/gerrit/gitweb?p=MN/SCMTA/zuul/mn_scripts.git;a=blob;f=tools/upload_log_to_s3.sh;h=fcbf7bc61d7689f3e3a59270737f0509250b3947;hb=refs/heads/master

SCRIPT_FOLDER=$(dirname $(readlink -f "$0"))

# short hostname
HOSTNAME=$(hostname -s)

# Check if HOSTNAME and ORG are set in environment variable.
if [[ -z ${HOSTNAME} ]] || [[ -z ${ORG} ]]; then
    echo "HOSTNAME or ORG is not set"
    exit 1
fi


# Check if docker daemon is running or not.
sudo docker info > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "Cannot connect to the Docker daemon. Is the docker daemon running?"
  exit 1
fi

# List all the running containers
container_names=($(sudo docker ps --format "{{.Names}}"))

# When there is no running container
if [[ ${#container_names[@]} -lt 1 ]]; then
    echo "No running container found"
    exit 1
fi

for container_name in "${container_names[@]}"; do
    if [[ x"${container_name}" =~ ^xzuul-server.*$ ]] || \
       [[ x"$container_name" =~ ^xmerger.*.[0-9]*$ ]] || \
       [[ x"${container_name}" == x"gearman" ]]
    then
        echo "${container_name}"
        docker exec ${container_name} bash -c "/opt/script/upload_log_to_s3.sh ${HOSTNAME} ${container_name} ${ORG}"

    else
        echo "No need to upload logs for ${container_name} container."
    fi
done