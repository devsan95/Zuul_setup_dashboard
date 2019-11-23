#!/usr/bin/env bash

# Description:
# this script is provided to IT, when the zuul service which is on linsee. When linsee is going to MB, we
# need zuul service(zuul server, zuul merger, zuul mysql) can automatically recover.
#
# Functions:
# 1. basic start zuul service
# 2. service status check and support some known issue auto fix.
# 3. Inform zuul team when the exception can not be solved automatically.
#
# Author: irin.zheng@nokia-sbell.com

# TODO
# know issues solution need added
# 1. nginx-set docker container rename to nginx
# 2. auto fix when nginx container start failed
# 3. both in zuul server and zuul merger container,
#    httpd progress sometimes start failed(need to kill the progress then restart)
# 4. In zuul server, we need add an schedule to keep current changes status in zuul,
#    then when we restart the zuul server can recover it automatically.

CONTAINER_STATUS=""
PROGRESS_STATUS="NORMAL"
SHELL_FOLDER=$(dirname $(readlink -f "$0"))


# check what knid of zuul service on this linsee server , get it and recover it
function main(){
  # get all docker container at this server
  echo "Host: $(hostname)<br/>" > ${SHELL_FOLDER}/$(hostname).log
  container_names=($(sudo docker ps -a --format "{{.Names}}"))
  for container_name in "${container_names[@]}";
  do
    if [ x"$container_name" == x"zuul-server" ]; then
      restart_zuule1 "$container_name"
    elif [ x"$container_name" == x"zuul-server-lte" ]; then
      restart_zuullte "$container_name"
    elif [[ x"$container_name" =~ ^xmerger_.*_[1-9]*$ ]]; then
      restart_zuul_merger "$container_name"
    elif [ x"$container_name" == x"mysql" ]; then
      check_and_start_docker_container "$container_name"
    elif [ x"$container_name" == x"nginx-set" ]; then
      check_and_start_docker_container "$container_name"
    elif [ x"$container_name" == x"nginx" ]; then
      if [ x"$(hostname)" == x"eslinb49.emea.nsn-net.net" ]; then
        check_and_start_docker_container "$container_name"
      fi
    elif [ x"$container_name" == x"jenkins-prod" ]; then
        check_and_start_docker_container "$container_name"
    fi
  done

  # send information email
  source $(dirname ${SHELL_FOLDER})/pyenv.sh
  python ${SHELL_FOLDER}/zuul_notification_email.py -r ${SHELL_FOLDER}/$(hostname).log

}

# restart zuule1
function restart_zuule1(){
  container_name=$1
  # restart docker container
  check_and_start_docker_container "$container_name"
  if [ x"$CONTAINER_STATUS" == x"Up" ]; then
    # stop zuul-merger progress
    stop_progress_in_container "$container_name" "zuul-merger"
    # restart progress in container
    check_start_progress_in_container "$container_name" "zuul-server"
    check_start_progress_in_container "$container_name" "httpd"
    if [ x"${PROGRESS_STATUS}" == x"NORMAL" ]; then
      echo "recheck progress after 90 seconds..."
      echo "recheck progress after 90 seconds...<br/>" >> ${SHELL_FOLDER}/$(hostname).log
      sleep 90
      check_start_progress_in_container "$container_name" "zuul-server"
      check_start_progress_in_container "$container_name" "httpd"
    fi
    if [ x"${PROGRESS_STATUS}" == x"NORMAL" ]; then
      check_zuul_server_running_status
    fi
    PROGRESS_STATUS="NORMAL"
  fi
}

# restart zuullte
function restart_zuullte(){
  container_name=$1
  # restart docker container
  check_and_start_docker_container "$container_name"
  if [ x"$CONTAINER_STATUS" == x"Up" ]; then
    check_start_progress_in_container "$container_name" "zuul-server"
    check_start_progress_in_container "$container_name" "httpd"
    check_start_progress_in_container "$container_name" "zuul-merger"
    if [ x"${PROGRESS_STATUS}" == x"NORMAL" ]; then
      echo "recheck progress after 90 seconds..."
      echo "recheck progress after 90 seconds...<br/>" >> ${SHELL_FOLDER}/$(hostname).log
      sleep 90
      check_start_progress_in_container "$container_name" "zuul-server"
      check_start_progress_in_container "$container_name" "httpd"
      check_start_progress_in_container "$container_name" "zuul-merger"
    fi
    if [ x"${PROGRESS_STATUS}" == x"NORMAL" ]; then
      check_zuul_server_running_status
    fi
    PROGRESS_STATUS="NORMAL"
  fi
}

# restart zuul merger
function restart_zuul_merger() {
  merger_name=$1
  check_and_start_docker_container "$container_name"
  if [ x"$CONTAINER_STATUS" == x"Up" ]; then
    # stop zuul-server progress
    stop_progress_in_container "$container_name" "zuul-server"
    # start progress
    check_start_progress_in_container "$container_name" "httpd"
    check_start_progress_in_container "$container_name" "zuul-merger"
    if [ x"${PROGRESS_STATUS}" == x"NORMAL" ]; then
      echo "recheck progress after 90 seconds..."
      echo "recheck progress after 90 seconds...<br/>" >> ${SHELL_FOLDER}/$(hostname).log
      sleep 90
      check_start_progress_in_container "$container_name" "zuul-merger"
      check_start_progress_in_container "$container_name" "httpd"
      PROGRESS_STATUS="NORMAL"
    fi
  fi
}

# check docker container status
function check_and_start_docker_container() {
  container_name=$1
  container_status=$(sudo docker ps -a --format "{{.Names}}:{{.Status}}"|grep "${container_name}:"|awk -F ":" '{print $2}'|awk '{print $1}')
  if [ x"$container_status" == x"Up" ] ; then
    echo "$container_name container start success!"
    echo "Container: $container_name -> <font color='green'><b>Normal</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
    CONTAINER_STATUS="Up"
  else
    echo "$container_name container start Failed!"
    echo "Trying to restart it..."
    if sudo docker start "$container_name"; then
      echo "$container_name container start success!"
      echo "Container: $container_name -> <font color='green'><b>Normal</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      CONTAINER_STATUS="Up"
    else
      echo "$container_name container start Failed!"
      echo "Container: $container_name -> <font color='red'><b>Failed</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      CONTAINER_STATUS="Off"
    fi
  fi
}

# check progress status in docker container and restart it when it was not running
function check_start_progress_in_container() {
  container_name=$1
  progress_name=$2
  # for progress_name in ($(echo $progress_name|awk -F "," '{}'))
  # check progress status
  progress_status=$(sudo docker exec "$container_name" bash -c "supervisorctl status"|grep "$progress_name"|awk '{print $2}')
  if [ x"$progress_status" == x"RUNNING" ]; then
    echo "$progress_name in $container_name is running normal!"
    echo "Progress: $progress_name -> <font color='green'><b>Normal</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
  else
    echo "$progress_name in $container_name status was $progress_status!"
    echo "Trying to restart it..."
    sudo docker exec "$container_name" bash -c "supervisorctl restart $progress_name"
    progress_status=$(sudo docker exec "$container_name" bash -c "supervisorctl status"|grep "$progress_name"|awk '{print $2}')
    if [ x"$progress_status" == x"RUNNING" ]; then
      echo "$progress_name restart success!"
      echo "Progress: $progress_name -> <font color='green'><b>Normal</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
    else
      echo "$progress_name restart failed!"Failed
      echo "Progress: $progress_name -> <font color='red'><b>Failed</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      PROGRESS_STATUS="UNNORMAL"
    fi
  fi
}

# stop progress in container
function stop_progress_in_container() {
  container_name=$1
  progress_name=$2
  sudo docker exec "$container_name" bash -c "supervisorctl stop $progress_name"
  sleep 10
  progress_status=$(sudo docker exec "$container_name" bash -c "supervisorctl status"|grep "$progress_name"|awk '{print $2}')
  if [ x"$progress_status" == x"STOPPED" ]; then
      echo "$progress_name stop success!"
      echo "Progress: $progress_name stop-> <font color='green'><b>success</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
    else
      echo "$progress_name stop failed!"Failed
      echo "Progress: $progress_name stop-> <font color='red'><b>Failed</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
    fi
}

# check_zuul_server_running_status
function check_zuul_server_running_status() {
    echo "Check zuul server running status." >> ${SHELL_FOLDER}/$(hostname).log
    if wget http://127.0.0.1/status.json; then
      echo "Status.json check: <font color='green'><b>Normal</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
    else
      echo "Status.json check: <font color='red'><b>Failed</b></font><br/>. Can't find status.json<br/>" >> ${SHELL_FOLDER}/$(hostname).log
    fi
}

main