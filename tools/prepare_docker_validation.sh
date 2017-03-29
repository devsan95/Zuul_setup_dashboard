#!/usr/bin/env bash
# prepare env
export GIT_SSL_NO_VERIFY=true
SCRIPT_DIR="`dirname \"${BASH_SOURCE[0]}\"`"
SCRIPT_DIR="`( cd \"$SCRIPT_DIR/..\" && pwd )`"  # absolutized and normalized
if [ -z "$SCRIPT_DIR" ] ; then
  # error; for some reason, the path is not accessible
  # to the script (e.g. permissions re-evaled after suid)
  echo "Can't find CIHOME Path"
  exit 1  # fail
fi
script_pwd=update_zuul_layout
work_path=/tmp/zuul_tmp/${script_pwd}/
mkdir -p /tmp/zuul_tmp/${script_pwd}/
rm -rf /tmp/zuul_tmp/${script_pwd}/*
OLD_PATH="`pwd`"
cd ${work_path}
git clone http://gerrit.app.alcatel-lucent.com/gerrit/MN/SCMTA/zuul/layout

# update conf
${SCRIPT_DIR}/tools/update_zuul_qa_config.sh
sed -i 's#zuul.zuulqa.dynamic.nsn-net.net#zuul-docker.zuulqa2.dynamic.nsn-net.net#g' /etc/zuul/zuul.conf

#update layout
cat <<EOF > ${work_path}/layout/layout.d/docker_test.yaml
projects:
  - name: qa_dummy_job_docker
    check:
      - qa_download_patch_set
    gate:
      - qa_always_succeed
    post:
      - qa_always_succeed
EOF

. ${SCRIPT_DIR}/pyenv.sh
python ${SCRIPT_DIR}/layout/layout_handler.py -i "${work_path}/layout/layout.yaml" \
 -z "/etc/zuul/zuul.conf" merge -o "/etc/zuul/layout.yaml"

#restart service
supervisorctl restart zuul-launcher
supervisorctl restart zuul-merger
supervisorctl restart zuul-server