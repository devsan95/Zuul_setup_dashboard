rm -rf $1.zuul.conf

$ZUUL_SCRIPT_PATH/common/__zuul-exec-command-in-k8s.sh $1 zuul-merger "cat /etc/zuul/zuul.conf" | tee $1.zuul.conf

