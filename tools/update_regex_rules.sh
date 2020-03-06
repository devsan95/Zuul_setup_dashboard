#!bin/bash
zuul jobfilter --project MN/SCMTA/zuul/zuul-dummy --change 1320414,1 --layout /etc/zuul/layout.yaml --output /tmp/tmpjoblist --regex /ephemeral/zuul/www/zuul_log/rules
sed  -i "1i layout$(sed -n '2p' /etc/zuul/layout.yaml)" /ephemeral/zuul/www/zuul_log/rules

