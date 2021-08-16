#!/bin/bash


set -xeu

POD_NAME=$(kubectl --kubeconfig /ephemeral/zuul/k8s-deployment-nks/kube/$1-config -n $1-zuul get pods | grep $2 | awk '{print $1}' | xargs echo -n)
kubectl --kubeconfig /ephemeral/zuul/k8s-deployment-nks/kube/$1-config -n $1-zuul exec -it $POD_NAME -c $2 -- bash
