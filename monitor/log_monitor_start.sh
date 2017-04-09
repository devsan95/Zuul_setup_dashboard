#! /bin/bash 
moni_pid=$(ps -ef|grep "log_monitor.py"|grep -v "grep"|awk '{print $2}')

case ${stop_opt} in
    true)
       if [ -n "${moni_pid}" ];then
          kill -9 ${moni_pid}
       fi
    ;;
    false)
        if [ -n "${moni_pid}" ];then
            kill -9 ${moni_pid}
        fi
        source /root/mn_scripts/pyenv.sh
        nohup python /root/mn_scripts/monitor/log_monitor.py > /dev/null 2>&1 &
    ;;
    *)
        echo 'You do not select a right option'
    ;;
esac

