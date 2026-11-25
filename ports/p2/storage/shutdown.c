// SPDX-License-Identifier: MIT
#include "py/runtime.h"
#if MICROPY_VFS_FAT
#include "extmod/vfs.h"
#include "extmod/vfs_fat.h"
#include "extmod/vfs_lfs.h"
#include "lib/oofatfs/diskio.h"

int p2_is_filesystem_stream(const void *obj) {
    const mp_obj_type_t *type = ((const mp_obj_base_t *)obj)->type;
    return type == &mp_type_vfs_fat_fileio || type == &mp_type_vfs_fat_textio
           #if MICROPY_VFS_LFS2
           || type == &mp_type_vfs_lfs2_fileio || type == &mp_type_vfs_lfs2_textio
           #endif
    ;
}

void p2_unmount_filesystems(void) {
    mp_vfs_mount_t *mount = MP_STATE_VM(vfs_mount_table);
    while (mount != NULL) {
        // pyboard's host mount and arbitrary Python VFS objects are outside
        // the native storage lifecycle. Do not issue I/O to them at reset.
        mp_vfs_mount_t *next = mount->next;
        const mp_obj_type_t *type = mp_obj_get_type(mount->obj);
        if (type == &mp_fat_vfs_type
            #if MICROPY_VFS_LFS2
            || type == &mp_type_vfs_lfs2
            #endif
            ) {
            nlr_buf_t nlr;
            if (nlr_push(&nlr) == 0) {
                if (type == &mp_fat_vfs_type
                    && disk_ioctl(MP_OBJ_TO_PTR(mount->obj), CTRL_SYNC, NULL) != RES_OK) {
                    mp_printf(&mp_plat_print, "could not sync %s\n", mount->str);
                }
                mp_vfs_umount(mount->obj);
                nlr_pop();
            } else {
                mp_obj_print_exception(&mp_plat_print, MP_OBJ_FROM_PTR(nlr.ret_val));
            }
        }
        mount = next;
    }
}
#endif
