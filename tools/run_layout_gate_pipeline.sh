#!/usr/bin/env bash
export GIT_SSL_NO_VERIFY=true
SCRIPT_DIR="`dirname \"${BASH_SOURCE[0]}\"`"
SCRIPT_DIR="`( cd \"$SCRIPT_DIR/..\" && pwd )`"  # absolutized and normalized
if [ -z "$$SCRIPT_DIR" ] ; then
  # error; for some reason, the path is not accessible
  # to the script (e.g. permissions re-evaled after suid)
  echo "Can't find CIHOME Path"
  exit 1  # fail
fi

${SCRIPT_DIR}/tools/update_zuul_config.sh
${SCRIPT_DIR}/tools/update_zuul.sh

. ${SCRIPT_DIR}/pyenv.sh
set -e
python ${SCRIPT_DIR}/layout/update_layout_with_patch_set.py $@
python ${SCRIPT_DIR}/pipeline/validate_pipeline.py