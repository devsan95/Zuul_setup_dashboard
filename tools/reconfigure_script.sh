#!/usr/bin/env bash

Capture_time(){
  mkdir -p /tmp/zuul_layout
  mkdir -p /tmp/layout_file
  mkdir -p /tmp/zuul_chnage
  rm -rf /tmp/layout_file/layout.yaml
  cd /tmp/layout_file
  wget http://zuule1.dynamic.nsn-net.net/zuul_log/layout.yaml
  echo "#jayanth" >> /tmp/layout_file/layout.yaml
  rm -rf /etc/zuul/layout.yaml
  cp /tmp/layout_file/layout.yaml /etc/zuul/
  /bin/kill -SIGHUP `supervisorctl pid zuul-server`
  rm -rf /tmp/test
  mkdir -p /tmp/test
  cd /tmp/test
  wget http://zuule1.dynamic.nsn-net.net/zuul_log/layout.yaml
  mv layout.yaml /tmp/zuul_layout/
 # wget http://10.157.98.251/zuul_log/layout.yaml
  wget http://zuul-code.zuulqa.dynamic.nsn-net.net/zuul_log/layout.yaml
  mv layout.yaml /tmp/zuul_chnage/
 diff /tmp/zuul_layout/layout.yaml /tmp/zuul_chnage/layout.yaml

 if [ $? -eq 0 ] ; then
    echo "No new changes are applied"
    exit 1
 else
    echo "Yes changes are applied and refreshed"
 fi

}



Capture_time
