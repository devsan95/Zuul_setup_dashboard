#!/bin/bash
set -e

# if interface_version is set, add ext_commit_msg parameter
if [[ -n "${interface_version}" ]];then
    bb_file=$(find ${WORKSPACE}/meta-5g -name "${interface_version/-/[-_]}.bb")
    if [[ -z "${bb_file}" ]];then
        echo "**** Not find bb_file for ${interface_version} ****"
        exit 2
    fi
    bb_file_no=$(echo ${bb_file} |wc -l)
    if [[ ${bb_file_no} -ne 1 ]];then
        echo "**** Find multi bb file for ${interface_version}  *****"
        echo "**** result: ${bb_file} ****"
        exit 2
    fi
    comp_name=${bb_file//_*/}
    if [[ -z "${comp_name}" ]];then
        echo "**** Not find comp_name from ${bb_file} ****"
        exit 2
    fi
    commit_id=$(grep '^REVISION = "' ${bb_file} |sed "s/ *= */=/g"|awk -F"=" '{print $2}'|sed 's/"//g')
    if [[ -z "${commit_id}" ]];then
        echo "**** Not find commit_id from ${bb_file} ****"
        exit 2
    fi
    ext_msg_param="""interface info:
        comp_name: ${comp_name}
        bb_version: ${interface_version}
        commit-ID: ${commit_id}"""
fi


cd ${WORKSPACE}/script
chmod 600 ${WORKSPACE}/gerritt_info/keys/scmtaci.rsa
source pyenv.sh
cd ../yaml

if [[ -z "${yaml}" ]] && [[ -z "${jira_key}" ]]; then
    echo "Manual mode"
    YAML_PATH="${WORKSPACE}/yaml/${structure_file}"
    TOPIC_PREFIX="${topic_prefix}"
    if [[ -z "${PROMOTED_USER_ID}" ]]; then
        BUILD_USER_ID="${BUILD_USER_ID:-anonymous}"
    else
        BUILD_USER_ID=${PROMOTED_USER_ID}
    fi
    FEATURE_OWNER="${BUILD_USER_ID}"
    ENV_CHANGE="${env_change}"
    IF_RESTORE="${restore_from_topic}"
    FORCE_FEATURE_ID="False"
else
    echo "GUI mode"
    python ${WORKSPACE}/script/integration/archive_feature_yaml.py --gerrit-info-path ${WORKSPACE}/gerritt_info/${gerrit_info} --yaml "${yaml}" --identity "${jira_key}" --project MN/SCMTA/zuul/comp-deps --branch master --schema-path "${WORKSPACE}/yaml/schema/schema.json" --dependent True --output-path "${WORKSPACE}/yaml.yaml"
    YAML_PATH="${WORKSPACE}/yaml.yaml"
    TOPIC_PREFIX="feature"
    FEATURE_ID="${jira_key}"
    IF_RESTORE="False"
    FORCE_FEATURE_ID="True"
fi

GERRIT_INFO="${WORKSPACE}/gerritt_info/${gerrit_info}"
ZUUL_USER="scmtaci"
ZUUL_KEY="${WORKSPACE}/gerritt_info/keys/scmtaci.rsa"
STREAMS="${streams}"

set -x
python ${WORKSPACE}/script/integration/create_integration_changes.py \
                       --yaml-path "${YAML_PATH}" \
                       --gerrit-path "${GERRIT_INFO}" \
                       --zuul-user "${ZUUL_USER}" \
                       --zuul-key "${ZUUL_KEY}" \
                       create-changes --topic-prefix "${TOPIC_PREFIX}" \
                                      --streams "${STREAMS}"  \
                                      --feature-id "${FEATURE_ID}" \
                                      --feature-owner "${FEATURE_OWNER}" \
                                      --if-restore "${IF_RESTORE}" \
                                      --integration-mode "${integration_mode}" \
                                      --base-load "${base_load}" \
                                      --env-change """${ENV_CHANGE}""" \
                                      --force-feature-id "${FORCE_FEATURE_ID}" \
                                      --open-jira True \
                                      --ext_commit_msg """${ext_msg_param}"""
