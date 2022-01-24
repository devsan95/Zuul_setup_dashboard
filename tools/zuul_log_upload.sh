#!/bin/bash

set -x

SCRIPT_FOLDER=$(dirname $(readlink -f "$0"))

# Change this value based on the environment.
ORG="5g"

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
    if [[ x"${container_name}" == x"zuul-server" ]] || \
       [[ x"$container_name" =~ ^xmerger.*.[0-9]*$ ]] || \
       [[ x"${container_name}" = x"gearman" ]]
    then
        echo "${container_name}"
        docker exec ${container_name} bash -c "/opt/zuul/script/upload_log_to_s3.sh ${HOSTNAME} ${container_name} ${ORG}"

    else
        echo "No need to upload logs for ${container_name} container."
    fi
done
