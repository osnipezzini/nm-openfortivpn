/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef __NM_VPN_PLUGIN_UTILS_H__
#define __NM_VPN_PLUGIN_UTILS_H__

#include <NetworkManager.h>
#include <nm-vpn-editor-plugin.h>

/* dlopen()s the editor lib that sits next to this plugin lib (GTK3 or GTK4
 * variant, depending on what the host process loaded) and calls its factory. */
NMVpnEditor *nm_vpn_plugin_utils_load_editor(const char *plugin_name,
                                             const char *factory_name,
                                             NMVpnEditorPlugin *editor_plugin,
                                             NMConnection *connection,
                                             GError **error);

#endif
