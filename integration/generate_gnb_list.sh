#!/bin/bash
set -x
rm -rf ${WORKSPACE}/gnb_list

comm -23 \
    <(grep -nr ${WORKSPACE}/meta-5g/recipes-components/ -e gnb \
    | awk -F ":" '{print $1}' \
    | xargs -n 1 basename \
    | awk -F "_" '{print $1}' \
    | sort -u) \
    <(grep -Pazo 'DEPENDS = "([^"]|\n)*"' ${WORKSPACE}/integration/meta-5g-cb/recipes-integration/integration-SidePackage/* \
    | grep -Ev '"' \
    | sed -r 's/-[0-9].*//g' \
    | sort -u) \
    > ${WORKSPACE}/gnb_list