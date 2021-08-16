#!/bin/bash


set -xeu

POD_NAME=$(kubectl --kubeconfig /ephemeral/zuul/k8s-deployment/kube/$1-config get pods | grep $2 | awk '{print $1}' | xargs echo -n)
kubectl --kubeconfig /ephemeral/zuul/k8s-deployment/kube/$1-config exec -it $POD_NAME -c $2  bash
