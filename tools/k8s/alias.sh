#!/bin

export ZUUL_SCRIPT_PATH='/ephemeral/zuul/scripts/'
export ZUUL_SCRIPT_HOME='/ephemeral/zuul/k8s-deployment'

# Login
alias zuul-login="/ephemeral/zuul/scripts/zuul-login.sh"
alias zuul-login-nks="/ephemeral/zuul/scripts/zuul-login-nks.sh"

# List all pods
alias zuul-list-pods="/ephemeral/zuul/scripts/zuul-list-pods.sh"

# Restart container and process
alias zuul-restart="/ephemeral/zuul/scripts/zuul-restart.sh"
