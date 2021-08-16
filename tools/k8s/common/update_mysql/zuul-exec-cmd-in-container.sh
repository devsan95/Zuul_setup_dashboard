#!/bin/bash


set -x


# $1 -> bu id
# $2 -> deployment name
# $3 -> bash command to execute

POD_NAME=$(kubectl --kubeconfig /ephemeral/zuul/k8s-deployment/kube/$1-config get pods | grep $2 | awk '{print $1}' | xargs echo -n)
kubectl --kubeconfig /ephemeral/zuul/k8s-deployment/kube/$1-config exec $POD_NAME -c $2 -- mysql -h localhost -u root -p5gzuul_pwd -e "use zuul;ALTER TABLE zuul_buildset ADD COLUMN datetime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP() AFTER message;"
