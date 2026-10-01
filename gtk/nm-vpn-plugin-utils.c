/* SPDX-License-Identifier: GPL-2.0-or-later
 * Modeled on NetworkManager-openvpn shared/nm-utils/nm-vpn-plugin-utils.c */
#define _GNU_SOURCE
#include "nm-vpn-plugin-utils.h"

#include <dlfcn.h>
#include <string.h>

typedef NMVpnEditor *(*EditorFactory)(NMVpnEditorPlugin *, NMConnection *, GError **);

NMVpnEditor *
nm_vpn_plugin_utils_load_editor(const char *plugin_name,
                                const char *factory_name,
                                NMVpnEditorPlugin *editor_plugin,
                                NMConnection *connection,
                                GError **error)
{
    Dl_info info;
    gboolean gtk4;
    g_autofree char *dir = NULL;
    g_autofree char *path = NULL;
    void *handle;
    EditorFactory factory;
    NMVpnEditor *editor;

    /* GTK3 has gtk_container_add, GTK4 does not. */
    gtk4 = !dlsym(RTLD_DEFAULT, "gtk_container_add") && dlsym(RTLD_DEFAULT, "gtk_init");

    if (!dladdr((void *) nm_vpn_plugin_utils_load_editor, &info) || !info.dli_fname) {
        g_set_error(error, NM_CONNECTION_ERROR, NM_CONNECTION_ERROR_FAILED,
                    "cannot locate the plugin directory");
        return NULL;
    }
    dir = g_path_get_dirname(info.dli_fname);
    path = g_strdup_printf("%s/lib%s-vpn-plugin-%s-editor.so", dir, gtk4 ? "nm-gtk4" : "nm",
                           plugin_name);

    handle = dlopen(path, RTLD_LAZY | RTLD_LOCAL);
    if (!handle) {
        g_set_error(error, NM_CONNECTION_ERROR, NM_CONNECTION_ERROR_FAILED,
                    "cannot load editor %s: %s", path, dlerror());
        return NULL;
    }
    factory = (EditorFactory) dlsym(handle, factory_name);
    if (!factory) {
        g_set_error(error, NM_CONNECTION_ERROR, NM_CONNECTION_ERROR_FAILED,
                    "missing symbol %s in %s", factory_name, path);
        dlclose(handle);
        return NULL;
    }
    editor = factory(editor_plugin, connection, error);
    if (!editor)
        dlclose(handle);
    /* else: keep the module resident, its types live on. */
    return editor;
}
