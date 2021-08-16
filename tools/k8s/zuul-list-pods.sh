#!/bin/bash

# Arguments
# 
# @ zuul_id
#

set -xeu

zuul_id=$1

kubectl --kubeconfig /ephemeral/zuul/k8s-deployment/kube/${zuul_id}-config get pods
