#! /bin/bash
OLD_PATH="`pwd`"

EECLOUD_PATH="/ephemeral"
LINSEE_PATH="/var/fpwork"
HOME_PATH="~"
VENV_PATH=""
unset PYTHONPATH

if [ -d "$EECLOUD_PATH" ] ;
then
  VENV_PATH="$EECLOUD_PATH"/5g_conda/
elif [  -d "$LINSEE_PATH" ] ;
then
  VENV_PATH="$LINSEE_PATH"/5g_conda/
else
  echo "Can't find path to init venv, use home"
  VENV_PATH="$HOME_PATH"/5g_conda/
fi

if [ ! -e "$VENV_PATH"/envs/python2/bin/activate ];
then
  if [ ! -d "$VENV_PATH" ] ;
  then
    mkdir -p "$VENV_PATH"
  fi

  wget https://repo.continuum.io/miniconda/Miniconda2-latest-Linux-x86_64.sh
  bash Miniconda2-latest-Linux-x86_64.sh -b -p "$VENV_PATH" -f
  rm -rf Miniconda2-latest-Linux-x86_64.sh

  cd "$VENV_PATH"/bin
  "$VENV_PATH"/bin/conda create --name python2 python=2.7 -y
fi

cd "$VENV_PATH"
source "$VENV_PATH"/bin/activate python2
python -m pip install gitpython arrow sh pyyaml
chmod -R 777 *

cd "$OLD_PATH"

echo "Python Virtualenv init finished. "
