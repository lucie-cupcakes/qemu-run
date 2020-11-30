#!/bin/bash
while true; do
smb_dir=$(ls /tmp | grep qemu-smb | head -n1)
if [ "$smb_dir" != "" ]; then
	smb_dir="/tmp/$smb_dir"	
	echo "[global]
		allow insecure wide links = yes
		[qemu]
		follow symlinks = yes
		wide links = yes
		acl allow execute always = yes" >> "$smb_dir/smb.conf"
	#smbcontrol --configfile=$conf $pid reload-config
	exit 0
fi
sleep 5s
done
