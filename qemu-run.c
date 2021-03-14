/*Copyright (C) 2021 Lucie Cupcakes <lucie_linux [at] protonmail.com>
This file is part of qemu-run <https://github.com/lucie-cupcakes/qemu-run>.
qemu-run is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation; either version 3, or (at your option) any later
version.
qemu-run is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
for more details.
You should have received a copy of the GNU General Public License
along with qemu-run; see the file LICENSE.  If not see <http://www.gnu.org/licenses/>.*/

#include <glib.h>
#include <gmodule.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <unistd.h>
#include <linux/limits.h>
#include <sys/sysinfo.h> // @TODO: Is this Linux only ?
#include <sys/stat.h>

#define BUFFER_MAX 1048576

#define cfg_add_kv(cfg, k, v) g_hash_table_insert(cfg, g_strdup(k), g_strdup(v));

#define log_msg(m) fprintf(stderr, "%s\n", m);
#define print_gpl_banner() \
	puts("qemu-run. Forever beta software. Use on production on your own risk!\nThis software is Free software - released under the GPLv3 License.\nRead the LICENSE file. Or go visit https://www.gnu.org/licenses/gpl-3.0.html\n");

gboolean file_exists(const char *fpath) {
	struct stat buffer;
	return (stat (fpath, &buffer) == 0) ? TRUE : FALSE;
}

gboolean g_dir_exists(const gchar *path) {
	gboolean rc = FALSE;
	GDir* gd = g_dir_open(path, 0, NULL);
	if (gd != NULL) {
		rc = TRUE;
		g_dir_close(gd);
	}
	return rc;
}

gboolean g_hash_table_match_key_alow(GHashTable *t, gpointer k, const char *s) {
	/* Returns TRUE if the value of the provided key for the HashTable t
	 * at lowercase is equal to s
	 * Otherwise, returns FALSE
	*/
	gboolean res = FALSE;
	char *t_v_low;
	gpointer t_v = g_hash_table_lookup(t, k);
	
	if (t_v != NULL) {
		t_v_low = g_ascii_strdown(t_v, -1);		
		res = strcmp((const char*)t_v_low, s) == 0 ? TRUE : FALSE;
		g_free(t_v_low);
	}
	
	return res;
}

size_t cstr_trim_right(const char *cstr, const size_t length) {
	size_t difference = 0;
	for (size_t i = length - 1; i < length; i--) {
		if (! isspace(*(cstr + i))) break;
		difference++;
	}
	return length - difference;
}

int process_kv_pair(char *kv_cstr, GHashTable *cfg) {
	size_t kv_cstr_len = strlen(kv_cstr);
	kv_cstr[kv_cstr_len - 1] = '\0';
	if (kv_cstr_len < 3) return 1;

	char c = '\0';
	char value_buffer[BUFFER_MAX], key_buffer[BUFFER_MAX];

	size_t value_len = 0, key_len = 0;
	int setting_key = 1, trimming_left = 1;

	for (size_t i = 0; (c = kv_cstr[i]) != '\0'; i++) {
		if (c == '=') {
			setting_key = 0;
			trimming_left = 1;
			continue;
		}
		if (setting_key && trimming_left && !isspace(c)) {
			trimming_left = 0;
			key_buffer[key_len] = c;
			key_len++;
		} else if (setting_key && !trimming_left)  {
			key_buffer[key_len] = c;
			key_len++;
		} else if (!setting_key && trimming_left && !isspace(c)) {
			trimming_left = 0;
			value_buffer[value_len] = c;
			value_len++;
		} else if (!setting_key && !trimming_left) {
			value_buffer[value_len] = c;
			value_len++;
		} 
	}
	key_buffer[key_len] = 0;
	value_buffer[value_len] = 0;
	key_len = cstr_trim_right(key_buffer, key_len);
	value_len = cstr_trim_right(value_buffer, value_len);
	key_buffer[key_len] = 0;
	value_buffer[value_len] = 0;
	g_hash_table_replace(cfg, g_strdup(key_buffer), g_strdup(value_buffer));
	return 0;
}

gboolean config_load(const char *fpath, GHashTable *cfg) {
	FILE *fptr = fopen(fpath, "r");
	if (fptr == NULL) return FALSE; //@TODO: error management
	char line[BUFFER_MAX];
	while(fgets(line, BUFFER_MAX, fptr) != NULL) {
		process_kv_pair(line, cfg);
	}
	fclose(fptr);
	return TRUE;
}

void program_get_cfg_values(GHashTable *cfg, char *vm_dir) {
	char path_buff[PATH_MAX] = {0};
	char nproc_str[4];
	snprintf(nproc_str, 4, "%d", get_nprocs());
	cfg_add_kv(cfg, "sys", "x64");
	cfg_add_kv(cfg, "efi", "no");
	cfg_add_kv(cfg, "cpu", "host");
	cfg_add_kv(cfg, "cores", nproc_str);
	cfg_add_kv(cfg, "mem", "2G");
	cfg_add_kv(cfg, "acc", "yes");
	cfg_add_kv(cfg, "vga", "virtio");
	cfg_add_kv(cfg, "snd", "hda");
	cfg_add_kv(cfg, "boot", "c");
	cfg_add_kv(cfg, "fwd_ports", "2222:22");
	cfg_add_kv(cfg, "hdd_virtio", "yes");
	cfg_add_kv(cfg, "net", "virtio-net-pci");
	cfg_add_kv(cfg, "rng_dev", "yes");
	cfg_add_kv(cfg, "host_video_acc", "no");
	cfg_add_kv(cfg, "localtime", "no");
	cfg_add_kv(cfg, "headless", "no");
	cfg_add_kv(cfg, "vnc_pwd", "");
	cfg_add_kv(cfg, "monitor_port", "5510");
	
	snprintf(path_buff, PATH_MAX, "%s/%s", vm_dir, "shared");
	if (g_dir_exists(path_buff)) {
		cfg_add_kv(cfg, "shared", path_buff);
	} else {
		cfg_add_kv(cfg, "shared", "");
	}
	
	snprintf(path_buff, PATH_MAX, "%s/%s", vm_dir, "floppy");
	if (file_exists(path_buff)) {
		cfg_add_kv(cfg, "floppy", path_buff);
	}
	snprintf(path_buff, PATH_MAX, "%s/%s", vm_dir, "cdrom");
	if (file_exists(path_buff)) {
		cfg_add_kv(cfg, "cdrom", path_buff);
	}
	snprintf(path_buff, PATH_MAX, "%s/%s", vm_dir, "disk");
	if (file_exists(path_buff)) {
		cfg_add_kv(cfg, "disk", path_buff);
	}
}

gboolean program_build_cmd_line(GHashTable *cfg, char *vm_dir, char *vm_name, GPtrArray **out_cmd) {
	gboolean rc = TRUE;
	int drive_index = 0, telnet_port = 55555; // @TODO: Get usable TCP port
	gpointer cfg_v;
	*out_cmd = NULL;
	GPtrArray *cmd = g_ptr_array_new_with_free_func(g_free);
	char cmd_slice[BUFFER_MAX] = {0};
	char sf_str[BUFFER_MAX] = {0};
	char fwd_ports_str[BUFFER_MAX] = {0};
	cmd_slice[0] = 0; sf_str[0] = 0;
	
	cfg_v = g_hash_table_lookup(cfg, "sys");
	if (strcmp((const char*)cfg_v, "x32") == 0) {
		g_ptr_array_add(cmd, g_strdup("qemu-system-i386"));
	} else if (strcmp((const char*)cfg_v, "x64") == 0) {
		g_ptr_array_add(cmd, g_strdup("qemu-system-x86_64"));
	} else {
		log_msg("Invalid value for sys"); //@TODO: Logger
		g_ptr_array_free(cmd, TRUE);
		rc = FALSE;
	}

	if (g_hash_table_match_key_alow(cfg, "acc", "yes")) {
		g_ptr_array_add(cmd, g_strdup("--enable-kvm"));
	}
	
	if (strcmp(vm_name, "") != 0) {
		g_ptr_array_add(cmd, g_strdup("-name"));
		g_ptr_array_add(cmd, g_strdup(vm_name));
	}
	
	g_ptr_array_add(cmd, g_strdup("-cpu"));
	g_ptr_array_add(cmd, g_strdup((char*)g_hash_table_lookup(cfg, "cpu")));
	g_ptr_array_add(cmd, g_strdup("-smp"));
	g_ptr_array_add(cmd, g_strdup((char*)g_hash_table_lookup(cfg, "cores")));
	g_ptr_array_add(cmd, g_strdup("-m"));
	g_ptr_array_add(cmd, g_strdup((char*)g_hash_table_lookup(cfg, "mem")));
	g_ptr_array_add(cmd, g_strdup("-boot"));
	snprintf(cmd_slice, BUFFER_MAX, "order=%s", (char*)g_hash_table_lookup(cfg, "boot"));
	g_ptr_array_add(cmd, g_strdup(cmd_slice));

	g_ptr_array_add(cmd, g_strdup("-usb"));
	g_ptr_array_add(cmd, g_strdup("-device"));
	g_ptr_array_add(cmd, g_strdup("usb-tablet"));
	
	if (! g_hash_table_match_key_alow(cfg, "snd", "no")) {
		g_ptr_array_add(cmd, g_strdup("-soundhw"));
		g_ptr_array_add(cmd, g_strdup((char*)g_hash_table_lookup(cfg, "snd")));
	}

	g_ptr_array_add(cmd, g_strdup("-vga"));
	g_ptr_array_add(cmd, g_strdup((char*)g_hash_table_lookup(cfg, "vga")));

	if (g_hash_table_match_key_alow(cfg, "headless", "yes")) {
		g_ptr_array_add(cmd, g_strdup("-monitor"));
		snprintf(cmd_slice, BUFFER_MAX, "telnet:127.0.0.1:%d,server,nowait", telnet_port);
		g_ptr_array_add(cmd, g_strdup(cmd_slice));
		g_ptr_array_add(cmd, g_strdup("-vnc"));
		gboolean has_vncpwd = (!strcmp((const char*)g_hash_table_lookup(cfg, "vnc_pwd"), ""));
		g_ptr_array_add(cmd, g_strdup(has_vncpwd ? "127.0.0.1:0,password" : "127.0.0.1:0" ));
		g_ptr_array_add(cmd, g_strdup("-display"));
		g_ptr_array_add(cmd, g_strdup("none"));
	} else {
		if (g_hash_table_match_key_alow(cfg, "host_video_acc", "yes")) {
			g_ptr_array_add(cmd, g_strdup("-display"));
			g_ptr_array_add(cmd, g_strdup("gtk,gl=on"));
		} else {
			g_ptr_array_add(cmd, g_strdup("-display"));
			g_ptr_array_add(cmd, g_strdup("gtk,gl=off"));
		}
	}
	
	if (g_hash_table_match_key_alow(cfg, "rng_dev", "yes")) {
		g_ptr_array_add(cmd, g_strdup("-object"));
		g_ptr_array_add(cmd, g_strdup("rng-random,id=rng0,filename=/dev/random"));
		g_ptr_array_add(cmd, g_strdup("-device"));
		g_ptr_array_add(cmd, g_strdup("virtio-rng-pci,rng=rng0"));
	}

	cfg_v = g_hash_table_lookup(cfg, "shared");
	if (strcmp((const char*) cfg_v, "") != 0) {
		if (g_dir_exists((const char*) cfg_v)) {
			snprintf(sf_str, BUFFER_MAX, ",smb=%s", (const char*)cfg_v);
		}
	}
	
	/* @TODO: Forward ports logic */

	g_ptr_array_add(cmd, g_strdup("-nic"));
	snprintf(cmd_slice, BUFFER_MAX, "user,model=%s%s%s", (char*)g_hash_table_lookup(cfg, "net"), sf_str, fwd_ports_str);
	g_ptr_array_add(cmd, g_strdup(cmd_slice));
	
	cfg_v = g_hash_table_lookup(cfg, "floppy");
	if (file_exists((const char*) cfg_v)) {
		g_ptr_array_add(cmd, g_strdup("-drive"));
		snprintf(cmd_slice, BUFFER_MAX, "index=%d,file=%s,if=floppy,format=raw", drive_index, (char*)cfg_v);
		g_ptr_array_add(cmd, g_strdup(cmd_slice));
		drive_index++;
	}
	
	cfg_v = g_hash_table_lookup(cfg, "cdrom");
	if (file_exists((const char*) cfg_v)) {
		g_ptr_array_add(cmd, g_strdup("-drive"));
		snprintf(cmd_slice, BUFFER_MAX, "index=%d,file=%s,media=cdrom", drive_index, (char*)cfg_v);
		g_ptr_array_add(cmd, g_strdup(cmd_slice));
		drive_index++;
	}
	
	cfg_v = g_hash_table_lookup(cfg, "disk");
	if (file_exists((const char*) cfg_v)) {
		gboolean hdd_virtio = g_hash_table_match_key_alow(cfg, "hdd_virtio", "yes");
		g_ptr_array_add(cmd, g_strdup("-drive"));
		snprintf(cmd_slice, BUFFER_MAX, "index=%d,file=%s%s", drive_index, (char*)cfg_v, hdd_virtio ? ",if=virtio" : "");
		g_ptr_array_add(cmd, g_strdup(cmd_slice));
		drive_index++;
	}
	
	if (g_hash_table_match_key_alow(cfg, "localtime", "yes")) {
		g_ptr_array_add(cmd, g_strdup("-rtc"));
		g_ptr_array_add(cmd, g_strdup("base=localtime"));
	}
	
	if (rc) {
		*out_cmd = cmd;
	}
	
	return rc;
}

gboolean program_find_vm_location(int argc, char **argv, char **out_vm_name, char **out_vm_dir, char **out_vm_cfg_file) {
	gboolean rc = FALSE;
	*out_vm_name = NULL;
	*out_vm_dir = NULL;
	*out_vm_cfg_file = NULL;
	
	if (argc == 1) {
		char cwd[PATH_MAX];
		getcwd(cwd, sizeof(cwd));
		*out_vm_dir = g_strdup(cwd);
	}
	
	if (FALSE) {
		// @TODO: detect_if_cfg_is_in_args(int argc, char** argv)
		/*char cwd[PATH_MAX];
		getcwd(cwd, sizeof(cwd));
		*out_vm_dir = g_strdup(cwd);
		*out_vm_name = g_strdup("VM_NAME");*/
	} else {
		// Normal lookup using ENV var
		const char *vm_name = argv[1];
		const char *vm_dir_env_str = getenv("QEMURUN_VM_PATH");
		gboolean vm_dir_exists = FALSE;
		char vm_dir[PATH_MAX];
		gchar **vm_dir_env = g_strsplit(vm_dir_env_str, ":", 0);

		for (int i = 0; vm_dir_env[i] != NULL && vm_dir_exists == FALSE; i++) {
			snprintf(vm_dir, PATH_MAX, "%s/%s", vm_dir_env[i], vm_name);
			vm_dir_exists = g_dir_exists(vm_dir);
		}
		
		if (vm_dir_exists) {
			char cfg_file[PATH_MAX];
			snprintf(cfg_file, PATH_MAX, "%s/%s", vm_dir, "config");
			*out_vm_name = g_strdup(vm_name);
			*out_vm_dir = g_strdup(vm_dir);
			*out_vm_cfg_file = g_strdup(cfg_file);
			rc = TRUE;
		} else {
			log_msg("Error: Cannot find VM, Check your VM_PATH env. variable ?");
		}
		
		g_strfreev(vm_dir_env);
		return rc;
	}
}

void g_hash_table_print(gpointer key, gpointer value) {
	printf("%s=%s\n", (char*) key, (char*) value);
}

void g_ptr_array_foreach_len(gpointer data, gpointer user_data) {
	//printf("%s ", (const char*) data);
	size_t len_total = *(size_t*)user_data;
	*(size_t*)user_data = len_total + strlen((const char*) data) + 1;
}

void g_ptr_array_foreach_copy(gpointer data, gpointer user_data) {
	char *src = (char *) data;
	char *dst = *(char **)user_data;

	for (int i = 0; src[i] != '\0'; i++) {
		*dst = src[i];
		dst++;
		//printf("%p = [%c]\n", dst, src[i]);
	}
	
	*dst = ' '; dst++;
	*(char **)user_data = dst;
}

int main(int argc, char **argv) {
	print_gpl_banner();
	char *vm_name = NULL;
	char *vm_dir = NULL;
	char *vm_cfg_file = NULL;
	GPtrArray *cmd = NULL;
	
	if (! program_find_vm_location(argc, argv, &vm_name, &vm_dir, &vm_cfg_file)) {
		return 1;
	}
	
	//printf("vm_name=%s\nvm_dir=%s\nvm_cfg_file=%s\n", vm_name, vm_dir, vm_cfg_file);
	
	GHashTable *cfg = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, g_free);
	program_get_cfg_values(cfg, vm_dir);
	if (! config_load(vm_cfg_file, cfg)) {
		log_msg("Error: cannot load config.");
		return 1;
	}
	
	if (! program_build_cmd_line(cfg, vm_dir, vm_name, &cmd)) {
		return 1;
	}

	//g_hash_table_foreach(cfg, g_hash_table_print, NULL);
	size_t cmd_final_len = 0;
	g_ptr_array_foreach (cmd, g_ptr_array_foreach_len, &cmd_final_len);
	char *cmd_final = malloc(sizeof(char)*cmd_final_len);
	char *cmd_final_start = cmd_final;
	g_ptr_array_foreach (cmd, g_ptr_array_foreach_copy, &cmd_final);
	cmd_final_start[cmd_final_len - 1] = '\0';
	printf("Command line arguments:\n%s\n", cmd_final_start);
	system(cmd_final_start);
	free(cmd_final_start);
	g_free(vm_name); g_free(vm_dir); g_free(vm_cfg_file);
	g_ptr_array_free(cmd, TRUE);
	g_hash_table_destroy(cfg);
	return 0;
}
