#! /bin/bash

run() {
    # It's nice to be able to print some commands without
    # enabling XTRACE for all the things.
    echo "Executing: $*"
    "$@"
}

run_try_n() {
    # arguments: <tries> <delay> <command words>
    # try at most <tries> times to execute a command
    # with the delay of <secs> seconds between tries
    if [[ $# -lt 3 ]]; then
        die "${FUNCNAME}: missing parameters"
    fi

    local tries="$1"
    shift
    local delay="$1"
    shift

    if [[ ${tries} -lt 1 ]]; then
        die "${FUNCNAME}: tries ${tries} is invalid"
    fi

    local i=1
    while true; do
        if run "$@"; then
            break
        fi

        if [[ "${i}" -ge "${tries}" ]]; then
            ewarn "command failed, no more tries left"
            return 1
        else
            ewarn "command failed, trying again (current try: ${i})"
            run sleep "${delay}"
            ((i++))
        fi
    done
}


# Determine the directory containing this script
if [[ -n $BASH_VERSION ]]; then
    _SCRIPT_LOCATION=${BASH_SOURCE[0]}
    _SHELL="bash"
elif [[ -n $ZSH_VERSION ]]; then
    _SCRIPT_LOCATION=${funcstack[1]}
    _SHELL="zsh"
else
    echo "Only bash and zsh are supported"
    exit 1
fi

# Ensure that this script is sourced, not executed
# Also note that errors are ignored as `activate foo` doesn't generate a bad
# value for $0 which would cause errors.
if [[ -n $BASH_VERSION ]] && [[ "$(basename "$0" 2> /dev/null)" == "pyenv.sh" ]]; then
    (>&2 echo "Error: activate must be sourced. Run 'source pyenv.sh'
instead of 'pyenv.sh'.
")
    exit 1
fi

OLD_PATH="`pwd`"
CIHOME_PATH="`dirname \"${BASH_SOURCE[0]}\"`"
CIHOME_PATH="`( cd \"$CIHOME_PATH\" && pwd )`"  # absolutized and normalized
if [ -z "$CIHOME_PATH" ] ; then
  # error; for some reason, the path is not accessible
  # to the script (e.g. permissions re-evaled after suid)
  echo "Can't find CIHOME Path"
  exit 1  # fail
fi

EECLOUD_PATH="/ephemeral"
LINSEE_PATH="/var/fpwork"
VAR_PATH="/var"
HOME_PATH=~
VENV_PATH=""
CHECK_PATH=""
unset PYTHONPATH
export no_proxy=nokia.com,alcatel-lucent.com,nsn-net.net,$no_proxy

function check_and_make(){
    if [ -d "$VENV_PATH" ] && [ -w "$VENV_PATH" ] ;
    then
        :
    else
        if [ -d "$1" ] && [ -w "$1" ] ;
        then
            echo "Can't find path to init conda, use $1"
            CHECK_PATH="$1"/5g_conda/
            if [ -d "$CHECK_PATH" ] && [ -w "$CHECK_PATH" ] ;
            then
                 echo "$CHECK_PATH is ready for use"
                 VENV_PATH="$CHECK_PATH"
            else
                echo "$CHECK_PATH not exist. Try to make..."
                set +e
                mkdir -p "$CHECK_PATH"
                set -e
                if [ -d "$CHECK_PATH" ] && [ -w "$CHECK_PATH" ] ;
                then
                    echo "$CHECK_PATH is ready for use"
                    VENV_PATH="$CHECK_PATH"
                else
                    echo "$CHECK_PATH not exist or not writable"
                fi
            fi
        else
            :
        fi


    fi
}

check_and_make "$LINSEE_PATH"
check_and_make "$EECLOUD_PATH"
check_and_make "$VAR_PATH"
check_and_make "$HOME_PATH"

if [ -d "$VENV_PATH" ] && [ -w "$VENV_PATH" ] ;
then
    echo "Directory for conda is ready, checking..."
else
    echo "Directory for conda is not ready, abort"
    exit 1
fi

export http_proxy=http://10.158.100.1:8080
export https_proxy=https://10.158.100.1:8080

prepare_python_env(){
if [ ! -e "$VENV_PATH"/envs/python2/bin/python ];
then
  cd "$VENV_PATH"
  wget https://repo.continuum.io/miniconda/Miniconda2-latest-Linux-x86_64.sh
  bash Miniconda2-latest-Linux-x86_64.sh -b -p "$VENV_PATH" -f
  rm -rf Miniconda2-latest-Linux-x86_64.sh

  cd "$VENV_PATH"/bin
  "$VENV_PATH"/bin/conda update conda -y
  "$VENV_PATH"/bin/conda update --all -y
  "$VENV_PATH"/bin/conda install python=2.7 -y
  "$VENV_PATH"/bin/conda update python -y
  "$VENV_PATH"/bin/conda create --name python2 python=2.7 -y
  source "$VENV_PATH"/bin/activate python2
  conda install pycrypto mysql-connector-python -y
  conda install -c conda-forge yappi -y
  pip install --upgrade pip
  pip install git+http://gerrit.ext.net.nokia.com/gerrit/MN/SCMTA/zuul/zuul
  chmod -R 777 "$VENV_PATH"
fi

cd "$VENV_PATH"
source "$VENV_PATH"/bin/activate python2
conda install -y certifi

pip install --no-cache-dir \
    configobj \
    jenkins-job-builder \
    jenkinsapi \
    networkx \
    python-jenkins \
    PyZMQ \
    requests \
    ruamel.yaml<=0.15

pip install --no-cache-dir \
    beautifulsoup4 \
    paramiko

pip install --no-cache-dir \
    arrow \
    gitpython \
    ptpython \
    pydocstyle \
    pygerrit2 \
    pymysql==0.10.1 \
    python-slugify \
    pyyaml \
    sh

pip install --no-cache-dir \
    click \
    fire \
    jinja2 \
    jira \
    jsonschema \
    mysql-connector \
    pyrsistent==0.16.1 \
    python-gitlab \
    pytz \
    xlwt

pip uninstall -y \
    flake8 \
    pylint

pip install --no-cache-dir -U \
    flake8 \
    pylint

pip install --no-cache-dir -U \
    git+http://gerrit.ext.net.nokia.com/gerrit/MN/SCMTA/zuul/zuul

pip install --no-cache-dir -U \
    git+https://gerrite1.ext.net.nokia.com:443/scm_tools

export PYTHONPATH=${CIHOME_PATH}/CITOOLS:${CIHOME_PATH}:${PYTHONPATH}
cd "$OLD_PATH"
}

run_try_n 3 10 prepare_python_env
echo "Python Virtualenv init finished. "
