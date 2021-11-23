#!/bin/sh

mkdir -p /tmp/layout_file
rm -rf /tmp/layout_file/layout.yaml
cd /tmp/layout_file
wget http://zuule1.dynamic.nsn-net.net/zuul_log/layout.yaml
echo "#jayanth" >> /tmp/layout_file/layout.yaml
rm -rf /etc/zuul/layout.yaml
cp /tmp/layout_file/layout.yaml /etc/zuul/
