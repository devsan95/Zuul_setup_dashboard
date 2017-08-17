#! /bin/bash


zuul_image_tag="v2.2"
public_ip=$(curl -s --connect-timeout 5 http://169.254.169.254/latest/meta-data/public-ipv4 )
zuulweb_port=""

error (){
  echo "Error: $1"
  exit 2
}

usage()
{
  cat <<EOF

Usage: zuul_backup.sh  [-p <port>] [-h] [-d]

Options:
        -p <port>, specific the host port which zuul webpage is running, if no -p provided, default to 80
        -h show the usage for this script
EOF
  exit 0
}

optionp=""
optionparg=""

while getopts hp: option
do
  case $option in
  p) optionp="true"
     optionparg=$OPTARG;;
  h) optionh="true";;
  ?) error "illegal option specified, check zuul_backup.sh -h";;
  esac
done

[ -n "$optionh" ] &&  usage
if [ -n "$optionp" ];then
   zuulweb_port=$optionparg
else 
  zuulweb_port="80"
fi

wupiao(){
# [w]ait [u]ntil [p]ort [i]s [a]ctually [o]pen \n",
  timeout=9
  counter=1
  until curl -o /dev/null -sIf http://localhost:$zuulweb_port; do 
    if [ $counter -gt $timeout ];then
      echo "$counter times attempt failed"
      exit 1
    fi
    sleep 1 
    echo "The $counter attempt ..."
    let counter=counter+1
  done;

}

check_return_value (){
  if [ $1 -eq 0 ];then
    if [ "$__colormap" == "true" ];then
       echo -e "\033[32m[PASSED] $2\033[0m"
    else
       echo -e "[PASSED] $2"
    fi
  else
    if [ "$__colormap" == "true" ];then
      echo -e "\033[31m[FAILED] $3\033[0m"
    else
      echo -e "[FAILED] $3"
    fi
    exit 2
  fi
}


system_check() {
  if [ "$(whoami)" == "root" ];then
    if [ -n "$(cat /etc/system-release|grep "Red Hat"|grep "7")"  ];then
       echo "Current OS is $(cat /etc/system-release)"
       echo "match the Requirement, continue..."
    else 
       echo "Current OS does not match the docker installation, please choose Red Hat 7.2 or newer"
    fi
  else 
    echo "Please change user root to configure the environment"
    exit 2
  fi 
}

docker_check() {
  if [ -n "$(rpm -qa|grep docker)" ];then
     echo "Docker is installed, version: $(docker --version)"
       if [ -z "$(systemctl status docker|grep running)" ];then
          systemctl start docker
       else 
          echo "Docker is running ..."
       fi
  else
     echo "Can not find Docker installed, Now we are starting to install docker ..."
     cat << EOF > /etc/yum.repos.d/docker.repo
[dockerrepo]
name=Docker Repository
baseurl=https://yum.dockerproject.org/repo/main/centos/7
enabled=1
gpgcheck=1
gpgkey=https://yum.dockerproject.org/gpg
EOF
     yum install -y docker-engine-17.05.0.ce 
     check_return_value "$?" "Docker install successfully" "Docker install failed" 
     systemctl start docker
     check_return_value "$?" "Docker is running ..." "Docker run failed"
  fi
  echo "checking Docker configration ..."
  if [ -z "$(systemctl status docker|grep insecure-registry)" ];then
    cat  <<  EOF > /etc/sysconfig/docker
# /etc/sysconfig/docker
#
# Other arguments to pass to the docker daemon process
# These will be parsed by the sysv initscript and appended
# to the arguments list passed to docker daemon


other_args="-g /ephemeral/sysdocker  --insecure-registry archive.docker-registry.eecloud.nsn-net.net:5000 --insecure-registry  hzdocker.dynamic.nsn-net.net:5000"
HTTP_PROXY=http://10.158.100.1:8080
HTTPS_PROXY=http://10.158.100.1:8080
NO_PROXY=localhost,127.0.0.0/8,nsn-net.net

EOF
    sed -i 's#\[Service\]#\[Service\]\nEnvironmentFile=/etc/sysconfig/docker#g' /usr/lib/systemd/system/docker.service
    sed -i 's#/usr/bin/dockerd#/usr/bin/dockerd  $other_args#g' /usr/lib/systemd/system/docker.service
    systemctl daemon-reload
    service docker restart
    check_return_value "$?" "Docker reconfig done!" "Docker reconfig Failed"
  else 
    echo "Docker configuration is OK for us!"
  fi
}

tools_check(){
  if [ -n "$(git --version)" ];then
     echo "git is already installed : $(git --version)" 
  else 
     echo "git not found, start to install git ..."
     yum install git -y 
     check_return_value "$?" "Git installed successfully: $(git --version)" "Git installed failed"
  fi
  if [ -n "$(rpm -qa|grep java-1.8.0-openjdk)" ];then
     echo "Java 1.8 version installed : $(rpm -qa|grep "java-1.8.0-openjdk"|grep -v "headless")"
  else 
     echo "Java 1.8 version not found, start to install java 1.8"
     yum install -y java-1.8.0-openjdk
     check_return_value "$?" "Java 1.8 installed successfully: $(rpm -qa|grep "java-1.8.0-openjdk"|grep -v "headless")" "Java 1.8 installed failed"
  fi
}

add_publickey(){
  [ -f  "/root/.ssh/authorized_keys" ] || touch /root/.ssh/authorized_keys && chmod 400 /root/.ssh/authorized_keys
  if [ -n "$(cat /root/.ssh/authorized_keys|grep "beling01.china.nsn-net.net")" ];then
    echo "Public Key already added ..."
  else 
    cat << EOF  >> /root/.ssh/authorized_keys
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDD4jED4i6I3TIAs2RcnoGKCYbKYPLkyL7pbb9B8Cw2QqNUizjGWg9UmeyxAFBc/s6Z6Qba+qJGH+ptb5eRRrOqKOk34fBQ4cUfIlf4QXKA0OSdLyTmPJCRBeadPUtOPyZhR1bAnmM6UoYLLUjMgClt9FxU9I/tIUdzGN3nd2PhbZquXgXwXNTYlu/vI2ChW1d7cV0N7bST0pUW+c+bUIpcR0u1HEKHCAkpoWtk5kztg6QO3mPmAOAUJYD8JF7eGl+LKv2h+lhC8cBf/AQBPk7+9GpwQ8C4+MEsM0fNZ7z3vq0ZRQwWpHegcd9qt89eWMm3eFcnU5XkM0Fjd9keFx8r 000731731366@eucalyptus.key4bbsweetadm26
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAgEAxaOtCzbQvsRlCi9EcRMoxd8OiyIQuhjjT4rKUtQpWzZ8GN++tJBvx7IFwQsWJGaLM3THmOEud83cY0FMIojXlGCKiWazmF5axOstmyubuTgk0TZqPpwK2q/JtP45E8a9TTz6GXHO0oTOpX3aB+uvthCwZXbJVO8KxeVhBTTv6ZUICVvy84UZD1bmCLt1QvHgvJbdP5uy0QKDCPLMKjpoZghIheFz8Kf1iYzpuX2EK4lpSKrmHusftbs7AQhpQMxFL2LZc/L3kf0FOe5e6w9wzutVR5oPW1ZBf2ezwcXFJhPcJ9aMW9vaKFIb7pnAsKXFARNxVGcLz7dOnjgoYuQ0dyZDWEEDgeWNr2muhO69ScTBZeOJ81b8XqiOT75G9wxxYaAyrm+u3EBU8aNuJFLoGl7ZsvlndI+2muVGciTz9hg14tIAx+CR7fygjG8qLiuwWMD0YqrWme1UQ3OGP2EQVaWzJZ2eAXt4hO/X/opV39G7GUvZk0X3y+o5KXmz4SgJs1zph2Sygn76JY1ookwLvmd1cVOlapCGcnkXVMyJhwKZym3HkG74ebrKNiGlXP9+GBSnR1Dwrg+0p7Buh/GMqyy3j6vHUYHRcZDyKjJJsnxUD/mD6QGJoP/kYqMy6/H289YZusFqk6aLXku57llpK9tHrfpReLp7QFwXzUX4h68= mfourtic@frmrssucc039
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAy5/2GHz9jQvscDAlNOMvqIrLI3IgBNep+TIRwQemcC2THxYviy1KXtvukwqUHq/68RsvwlXh2lDRLQ24aidMVon3Oi/oDpdtQi6bS+meH1gn3UwFIF+YgJGH4OWVOYaeIHMr+kqriDhlWBULvsH9faZ8bv/+YRZpvGsD3odWL+rTptzE8A92NEUtBuH32axPQ/qkej5Rzsa5co86vYx7fdGtACaC+cORhlOJ5BgIuHRI8O0lh3uQihj0xGmtO78teHqqPUvl7RQsyeURyvqPOontj2fNg0sEV7o3fl/sY4qvOmPxWncyqxMNsGUvJ07X5CUF4wwgDVg5D5XrewW/sQ== jtong@hzling20.china.nsn-net.net
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAuILfM+xelw9joDYPNIAwz8uBaIbzh3FKQYajYnMyiXDa/lZUZioQ8eSzHgUTK06t4Q3mhh+eODs2DhvINCjh2fXcPzKAfqz8WaqMJG1orIKAGrgZ4awGuo8qFsfbUe3iY+1e3Xh8j4RJ3xXnoiInIEFAC3Jx34l7Tngd1P8r/ihU5Yf0/oX3WvEk+sMFTvNOmVryGnYHohotJ9GSnLd3BZ6QOjsGNSPW9UsLkhi7AvwlSKu3lxUdwRfhQ8JRNy0IW+49D7RxRPxoMmwGT6Bqoc1SB2Wq9OSN3ofae8Qh7u3VeRmyeUSq1HwGjtw/u4E84t8r+Qr5jOg0hlyTXRJ5QQ== root@beling01.china.nsn-net.net
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCjXtPg0z9S0E5DeNgefkFzCcEM3S/0OaEzgGpH7j33xx1/By5Jjjbt8mMZhg1n+LP5tWK6XgJwa9A6CNoFcWyNphXLvXZAHAxuyQOyUIn9SyyMltihxZkJPVEHNeMf7fHYMtKf6nnV35sRRxOpkC0+3jYf/pvVh04MQagFikc5n1lW01V0ydOWyaKEzEADVQwqvS+ediDuPLgNHyh9x6wuhCuM/oR5jl/FQsCZZpZDTrh2k4DCRIJDe3qLJd8LHNZbuRDn9aijUQtmajpMfRk5KmmmNG7NUY2K2jUj3vROQ9vE6VjPeE7ILmVdJIOYes43N+M3BsAozjbiMLW5So+r isabelle.pacault@alcatel-lucent.com
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA7CqD3gyjKxSQj1IxebnxT/xpLnsKwxiFcB0b6Lar75iFapSnU8WeWnnxMYqH1imedTVud0PljScjtTniFTzQD+kUkYYI8FNGalO2P1GwjaUq5mRoZkjG8vHRw/YGUmm+J2j4h2+kzhGmCNn+wN41zN5qeLF8TYQDfgWfYDOk5OqNRs9zDiNxKBs38DengzugumeXSwXoY7ew9dnrksZVUUc+QhCp/july7VJHVlhMtwT5IFdZ14pKNbIkfxsTHQEewgrcSJJi6PPvDbXXRfWo9/P8gikBP6j579y2468ar049Exl/66o9Np8oEt4L0ay8KDf0oYcmLVIeq4f6a8nOQ== mfourtic@euca-10-254-3-67 key for user mfourtic on esling135
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAs/VRKFeZjiuI0g0COzXnNYh+HCqKVY/SSIzOABGrRP0sfLRfqaQ1a+3zP5C6GpDtp8MFdwlnU4sNbg5yciaGzKE7cVLiIGvDfPOdoHtLbaATGWBaLRNamlM8nUIGm73jLghn3THB/ff0mPCZifddRjP4CFLTxuzzLjQgB+vmg+HmBBonnc/C7Qnoa1rJSOtz+Qv/hqjCmLpCdXUaCiJod0iEwnYJSjF2stC2WvfLxTIZjrVa1UQhNN3PANlpSRTCbkRVo/Fu+EHxBTv3SPxl3YWMRxkVcsOUB0Z85q76rIqWm7jUazV7lAIlxTz1Nus0d3oOc5ZtRsobyCBlnRLu1Q== jidan@hzling30.china.nsn-net.net
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDjyRJckqy6HA2RozCE29cnVWJrVS+Gw05dUG2MoG4owplVBh4LhQxoZ3JrXY4pUoo934s3dl0UQQDUQA2xN1z79NjH11PePS2FQEAPwhROD6FR/32VLK4tVzDbH9WwWxadnUdcrr9hy1cq720sJ1DIJrP7irrPuM3/d8nZO1dG6YD3jaPfvC23EzUpiipxCo1OLmfxz4n/UMMljoeHub6C4ICiu6YK4ynN1Gdyp6F/tjA5mGNbxffW1mcclTRryRzA/R30VeykL8uUQ8nlK5DMT6/MJtuotfHh32v9gyHwUoz060BjVV39QMnqX+9uHM7eo7QSidEhXbWyoBaJWzzP imported-openssh-key
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA53qpWuRxDpmL+VprDwtvbiWFJo7Y03FFbGbY2BPM2/QTwso7yUEtBDtdwcISRWgf1bQR3bG+DCe0NwYnS/uRC5HGYsS1YwbCNYEVJgAwa81ONgXC3VnnH2xPGzeit6r5aNKakg9Kf9SPZ4m4ldOD1HcsToIPavmVKURf5E72IQ+yBTExLelAKT3X4Xiwwdx6IGjInlhNReMdXd2616+G4d9LkC/XP93T8ZfCHLotoLqpTUSuPANUU3UpUodoM4wmaTz3fpZAfgHBY8JxCqpOh2pU4EcjPDfWIZeKNaCX09+D7XdnrU5jAQcBha+zcAByKRF4KEA2FomDVIdMKt16vw== y75zhang@hzlinb06.china.nsn-net.net
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEApf1jI6A4JmBW460FVCoiHvCropWWpo9KfcObffGOBoYg3Rq1V2sO4YgHMJJsom05zmMGbTtuNOyGFPPpnTExts9jdROQPquwOKv5KKRZyQPSBcKIi/V5ArtUQYh6x4mKtqvXo9XnXwTgWpCD2TnS+dRWF4Ff5+75vuyWeuUEyDgN5gtOjNBkWgPlKUwjNKLfK8007eZVEo2A/QHXDVDHD3uHhC8uBx6ZtMSdY0iZIWDEuNX5sGayfsp2hr3F6qn9KYSLcmyjRMj+VHSltWds9amODm5PS0VmiUK7L9ZTHB7F0Vp6Hqal1z4IyOxTEcn730hwALjjANLLg++5n0QH8w== ca_5g_hz_scm@hzlinb04.china.nsn-net.net
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC/FTM64qI8aR9+I5mgUuzKnRH8nG2LiUj/Yvarg8E20ZgwxTdGqBFhDNxVktKTmi5vS2qq5hXbdXKu1p/2b1805XAyAdElFRWJkY3o5nO8hetSWIcictxQV1Roe+TKibddqm1aDfn3YxVTAehF8Km0xDW+FaoPxg93gZBZwMKRFt9gYS2ejo9xBo+ghEYELFy/eMNAlJP6cHD2CoFjHrEbEc492wxtmRx/Dw0Bg5BQHe8V+ijqJNkJthRhXAWcjiEUVOYEyJ4IPR1FVQs5H6I4PtYqw3uw2iKtlCNnbcor+v+tB7qRER+I6rZ+Y9WBQ/Q5tQe/ZGb+ILCaCMZ/TCij jenkins@85d05befdc60
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC9mWIxe30J5cz0rkAHrzYO0GnmLwt4R5LHLX0R5IDbC5b/Labwwk+qhbdrg0SV8IhZqf7y6M3S8zJJNXcWakkgz3MMlR5LO9zQXM2yFEfUu832rO7OsZaz005LSYWbofUwJiGkz/0oKUQMnjXZsPz2LUMKyIQAp+ZetXGlkvOQhBP56uhCpaL5Wn5fq/NOctIGCWYUPdtlP1LDRFKUMzfZ3Mb/QTUQAvzmnKrW3cnQOul6JMEr0goFYada+cmsGCuDzLCFmByL8JAn1u1I3c3QJIEkKTUSxkUjMuxpE0jjqjAHvW3p0TQP69BOa4ffhu4u+gsncoA8nUXxdTQLcxU3 jenkins@38c2e5e04d29
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCzpNoJ8XQxjqg297Na9ntJ4SkZjblu+oZ9ZPdMd0syOx3DkfRApxl156sy2jbuwQH6t8mZ8fSNJmmytQbvL3WuB/YEnyB0FEmVs6OXHGw5qBYzoNh5bjRJWYjf1r/Yq8ygbJyRAoMtO1LME187QIV/M6PHiz1H92VxOgP1DZQidiGaY30RbiwOOejGkoq440OVX778uYot+RS/9gvV6M7XKxrWfNf39GRE5HEGScjru6F/GOgO3yTfQODJxhr6aWarSXDX+r1G9raRR8f99Sau0X4UIkdn+4hWII6kWBThkPM4aC1V7CGs8KbU0BXZxvlc4+58abgVGBK+WRFPMRFl dongsheng.xuan@nokia.com
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA6bKPacnS6IY9gdZZojj4MRZ68zAiRDMZBjjRYj2GdVeofqdQCZ8N+QUoysX8Y2fo1QiHqGhX5cyylEZjFfN+XqBPFBb+FupXjeus6OdY2TerJFJYgmQwbvTkIow3XOE2DM/xOUIfcdzhU0umm9TfzC6SDv7uZoPbyrS66xG0fOqEg66DU4+JKZkDKcICb1qE9yrjTLxw4qHrdeWxw/yfiSM+E0kjJHwaArXtmG7d5/IZRGsR4/Q8Mfa63NUQ9y6w4pHH6f6p71P9a3I3pIzM5ebLYvA00ILzmq4vF4krlwea2u4lenBs2MMBcMJ0lxYi1IRKuKQIJ24kLAQySGcyXw== kpei@hzling30.china.nsn-net.net

EOF
  fi
  check_return_value "$?" "Publickey added to the authorized_keys, please check in root ssh config" "Pubkey add to the authorized_keys failed"
}

get_dockerimage(){
  docker pull archive.docker-registry.eecloud.nsn-net.net/5gci/zuul-server:${zuul_image_tag}
  check_return_value "$?" "zuul image pulled succesfully" "zuul image pulled failed"
}

run_container(){
  docker stop zuul-server && docker rm zuul-server 
  docker run -itd --privileged -p  $zuulweb_port:80 -p 4730:4730 --name zuul-server archive.docker-registry.eecloud.nsn-net.net/5gci/zuul-server:${zuul_image_tag}
  check_return_value "$?" "zuul container run successfully" "zuul container run failed"
  echo "Checking the service in webpage is ready or not, now checking in port $zuulweb_port ..." 
  wupiao
  check_return_value "$?" "zuul webpage is ready " "zuul webpage checking  timeout..."
}

update_zuul_source(){
  echo "pulling latest mn_script ..."
  docker exec zuul-server bash -c "cd /root/mn_scripts/;git pull" 
  check_return_value "$?" "mn_script updated successfully" "mn_script updated failed"
  echo "updating zuul source code in container ..."
  docker exec zuul-server "/root/mn_scripts/tools/update_zuul.sh" 
  check_return_value "$?" "zuul source code update successfully" "zuul source code update failed"
}

update_zuul_conf(){
  echo "updating zuul conf in container ..."
  docker exec zuul-server "/root/mn_scripts/tools/update_zuul_config.sh" 
  check_return_value "$?" "zuul conf update successfully" "zuul conf update failed"
}

update_zuul_layout(){
  echo "updating zuul layout yaml ..."
  docker exec zuul-server "/root/mn_scripts/tools/update_zuul_layout.sh" 
  check_return_value "$?" "zuul layout update successfully" "zuul layout update failed"
}

echo ---------------------------------
echo "[Step 1 : checking the system]"
system_check
echo -e '\n'
echo "[Step 2 : checking the Docker]"
docker_check
echo -e '\n'
echo "[Step 3 : needed tools check]"
tools_check
echo -e '\n'
echo "[Step 4 : Add the needed publickey]"
add_publickey
echo -e '\n'
echo "[Step 5 : Get zuul docker images]"
get_dockerimage
echo -e '\n'
echo "[Step 6 : Run zuul containers]"
run_container
echo -e '\n'
echo "[Step 7 : Update zuul source codes in container]"
update_zuul_source
echo -e '\n'
echo "[Step 8 : Update zuul conf in container]"
echo -e '\n'
echo "[Step 9 : Update layout yaml]"
update_zuul_layout
echo -e '\n'
echo "[ALL things are ready, Please check in the Zuul web page]: $public_ip:$zuulweb_port"
echo ---------------------------------

