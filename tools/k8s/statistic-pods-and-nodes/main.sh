for id in `cat id.txt`; do
    kubectl --kubeconfig /ephemeral/k8s-deployment/kube/%%-config get pods -o=custom-columns=NAME:.metadata.name,NODE:.spec.nodeName,STATUS:.status.phase > node.%%.txt
done

