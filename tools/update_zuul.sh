#!/usr/bin/env bash
export GIT_SSL_NO_VERIFY=true
supervisorctl stop zuul-server
supervisorctl stop zuul-merger
supervisorctl stop zuul-launcher
pip uninstall zuul -y
pip install git+ssh://ca_zuul_qa@gerrit.ext.net.nokia.com:29418/MN/SCMTA/zuul/zuul
supervisorctl start zuul-server
supervisorctl start zuul-merger
supervisorctl start zuul-launcher