#!/bin/bash

remove_danger_vars() {
    must_have_file "${result_env_file}"
    ###This list (should|could) be extended in future
    danger_vars=(
        PATH
        TMPDIR
        TEMP
        JAVA_HOME
        TMP
        GUESTFISH
        QT_PLUGIN_PATH
        XDG_
        MAIL
        KDEDIRS
        LESSOPEN
    )
    for i in "${danger_vars[@]}"; do run sed -i "/${i}=/d" "${result_env_file}"; done
}


result_env_file="/var/fpwork/ca_5gcv/result.env"
origin_env="/var/fpwork/ca_5gcv/origin.env"
new_env="/var/fpwork/ca_5gcv/new.env"
printenv > "${new_env}"
grep -Fxvf "${origin_env}" "${new_env}" > "${result_env_file}"

docker login mnp5gcb-docker-repo-local.esisoj70.emea.nsn-net.net --username 5gcvci --password AKCp5Z2hdAG6j8reEXRedwmbkFmFdaihpaHx1vhJKDS9DVrYt1XBt6NXaubyFn5LMxVtSQsBz
DOCKER_IMAGE='mnp5gcb-docker-repo-local.esisoj70.emea.nsn-net.net/5g/cbbuild:3.2.1'
docker pull "${DOCKER_IMAGE}"

   VOLUMES="-v /sys/fs/cgroup:/sys/fs/cgroup:ro \
             -v /boot:/boot:ro \
             -v /lib/modules:/lib/modules:ro \
             -v /var/fpwork/ca_5gcv:/ephemeral:rw"

    if [[ -n "${SSH_AUTH_SOCK}" ]]; then
        VOLUMES+=" -v ${SSH_AUTH_SOCK}:/ssh-agent"
    fi

    NPROC="$(expr "$(nproc)" - 3)"
    CONTAINER_ID="$(docker run -id --privileged \
                 --network host \
                 --cpuset-cpus="0-${NPROC}" \
                 ${VOLUMES} \
                 --env-file="${result_env_file}" \
                 --env SSH_AUTH_SOCK=/ssh-agent \
                 "${DOCKER_IMAGE}")"


docker exec -u "${UID}" "${CONTAINER_ID}" /bin/bash -c "npm cache clean"
docker exec -u "${UID}" "${CONTAINER_ID}" /bin/bash -c "sudo chown -R ca_5gcv:root ~/.*"

rm -f "${WORKSPACE}/docker.prop"
{
    for i in CONTAINER_ID; do
        echo "$i=${!i}"
    done
} >> "${WORKSPACE}/docker.prop"
