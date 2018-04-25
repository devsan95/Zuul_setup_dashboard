#!/bin/bash
#for docker container auto mount disk

SITE=$1

function NFSSWITCHER(){

mkdir -p /build/ltesdkroot /build/rcp /mnt/5GCV_storage

if [[ ! -n "$SITE" ]];then
	echo "AUTO SITE SETTING......"
	hzchon=`ping -c 1 hzchon11.china.nsn-net.net | awk 'NR==2{print $8}'`
	eslinn=`ping -c 1 eslinn11.emea.nsn-net.net | awk 'NR==2{print $8}'`
	HGH=${hzchon#*=}
	ESL=${eslinn#*=}
	if [[ -z "$HGH" && -z "$ESL" ]];then
		echo "servers error!"
	elif [[ -z "$HGH" && -n "$ESL" ]];then
		mount -t nfs -o rw eslinn11.emea.nsn-net.net:/vol/eslinn11_ltesdk/build/build/ltesdkroot /build/ltesdkroot
		mount -t nfs -o rw eslinn10.emea.nsn-net.net:/vol/eslinn10_ltesdkrcp_bin/rcp /build/rcp
		mount -t nfs -o rw 5gcbnfs.dynamic.nsn-net.net:/ephemeral/NFS /mnt/5GCV_storage
	elif [[ -n "$HGH" && -z "$ESL" ]];then
		mount -t nfs -o rw hzchon11.china.nsn-net.net:/vol/hzchon11_ltesdk/ltesdkroot/ltesdkroot /build/ltesdkroot
		mount -t nfs -o rw hzchon10.china.nsn-net.net:/vol/hzchon10_ltesdkrcp_bin /build/rcp
		mount -t nfs -o rw centralizednfs.dynamic.nsn-net.net:/ephemeral/NFS /mnt/5GCV_storage
	elif [[ -n "$HGH" && -n "$ESL" ]];then
		HE=`echo "scale=3; $HGH-$ESL" | bc`
		if [[ $(echo "$HE > 0"|bc) = 1 ]];then
			echo "espoo is closer"
			mount -t nfs -o rw eslinn11.emea.nsn-net.net:/vol/eslinn11_ltesdk/build/build/ltesdkroot /build/ltesdkroot
			mount -t nfs -o rw eslinn10.emea.nsn-net.net:/vol/eslinn10_ltesdkrcp_bin/rcp /build/rcp
			mount -t nfs -o rw 5gcbnfs.dynamic.nsn-net.net:/ephemeral/NFS /mnt/5GCV_storage
			echo "espoo servers mounting done!"
		elif [[ $(echo "$HE < 0"|bc) = 1 ]];then
			echo "hz is closer"
			mount -t nfs -o rw hzchon11.china.nsn-net.net:/vol/hzchon11_ltesdk/ltesdkroot/ltesdkroot /build/ltesdkroot
			mount -t nfs -o rw hzchon10.china.nsn-net.net:/vol/hzchon10_ltesdkrcp_bin /build/rcp
			mount -t nfs -o rw centralizednfs.dynamic.nsn-net.net:/ephemeral/NFS /mnt/5GCV_storage
			echo "hz servers mounting done!"
		fi
	fi
#	echo "Please add SITE parameter......"
elif [[ "$SITE" = "hz" ]];then
	echo "hz be chosen"
	mount -t nfs -o rw hzchon11.china.nsn-net.net:/vol/hzchon11_ltesdk/ltesdkroot/ltesdkroot /build/ltesdkroot
	mount -t nfs -o rw hzchon10.china.nsn-net.net:/vol/hzchon10_ltesdkrcp_bin /build/rcp
	mount -t nfs -o rw centralizednfs.dynamic.nsn-net.net:/ephemeral/NFS /mnt/5GCV_storage
	echo "hz servers mounting done!"
elif [[ "$SITE" = "espoo" ]];then
	echo "espoo be chosen"
	mount -t nfs -o rw eslinn11.emea.nsn-net.net:/vol/eslinn11_ltesdk/build/build/ltesdkroot /build/ltesdkroot
	mount -t nfs -o rw eslinn10.emea.nsn-net.net:/vol/eslinn10_ltesdkrcp_bin/rcp /build/rcp
	mount -t nfs -o rw 5gcbnfs.dynamic.nsn-net.net:/ephemeral/NFS /mnt/5GCV_storage
	echo "espoo servers mounting done!"
else
	echo "Wrong SITE......"
fi
}

NFSSWITCHER
