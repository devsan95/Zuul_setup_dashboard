#!/bin/bash -exu

##########################################################
# Restart zuul containers and process in containers      #
##########################################################

# Arguments
# 
# @ zuul_id
# 
# 1. trs
# 2. l1
# 3. oam
# 4. soc
# 5. ecp
# 6. hetran
# 7. bbp
# 
#  
# @ component
# 1. zuul-server
# 2. zuul-merger
# 3. zuul-gearman
# 4. mysql
#
# @type
# 1. process
# 2. container

zuul_id=$1
component=$2
type=$3

kubeconfig="/ephemeral/zuul/k8s-deployment/kube/${zuul_id}-config"
pod_name=$(kubectl --kubeconfig ${kubeconfig} get pods | grep ${component} | awk '{print $1}' |xargs echo -n)

if [ ${type} == "process" ];then  
    # go inside container and restart all process
    kubectl --kubeconfig ${kubeconfig} exec -it ${pod_name} supervisorctl restart all

else
    # Delete contaienr and will be brought back by k8s
    kubectl --kubeconfig ${kubeconfig} delete pod ${pod_name}
fi

