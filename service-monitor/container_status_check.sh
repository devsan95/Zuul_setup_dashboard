#!/usr/bin/env bash
#
# Check containers' status at server and try to restart some containers when it was exited
##################################################################################
# funcation name:   restart_container_and_log
# description:      restart container and writer log at target file
# parameter1:       container_name
# parameter2:
# usage example:    restart_container_and_log
# return:           irin.zheng@nokia-sbell.com
# author:           irin.zheng@nokia-sbell.com
##################################################################################
restart_container_and_log(){
  echo -e "<font size='5'><font color='red'><b>$container_name</b></font> container at <font color='red'><b>$(hostname)</b></font> is exited, trying restart.</font><br/>" >>$(hostname).log
  sudo docker start $container_name
  if [ $? -eq 0 ]; then
    echo "<font size='5'><font color='red'><b>$container_name</b></font> container at <font color='red'><b>$(hostname)</b></font> restart success, kindly check and make sure!</font><br/>">>$(hostname).log
  else
    echo "<font size='5'><font color='red'><b>$container_name</b></font> container at <font color='red'><b>$(hostname)</b></font> restart faild, please check ASAP!</font><br/>">>$(hostname).log
  fi
}

# main process
exited_containers_info=$(sudo docker ps -a --format "{{.Names}}: {{.Status}}" -f status=exited)
if test -n "$exited_containers_info"; then
    echo "--------------- START:show exited containers at $(hostname) ---------------"
    echo "$exited_containers_info"
    echo "--------------- END:  show exited containers at $(hostname)---------------"
    container_names=($(echo "$exited_containers_info"|awk -F ":" '{print $1}'))
    rm -rf $(hostname).log
    for container_name in "${container_names[@]}";
    do
        if [ x"$container_name" == x"zuul-server" ]; then
            restart_container_and_log
        elif [ x"$container_name" == x"zuul-server-lte" ]; then
            restart_container_and_log
        #elif [ x"$container_name" == x"zuul-merger" ]; then
        #    if [ x"$(hostname)" == x"eslinb40.emea.nsn-net.net" ]; then
        #        echo "<font size='5'><font color='red'><b>$container_name</b></font> container at <font color='red'><b>$(hostname)</b></font> is exited, due to this is special container, can't restart it, please check ASAP!</font><br/>" >>$(hostname).log
        #    else
        #        restart_container_and_log
        #    fi
        #elif [[ x"$container_name" =~ ^xmerger_.*_[1-9]*$ ]]; then
        #    restart_container_and_log
        elif [ x"$container_name" == x"mysql" ]; then
            restart_container_and_log
	elif [ x"$container_name" == x"nginx_set" ]; then
	    restart_container_and_log
	elif [ x"$container_name" == x"jenkins-prod" ]; then
	    restart_container_and_log
        fi
    done
else
    echo "--------------- INFO: Containers are running good at $(hostname) ---------------"
fi
if [ -f "$(hostname).log" ]; then
  scp ./$(hostname).log root@10.157.164.203:/var/fpwork/container_status/
fi
