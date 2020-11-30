#!/usr/bin/env python3
# Shared folders: Needs smbd and gawk
import os, sys, errno, socket, subprocess
from enum import Enum

# Mini error handling lib:
class InfoMsgType(Enum):
	im_error = 0
	im_warning = 1
	im_info = 2

class InfoMsg:
	def __init__(self, msg_txt, msg_type = InfoMsgType.im_error):
		self.msg_txt = msg_txt
		self.msg_type = msg_type

class ReturnCode:
	def __init__(self, ok=True, msg=None): #op_success = Boolean, infomsg = InfoMsg class.
		self.ok = ok
		self.msg = msg
	def set_error(self, err_msg):
		self.ok = False
		self.msg = err_msg

#My replacement for configobj, fuck that shit.
def load_cfg_process(res, lines):
	for line in fh.readlines():
		if line.find('=') != -1:
			sline = line.split('=')
			res[sline[0].strip()] = sline[1].strip()
	return res

def load_cfg_from_file(fpath, defaults=None): # defaults must be a dictionary..
	res = {}
	if defaults is not None:
		res = defaults.copy()
	with open(fpath, 'r') as fh:
		res = load_cfg_process(res, fh.readlines())
	return res

def load_cfg_from_args(arg_cfg_str, defaults=None, delimiter=','):
	res = {}
	if defaults is not None:
		res = defaults.copy()
	res = load_cfg_process(res, arg_cfg_str.split(delimiter))
	return res

def get_disk_format(file_path):
	out = subprocess.check_output(['qemu-img','info', file_path], universal_newlines=True).split()
	prev_was_fmt = False
	result = ''
	for s in out:
		if prev_was_fmt:
			result = s
			break
		else:
			prev_was_fmt = s == 'format:' 
	return result

def spawn_daemon(func):
	# do the UNIX double-fork magic, see Stevens' 'Advanced
	# Programming in the UNIX Environment' for details (ISBN 0201563177)
	try:
		pid = os.fork()
		if pid > 0:
			return
	except OSError as e:
		print('fork #1 failed: %d (%s)' % (e.errno, e.strerror), file=sys.stderr)
		sys.exit(1)
	os.setsid()
	try:
		pid = os.fork()
		if pid > 0:
			sys.exit(0)
	except OSError as e:
		print('fork #2 failed: %d (%s)' % (e.errno, e.strerror), file=sys.stderr)
		sys.exit(1)
	func()
	os._exit(os.EX_OK)
	
def get_qemu_version():
    result = []
    str_ver = subprocess.check_output(['qemu-system-i386', '--version']).decode(sys.stdout.encoding).strip()
    str_ver = str_ver.splitlines()[0].lower() # grab first line
    #check for shit added by distros : for example: '(Debian)'
    if str_ver.find('(') > -1:
        str_ver = str_ver.split('(')[0].strip()
    str_ver = str_ver.split('version')[1].strip().split('.')
    for i in str_ver: #convert array<str> to array<int>
        result.append(int(i))
    return result

def get_usable_port():
	port = 0
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.bind(('127.0.0.1', 0))
	port = sock.getsockname()[1]
	sock.close()
	return port

def detect_if_cfg_is_in_args():
	res = False
	if len(sys.argv) >= 2:
		if sys.argv[1].find('--cfg=') != -1:
			res = True
	return res

def program_find_vm_location():
	# return values=
	rc = ReturnCode()
	vm_name = ''
	vm_dir = ''
	# Use environment variable to find where the VM is
	if len(sys.argv) == 1: # No args.
		rc.set_error(InfoMsg('Warning: No arguments, assuming the VM is in CWD.', InfoMsgType.im_warning))
		vm_dir = os.getcwd()
	else:
		if detect_if_cfg_is_in_args() == True:
			vm_dir = os.getcwd()
			vm_name = "QEMU-VM"
		else:
			# Normal lookup using ENV var
			try:
				vm_dir_env = os.environ["QEMURUN_VM_PATH"].split(":")
			except:
				rc.set_error(InfoMsg("Cannot find environment variable QEMURUN_VM_PATH.\nPython error \#%d (%s)" % (e.errno, e.strerror)))
			vm_name = sys.argv[1]
			for p in vm_dir_env:
				vm_dir = '{}/{}'.format(p, vm_name)
				if os.path.exists(vm_dir):
					break
			if not os.path.exists(vm_dir):
				rc.set_error(InfoMsg('Cannot find VM: {}, Check your VM_PATH env. variable ?.'.format(vm_dir)))
	return rc, vm_name, vm_dir

def program_get_cfg_values(vm_dir):
	rc = ReturnCode()
	cfg = {}
	cfg['sys'] = 'x64'
	cfg['uefi'] = 'no'
	cfg['cpu'] = 'host'
	cfg['cores'] = subprocess.check_output(['nproc']).decode(sys.stdout.encoding).strip()
	cfg['mem'] = '2G'
	cfg['acc'] = 'yes'
	cfg['vga'] = 'virtio'
	cfg['snd'] = 'hda'
	cfg['boot'] = 'c'
	cfg['fwd_ports'] = ''
	cfg['hdd_virtio'] = 'yes'
	cfg['shared'] = 'shared'
	cfg['net'] = 'virtio-net-pci'
	cfg['rng_dev'] = 'yes'
	cfg['host_video_acc'] = 'no'
	cfg['localtime'] = 'no'
	cfg['headless'] = 'no'
	cfg['monitor_port'] = 5510
	cfg['cdrom'] = '{}/cdrom'.format(vm_dir) if os.path.isfile('{}/cdrom'.format(vm_dir)) else 'No'
	cfg['disk'] = '{}/disk'.format(vm_dir) if os.path.isfile('{}/disk'.format(vm_dir)) else 'No'

	if os.path.exists('{}/{}'.format(vm_dir, cfg['shared'])):
		cfg['shared'] = '{}/{}'.format(vm_dir, cfg['shared'])

	# Load Config File
	vm_cfg_file_path = '{}/config'.format(vm_dir)
	if os.path.isfile(vm_cfg_file_path):
		cfg = load_cfg_from_file(vm_cfg_file_path, cfg)
	else:
		if detect_if_cfg_is_in_args() == True:
			arg_cfg_str = sys.argv[1].split('--cfg=')[1]
			rc.set_error(InfoMsg('Info: Using configuration from arguments.', InfoMsgType.im_info))
			
			if arg_cfg_str.strip() == '':
				rc.set_error(InfoMsg('Error: argument cfg is empty.', InfoMsgType.im_info))
				return rc, None

			cfg = load_cfg_from_args()
		else:
			rc.set_error(InfoMsg('Cannot find config file.'))

	return rc, cfg

def program_build_cmd_line(cfg, vm_name, vm_dir):
	qemu_cmd = []
	qemu_ver = get_qemu_version()
	current_user_id = str(subprocess.check_output(['id','-u'], universal_newlines=True).rstrip())

	if cfg['sys'] == 'x32':
		qemu_cmd.append('qemu-system-i386')
	elif cfg['sys'] == 'x64':
		qemu_cmd.append('qemu-system-x86_64')

	if cfg['acc'].lower() == 'yes':
		qemu_cmd.append('--enable-kvm')

	if vm_name != '':
		qemu_cmd += ['-name', vm_name]

	if cfg['uefi'].lower() == 'yes':
		qemu_cmd += ['-L', '/usr/share/qemu', '-bios', 'OVMF.fd']

	if not (cfg['cpu'].lower() == 'host' and cfg['acc'].lower() != 'yes'):
		# Avoiding a non possible config..
		qemu_cmd += ['-cpu', cfg['cpu']]

	pulseaudio_socket = '/run/pulse/native'
	# pulseaudio_socket = '/run/user/' + current_user_id + '/pulse/native'

	qemu_cmd += ['-smp', cfg['cores'],
				'-m', cfg['mem'],
				'-boot', 'order=' + cfg['boot'],
				'-usb', '-device', 'usb-tablet',
				'-soundhw', cfg['snd']]

	telnet_port = 0

	if cfg['headless'].lower() == 'yes':
		telnet_port = get_usable_port()
		qemu_cmd += ['-monitor', 'telnet:127.0.0.1:{},server,nowait'.format(telnet_port)]
		qemu_cmd += ['-display', 'none']
	else:
		qemu_cmd += ['-vga', cfg['vga']]
		if cfg['host_video_acc'].lower() == 'yes':
			qemu_cmd += ['-display', 'gtk,gl=on']
		else:
			qemu_cmd += ['-display', 'gtk,gl=off']

	if qemu_ver[0] >= 4:
		qemu_cmd += ['-audiodev', 'pa,id=pa1,server=' + pulseaudio_socket]

	if cfg['rng_dev'].lower() == 'yes':
		qemu_cmd += ['-object', 'rng-random,id=rng0,filename=/dev/random', '-device', 'virtio-rng-pci,rng=rng0']

	sf_str = ''
	if os.path.exists(cfg['shared']):
		sf_str = ',smb=' + cfg['shared']

	fwd_ports_str = ''
	if cfg['fwd_ports'] != '':
		ports_split = cfg['fwd_ports'].split(',')
		for pair_str in ports_split:
			if pair_str.find(':') != -1: # If have FordwardPorts = <HostPort>:<GuestPort>
				pair = pair_str.split(':')
				fwd_ports_str += ',hostfwd=tcp::{}-:{},hostfwd=udp::{}-:{}'.format(pair[0], pair[1], pair[0], pair[1]);
			else:   # Else use the same port for Host and Guest.
				fwd_ports_str += ',hostfwd=tcp::{}-:{},hostfwd=udp::{}-:{}'.format(pair_str, pair_str, pair_str, pair_str);

	qemu_cmd += ['-nic', 'user,model={}{}{}'.format(cfg['net'], sf_str, fwd_ports_str)]

	drive_index = 0

	if os.path.isfile(cfg['disk']):
		hdd_fmt = get_disk_format(cfg['disk'])
		hdd_virtio = ''
		if cfg['hdd_virtio'].lower() == 'yes':
			hdd_virtio = ',if=virtio'
		qemu_cmd += ['-drive', 'file={},format={}{},index={}'.format(cfg['disk'], hdd_fmt, hdd_virtio, str(drive_index))]
		drive_index += 1

	if os.path.isfile(cfg['cdrom']):
		qemu_cmd += ['-drive', 'file={},media=cdrom,index={}'.format(cfg['cdrom'], str(drive_index))]
		drive_index += 1

	if cfg['localtime'] == 'Yes':
		qemu_cmd += ['-rtc', 'base=localtime']
		
	return qemu_cmd, telnet_port

def program_handle_rc(rc):
	if rc.ok == False:
		if rc.msg.msg_type == InfoMsgType.im_error:
			print(rc.msg.msg_txt)
			exit()
		elif rc.msg.msg_type == InfoMsgType.im_warning or rc.msg.msg_type == InfoMsgType.im_info:
			print(rc.msg.msg_txt)

def program_subprocess_qemu(qemu_cmd, qemu_env, vm_dir, telnet_port=0):
	sp = subprocess.Popen(qemu_cmd, env=qemu_env, cwd=vm_dir)
	print('QEMU Running at PID: {}'.format(str(sp.pid)))
	if telnet_port != 0:
		print('Telnet monitor port: {}'.format(str(telnet_port)))
	return sp

def program_subprocess_fix_smb():
	env_cpy = os.environ.copy()
	return subprocess.Popen(['bash', 'qemu_fix_smb.sh'], env=env_cpy)

def program_main():
	print("qemu-run. Forever beta software. Use on production on your own risk!\n")

	fun1_rc, vm_name, vm_dir = program_find_vm_location()
	program_handle_rc(fun1_rc)

	fun2_rc, cfg = program_get_cfg_values(vm_dir)
	program_handle_rc(fun2_rc)

	qemu_cmd, telnet_port = program_build_cmd_line(cfg, vm_name, vm_dir)

	qemu_env = os.environ.copy()
	qemu_env['SDL_VIDEO_X11_DGAMOUSE'] = '0'
	qemu_env['QEMU_AUDIO_DRV'] = 'pa'
	#qemu_env['QEMU_PA_SERVER'] = pulseaudio_socket

	print_cmd = False
	if len(sys.argv) == 3:
		if sys.argv[2] == '--print-cmd':
			print_cmd = True
	if print_cmd:
		#print(' '.join(qemu_cmd))
		print(*qemu_cmd)
	else:
		#if os.path.exists(cfg['shared']):
		#	spawn_daemon(program_subprocess_fix_smb)
		program_subprocess_qemu(qemu_cmd, qemu_env, vm_dir, telnet_port).wait()

if __name__ == '__main__':
	program_main()