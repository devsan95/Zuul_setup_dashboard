#!/usr/bin/env bash

# Description:
# this script is provided to IT, when the zuul service which is on linsee. When linsee is going to MB, we
# need zuul service(zuul server, zuul merger, zuul mysql) can automatically recover.

# script performs check on docker and if stopped it will try to start it again
# if docker is started, based on the hostname of the server, it will try to start the containers in their associated lists
# the containers will be started in the list order 
# For zuul and merger containers it will test the processesc and if stopped it will restart them...........

#Mail notifications will be sent when script is completed




CONTAINER_STATUS=""
PROCESS_STATUS="RUNNING"
SHELL_FOLDER=$(dirname $(readlink -f "$0"))
DOCKER_STATUS=""
DOCKER_START_ATTEMPTS=0

# Update list with proper containers to be started and the correct order
container_names_5G_eslinb40=("gearman" "zuul-server" "cadvisor")
container_names_5G_eslinb33=("mysql" "merger-0" "merger-1" "cadvisor")
container_names_5G_eslinb34=("mysql" "jenkins_prod_new" "merger_eslinb34_1" "merger_eslinb34_2" "nginx" "cadvisor")
container_names_SRAN_eslinb49=("mysql" "gearman" "merger_1" "zuul-server-lte" "nginx" "cadvisor")
container_names_RF_eslinb47=("mysql" "gearman" "merger_1" "merger_3" "zuul-server" "cadvisor")
container_names_TIMI_DEV_QA=("mysql" "gearman" "zuul-merger" "merger_1" "zuul-server" "cadvisor")

function create_symbolic_link(){
  echo "Creating symbolic link for cAdvisor"
  mount -o remount,rw '/sys/fs/cgroup/'
  ln -s /sys/fs/cgroup/cpu,cpuacct /sys/fs/cgroup/cpuacct,cpu
  mount -o remount,ro '/sys/fs/cgroup/'
}

function main(){
  # get server hostname
  echo "Host: $(hostname)<br/>" > ${SHELL_FOLDER}/$(hostname).log
  
  # check docker status
  check_docker_process
  
    #take action depending on docker state
  if [ x"$DOCKER_STATUS" == x"ACTIVE" ]; then
  echo "Docker service is ACTIVE"
  # start containers based on what server we are executing the script

    if [ x"$(hostname)" == x"eslinb40.emea.nsn-net.net" ]; then
      for container_name in "${container_names_5G_eslinb40[@]}";
      do
           startup $container_name
      done
      #test if zuul status page is reachable
      echo "..........................."
      echo "<font color='black'><b>..................................................</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      check_zuul_server_running_status
    
    elif [ x"$(hostname)" == x"eslinb33.emea.nsn-net.net" ]; then
      for container_name in "${container_names_5G_eslinb33[@]}";
      do
           startup $container_name
      done
      
    elif [ x"$(hostname)" == x"eslinb34.emea.nsn-net.net" ]; then
      for container_name in "${container_names_5G_eslinb34[@]}";
      do
           startup $container_name
      done

    elif [ x"$(hostname)" == x"eslinb49.emea.nsn-net.net" ]; then
      for container_name in "${container_names_SRAN_eslinb49[@]}";
      do
          startup $container_name
      done
      #test if zuul status page is reachable
      echo "..........................."
      echo "<font color='black'><b>..................................................</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      check_zuul_server_running_status
    
    elif [ x"$(hostname)" == x"eslinb47.emea.nsn-net.net" ]; then
      for container_name in "${container_names_RF_eslinb47[@]}";
      do
          startup $container_name
      done
      #test if zuul status page is reachable
      echo "..........................."
      echo "<font color='black'><b>..................................................</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      check_zuul_server_running_status
    
    elif [ x"$(hostname)" == x"zuul-timi-dev2.novalocal" ]; then
    
      for container_name in "${container_names_TIMI_DEV_QA[@]}";
      do
          startup $container_name
      done
      #test if zuul status page is reachable
      echo "..........................."
      echo "<font color='black'><b>..................................................</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      check_zuul_server_running_status
    
    fi

  elif [ x"$DOCKER_STATUS" == x"INACTIVE" ]; then
    echo "Docker service is INACTIVE"
    echo "Docker multiple start attempts failed. Please call IT support <br/>" >> ${SHELL_FOLDER}/$(hostname).log
    echo "Docker: <font color='red'><b> INACTIVE </b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log

   fi
  
  # send information email
  source $(dirname ${SHELL_FOLDER})/pyenv.sh
  python ${SHELL_FOLDER}/zuul_notification_email.py -r ${SHELL_FOLDER}/$(hostname).log
}

function startup() {

      container_name=$1
      if  [[ x"$container_name" =~ .*zuul-server.* ]]; then
        start_zuul "$container_name"
      elif [[ x"$container_name" =~ .*merger.* ]]; then
        start_zuul "$container_name"
      else 
        check_and_start_docker_container "$container_name"
        echo "recheck container status"
        echo "Re-checking container status <br/>" >> ${SHELL_FOLDER}/$(hostname).log
        check_and_start_docker_container "$container_name"
      fi

}

# check docker container status
function check_and_start_docker_container() {
  container_name=$1
  container_status=$(sudo docker ps -a --format "{{.Names}}:{{.Status}}"|grep "${container_name}:"|awk -F ":" '{print $2}'|awk '{print $1}')
  echo "..........................."
  echo "<font color='black'><b>..................................................</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
  if [ x"$container_status" == x"Up" ] ; then
    echo "$container_name container is STARTED"
    echo "Container: $container_name -> <font color='green'><b>STARTED</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
    CONTAINER_STATUS="Up"
  else
    echo "$container_name container is STOPPED"
    echo "Trying to start it..."
    if sudo docker start "$container_name"; then
      echo "$container_name container STARTED"
      echo "Container: $container_name -> <font color='green'><b>STARTED</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      CONTAINER_STATUS="Up"
    else
      echo "$container_name container start FAILED"
      echo "Container: $container_name -> <font color='red'><b>FAILED</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      CONTAINER_STATUS="Off"
    fi
  fi
  sleep 5
     
}

# start zuul merger / server and their processes
function start_zuul() {
  container_name=$1
  processes=()
  check_and_start_docker_container "$container_name"
  if [ x"$CONTAINER_STATUS" == x"Up" ]; then
    
    process=$(sudo docker exec "$container_name" bash -c "supervisorctl status" |awk -F'[ ]' '{print $1}')
    processes=(${process//\\n/ })
    for process in "${processes[@]}";
    do
      check_process_in_container $container_name $process
      #echo $PROCESS_STATUS
      #if [ $PROCESS_STATUS == "FAILED" ]; then
      #  echo "recheck process after 10 seconds..."
      #  echo "recheck process after 10 seconds...<br/>" >> ${SHELL_FOLDER}/$(hostname).log
      #  sleep 1
      #  check_process_in_container $container_name $process
      #fi
    done
   fi
}

# check process status in docker container and restart it when it was not running
function check_process_in_container() {
  container_name=$1
  process_name=$2
  # for process_name in ($(echo $process_name|awk -F "," '{}'))
  # check process status
  process_status=$(sudo docker exec "$container_name" bash -c "supervisorctl status"|grep "$process_name"|awk '{print $2}')
  if [ x"$process_status" == x"RUNNING" ]; then
    echo ">> $process_name in $container_name is RUNNING"
    echo "  - Process: $process_name -> <font color='green'><b>RUNNING</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
  else
    echo "$process_name in $container_name status was $process_status!"
    echo "    Trying to restart it..."
    sudo docker exec "$container_name" bash -c "supervisorctl restart $process_name"
    echo "    Waiting for processes to come up"
    sleep 10
    process_status=$(sudo docker exec "$container_name" bash -c "supervisorctl status"|grep "$process_name"|awk '{print $2}')
    
    if [ x"$process_status" == x"RUNNING" ]; then
      echo "$process_name restart success!"
      echo "  - Process: $process_name -> <font color='green'><b>RUNNING</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      PROCESS_STATUS="RUNNING"
    else
      echo "$process_name start FAILED"
      echo "  - Process: $process_name -> <font color='red'><b>FAILED</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      PROCESS_STATUS="FAILED"
    fi
  fi
}

# check_zuul_server_running_status
function check_zuul_server_running_status() {
    echo "Check zuul server running status." >> ${SHELL_FOLDER}/$(hostname).log
    if wget http://127.0.0.1/status.json; then
      echo "Status.json check: <font color='green'><b>AVAILABLE</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
      rm status.json*
    else
      echo "Status.json check: <font color='red'><b>FAILED</b></font><br/>. Can't find status.json<br/>" >> ${SHELL_FOLDER}/$(hostname).log
    fi
}

#check docker service status
function check_docker_process() {
  echo "Check docker process status"
  docker_status=$(sudo systemctl show docker --property=ActiveState)
  
  if [[ $docker_status =~ .*=inactive.* ]]; then
       echo "Docker is not active. Starting it now..."
   
       DOCKER_STATUS="INACTIVE"
       systemctl start docker
       
       if [ $DOCKER_START_ATTEMPTS -le 2 ]; then
       
          echo "Waiting for docker to start"
          sleep 5
          echo "Attempt $DOCKER_START_ATTEMPTS"
          ((DOCKER_START_ATTEMPTS++))
          check_docker_process
       fi
        

  else
    DOCKER_STATUS="ACTIVE"
    echo "Docker -> <font color='green'><b>ACTIVE</b></font><br/>" >> ${SHELL_FOLDER}/$(hostname).log
  fi
}

create_symbolic_link
main
