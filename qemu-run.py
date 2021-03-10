#!/usr/bin/env python3
"""Copyright (C) 2020 Lucie Cupcakes <lucie_linux [at] protonmail.com>
This file is part of qemu-run <https://gitlab.com/lucie_cupcakes/pybd>.
qemu-run is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation; either version 3, or (at your option) any later
version.
qemu-run is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
for more details.
You should have received a copy of the GNU General Public License
along with qemu-run; see the file LICENSE.  If not see <http://www.gnu.org/licenses/>."""

# Shared folders: Needs smbd and gawk
import os,sys,errno,socket,subprocess,time,base64,uuid
from enum import Enum

# Mini error handling lib:
class InfoMsgType(Enum):
    im_error=0
    im_warning=1
    im_info=2

class InfoMsg:
    def __init__(self,msg_txt,msg_type=InfoMsgType.im_error):
        self.msg_txt=msg_txt
        self.msg_type=msg_type

class ReturnCode:
    def __init__(self,ok=True,msg=None): #op_success=Boolean,infomsg=InfoMsg class.
        self.ok=ok
        self.msgs=[]
        if msg!=None:
            self.msgs.append(msg)
    def set_error(self,err_msg):
        self.ok=False
        self.msgs.append(err_msg)

# My replacement for configobj,fuck that shit.
def load_cfg_process(res,lines):
    for line in lines:
        if line.find('=')!=-1:
            sline=line.split('=', 1)
            key=sline[0].strip()
            if key.find('#')==-1:
                value=sline[1].strip()
                res[key]=value
    return res

def load_cfg_from_file(fpath,defaults=None): # defaults must be a dictionary..
    res={}
    if defaults is not None:
        res=defaults.copy()
    with open(fpath,'r') as fh:
        res=load_cfg_process(res,fh.readlines())
    return res

def load_cfg_from_args(arg_cfg_str,defaults=None,delimiter=','):
    res={}
    if defaults is not None:
        res=defaults.copy()
    res=load_cfg_process(res,arg_cfg_str.split(delimiter))
    return res

def get_disk_format(file_path):
    out=subprocess.check_output(['qemu-img','info',file_path],universal_newlines=True).split()
    prev_was_fmt=False
    result=''
    for s in out:
        if prev_was_fmt:
            result=s
            break
        else:
            prev_was_fmt=s=='format:' 
    return result

def spawn_daemon(func,args=None):
    # do the UNIX double-fork magic,see Stevens' 'Advanced
    # Programming in the UNIX Environment' for details (ISBN 0201563177)
    try:
        pid=os.fork()
        if pid > 0:
            return
    except OSError as e:
        print('fork #1 failed: %d (%s)' % (e.errno,e.strerror),file=sys.stderr)
        sys.exit(1)
    os.setsid()
    try:
        pid=os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        print('fork #2 failed: %d (%s)' % (e.errno,e.strerror),file=sys.stderr)
        sys.exit(1)
    if args!=None:
        func(args)
    else:
        func()
    os._exit(os.EX_OK)

def get_usable_port():
    port=0
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.bind(('127.0.0.1',0))
    port=sock.getsockname()[1]
    sock.close()
    return port

def detect_if_cfg_is_in_args():
    res=False
    if len(sys.argv) >= 2:
        if sys.argv[1].find('--cfg=')!=-1:
            res=True
    return res
    
def check_if_file_exists_in_path(fname, resolve=False):
    env_path=os.environ['PATH'].split(':')
    for p in env_path:
        fpath='{}/{}'.format(p,fname)
        if os.path.isfile(fpath):
          return fpath if resolve else True  
    return '' if resolve else False

def program_find_vm_location():
    # return values=
    rc=ReturnCode()
    vm_name=''
    vm_dir=''
    # Use environment variable to find where the VM is
    if len(sys.argv)==1: # No args.
        rc.set_error(InfoMsg('Warning: No arguments,assuming the VM is in CWD.',InfoMsgType.im_warning))
        vm_dir=os.getcwd()
    else:
        if detect_if_cfg_is_in_args()==True:
            vm_dir=os.getcwd()
            vm_name='QEMU-VM'
        else:
            # Normal lookup using ENV var
            try:
                vm_dir_env=os.environ['QEMURUN_VM_PATH'].split(':')
            except:
                rc.set_error(InfoMsg('Cannot find environment variable QEMURUN_VM_PATH.\nPython error \#%d (%s)' % (e.errno,e.strerror)))
            vm_name=sys.argv[1]
            for p in vm_dir_env:
                vm_dir='{}/{}'.format(p,vm_name)
                if os.path.exists(vm_dir):
                    break
            if not os.path.exists(vm_dir):
                rc.set_error(InfoMsg('Cannot find VM: {},Check your VM_PATH env. variable ?.'.format(vm_dir)))
    return rc,vm_name,vm_dir

def program_get_cfg_values(vm_dir):
    rc=ReturnCode()
    cfg={}
    cfg['*']=''
    cfg['sys']='x86_64'
    cfg['uefi']='no'
    cfg['cpu']='host'
    cfg['cores']=subprocess.check_output(['nproc']).decode(sys.stdout.encoding).strip()
    cfg['mem']='2G'
    cfg['acc']='yes'
    cfg['vga']='virtio'
    cfg['snd']='hda'
    cfg['boot']='c'
    cfg['fwd_ports']=''
    cfg['hdd_virtio']='yes'
    cfg['shared']='shared'
    cfg['net']='virtio-net-pci'
    cfg['rng_dev']='yes'
    cfg['host_video_acc']='no'
    cfg['localtime']='no'
    cfg['headless']='no'
    cfg['vnc_pwd']=''
    cfg['monitor_port']=5510
    cfg['floppy']='{}/floppy'.format(vm_dir) if os.path.isfile('{}/floppy'.format(vm_dir)) else 'No'
    cfg['cdrom']='{}/cdrom'.format(vm_dir) if os.path.isfile('{}/cdrom'.format(vm_dir)) else 'No'
    cfg['disk']='{}/disk'.format(vm_dir) if os.path.isfile('{}/disk'.format(vm_dir)) else 'No'
    if os.path.exists('{}/{}'.format(vm_dir,cfg['shared'])):
        cfg['shared']='{}/{}'.format(vm_dir,cfg['shared'])
    vm_cfg_file_path='{}/config'.format(vm_dir)
    if os.path.isfile(vm_cfg_file_path):
        cfg=load_cfg_from_file(vm_cfg_file_path,cfg)
    else:
        if detect_if_cfg_is_in_args()==True:
            arg_cfg_str=sys.argv[1].split('--cfg=')[1]
            rc.set_error(InfoMsg('Info: Using configuration from arguments.',InfoMsgType.im_info))
            if arg_cfg_str.strip()=='':
                rc.set_error(InfoMsg('Error: argument cfg is empty.'))
                return rc,None
            cfg=load_cfg_from_args(arg_cfg_str,cfg)
        else:
            rc.set_error(InfoMsg('Cannot find config file.'))
    return rc,cfg

def program_build_cmd_line(cfg,vm_name,vm_dir):
    rc=ReturnCode()
    drive_index=0
    telnet_port=0
    sf_str=''
    fwd_ports_str=''
    qemu_cmd=[]
    qemu_bin='qemu-system-{}'.format(cfg['sys'].lower())
    vm_is_x86=cfg['sys'].lower()=='x86_64' or cfg['sys'].lower()=='i386'
    if check_if_file_exists_in_path(qemu_bin): 
        qemu_cmd.append(qemu_bin)
    else:
        rc.set_error(InfoMsg('Invalid sys value.'))
    if cfg['acc'].lower()=='yes' and vm_is_x86:
        qemu_cmd.append('--enable-kvm')
    if vm_name!='':
        qemu_cmd+=['-name',vm_name]
    if cfg['uefi'].lower()=='yes':
        qemu_cmd+=['-L','/usr/share/qemu','-bios','OVMF.fd']
    if not (cfg['cpu'].lower()=='host' and vm_is_x86==False):
        qemu_cmd+=['-cpu',cfg['cpu']]
    qemu_cmd+=['-smp',cfg['cores'],
                '-m',cfg['mem'],
                '-boot','order=' + cfg['boot'],
                '-usb','-device','usb-tablet']
    if cfg['snd'].lower()!='no':
        qemu_cmd+=['-soundhw',cfg['snd']]
    qemu_cmd+=['-vga',cfg['vga']]
    if cfg['headless'].lower()=='yes':
        telnet_port=get_usable_port()
        qemu_cmd+=['-monitor','telnet:127.0.0.1:{},server,nowait'.format(telnet_port)]
        if cfg['vnc_pwd']!='':
            qemu_cmd+=['-vnc','127.0.0.1:0,password']
        else:
            qemu_cmd+=['-vnc','127.0.0.1:0']
        qemu_cmd+=['-display','none']
    else:
        if cfg['host_video_acc'].lower()=='yes':
            qemu_cmd+=['-display','gtk,gl=on']
        else:
            qemu_cmd+=['-display','gtk,gl=off']
    if cfg['rng_dev'].lower()=='yes':
        qemu_cmd+=['-object','rng-random,id=rng0,filename=/dev/random','-device','virtio-rng-pci,rng=rng0']
    if os.path.exists(cfg['shared']):
        sf_str=',smb=' + cfg['shared']
    if cfg['fwd_ports']!='':
        ports_split=cfg['fwd_ports'].split(',')
        for pair_str in ports_split:
            if pair_str.find(':')!=-1: # If have FordwardPorts=<HostPort>:<GuestPort>
                pair=pair_str.split(':')
                fwd_ports_str+=',hostfwd=tcp::{}-:{},hostfwd=udp::{}-:{}'.format(pair[0],pair[1],pair[0],pair[1]);
            else:   # Else use the same port for Host and Guest.
                fwd_ports_str+=',hostfwd=tcp::{}-:{},hostfwd=udp::{}-:{}'.format(pair_str,pair_str,pair_str,pair_str);
    qemu_cmd+=['-nic','user,model={}{}{}'.format(cfg['net'],sf_str,fwd_ports_str)]
    if os.path.isfile(cfg['floppy']):
        qemu_cmd+=['-drive','index={},file={},if=floppy,format=raw'.format(str(drive_index),cfg['floppy'])]
        drive_index+=1
    if os.path.isfile(cfg['cdrom']):
        qemu_cmd+=['-drive','index={},file={},media=cdrom'.format(str(drive_index),cfg['cdrom'])]
        drive_index+=1
    if os.path.isfile(cfg['disk']):
        hdd_fmt=get_disk_format(cfg['disk'])
        hdd_virtio=''
        if cfg['hdd_virtio'].lower()=='yes':
            hdd_virtio=',if=virtio'
        qemu_cmd+=['-drive','index={},file={},format={}{}'.format(str(drive_index),cfg['disk'],hdd_fmt,hdd_virtio)]
        drive_index+=1
    if cfg['localtime']=='Yes':
        qemu_cmd+=['-rtc','base=localtime']
    if cfg['*']!='':
        qemu_cmd+=cfg['*'].split(' ')
    return rc,qemu_cmd,telnet_port

def program_handle_rc(rc):
    if rc.ok==False:
        for msg in rc.msgs:
            if msg.msg_type==InfoMsgType.im_error:
                print(msg.msg_txt)
                exit()
            elif msg.msg_type==InfoMsgType.im_warning or msg.msg_type==InfoMsgType.im_info:
                print(msg.msg_txt)

def execute_bash_code(contents):
    fpath="/tmp/qemurun_{}.sh".format(str(uuid.uuid4()))
    fh=open(fpath,"w+")
    fh.write(contents)
    fh.close()
    env_cpy=os.environ.copy()
    fnull=open(os.devnull,'w')
    rc=subprocess.call(['bash',fpath],env=env_cpy,stdout=fnull,stderr=fnull)
    os.remove(fpath)
    return rc

def program_subprocess_qemu(args):
    sp=subprocess.Popen(args['qemu_cmd'],env=args['qemu_env'],cwd=args['vm_dir'])
    print('QEMU Running at PID: {}'.format(str(sp.pid)))
    if args['telnet_port']!=0:
        print('Telnet monitor port: {}'.format(str(args['telnet_port'])))
    return sp

def program_subprocess_fix_smb():
    time.sleep(5)
    script="""#!/bin/bash
        smb_dir=$(ls /tmp | grep qemu-smb | head -n1)
        if [ "$smb_dir"!="" ]; then
            smb_dir="/tmp/$smb_dir" 
            echo "[global]
                allow insecure wide links=yes
                [qemu]
                follow symlinks=yes
                wide links=yes
                acl allow execute always=yes" >> "$smb_dir/smb.conf"
            #smbcontrol --configfile=$conf $pid reload-config
            exit 0
        fi"""
    return execute_bash_code(script)
    #return True

def program_subprocess_change_vnc_pwd(args):
    time.sleep(5)
    script="""#!/bin/bash
    vnc_pwd='@vnc_pwd@'
    printf "change vnc password\n%s\nexit\n" $vnc_pwd | nc 127.0.0.1 @telnet_port@"""
    script=script.replace("@vnc_pwd@",args['vnc_pwd'])
    script=script.replace("@telnet_port@",str(args['telnet_port']))
    return execute_bash_code(script)

def program_main():
    print('qemu-run. Forever beta software. Use on production on your own risk!\n')
    print('This software is Free software - released under the GPLv3 License.')
    print('Read the LICENSE file. Or go visit https://www.gnu.org/licenses/gpl-3.0.html\n')
    rc,vm_name,vm_dir=program_find_vm_location()
    program_handle_rc(rc)
    rc,cfg=program_get_cfg_values(vm_dir)
    program_handle_rc(rc)
    telnet_port=0
    rc,qemu_cmd,telnet_port=program_build_cmd_line(cfg,vm_name,vm_dir)
    program_handle_rc(rc)
    qemu_env=os.environ.copy()
    qemu_env['SDL_VIDEO_X11_DGAMOUSE']='0'
    print('Command line arguments:')
    print(*qemu_cmd)
    if os.path.exists(cfg['shared']):
        spawn_daemon(program_subprocess_fix_smb)
    if cfg['vnc_pwd']!='':
        args={}
        args['vnc_pwd']=cfg['vnc_pwd']
        args['telnet_port']=telnet_port
        spawn_daemon(program_subprocess_change_vnc_pwd,args)
    args={}
    args['qemu_cmd']=qemu_cmd
    args['qemu_env']=qemu_env
    args['vm_dir']=vm_dir
    args['telnet_port']=telnet_port
    spawn_daemon(program_subprocess_qemu, args)

if __name__=='__main__':
    program_main()
