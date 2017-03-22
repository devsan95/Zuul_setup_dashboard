#!/usr/bin/env bash
export GIT_SSL_NO_VERIFY=true
supervisorctl stop zuul-server
supervisorctl stop zuul-merger
supervisorctl stop zuul-launcher
pip uninstall zuul -y
pip install git+http://gerrit.app.alcatel-lucent.com/gerrit/MN/SCMTA/zuul/zuul
supervisorctl start zuul-server
supervisorctl start zuul-merger
supervisorctl start zuul-launcher