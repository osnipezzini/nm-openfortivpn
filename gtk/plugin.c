/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <glib-object.h>
#include <gmodule.h>
#include <NetworkManager.h>
#include <nm-vpn-editor-plugin.h>

#include "nm-openfortivpn-service.h"
#include "nm-vpn-plugin-utils.h"

#define TYPE_OPENFORTIVPN_PLUGIN (openfortivpn_plugin_get_type())
#define OPENFORTIVPN_PLUGIN(o) (G_TYPE_CHECK_INSTANCE_CAST((o), TYPE_OPENFORTIVPN_PLUGIN, OpenfortivpnPlugin))

typedef struct { GObject parent; } OpenfortivpnPlugin;
typedef struct { GObjectClass parent; } OpenfortivpnPluginClass;

static void openfortivpn_plugin_iface_init(NMVpnEditorPluginInterface *iface);

GType openfortivpn_plugin_get_type(void);
G_DEFINE_TYPE_WITH_CODE(OpenfortivpnPlugin, openfortivpn_plugin, G_TYPE_OBJECT,
                        G_IMPLEMENT_INTERFACE(NM_TYPE_VPN_EDITOR_PLUGIN,
                                              openfortivpn_plugin_iface_init))

enum { PROP_NAME = 1, PROP_DESC, PROP_SERVICE };

static NMVpnEditor *
get_editor(NMVpnEditorPlugin *iface, NMConnection *connection, GError **error)
{
    return nm_vpn_plugin_utils_load_editor("openfortivpn", "nm_vpn_editor_factory_openfortivpn",
                                           iface, connection, error);
}

static NMVpnEditorPluginCapability
get_capabilities(NMVpnEditorPlugin *iface)
{
    return NM_VPN_EDITOR_PLUGIN_CAPABILITY_NONE;
}

static void
get_property(GObject *object, guint prop_id, GValue *value, GParamSpec *pspec)
{
    switch (prop_id) {
    case PROP_NAME:
        g_value_set_string(value, "openfortivpn");
        break;
    case PROP_DESC:
        g_value_set_string(value, "Fortinet SSL VPN (openfortivpn)");
        break;
    case PROP_SERVICE:
        g_value_set_string(value, NM_DBUS_SERVICE_OPENFORTIVPN);
        break;
    default:
        G_OBJECT_WARN_INVALID_PROPERTY_ID(object, prop_id, pspec);
    }
}

static void
openfortivpn_plugin_class_init(OpenfortivpnPluginClass *klass)
{
    GObjectClass *oc = G_OBJECT_CLASS(klass);

    oc->get_property = get_property;
    g_object_class_override_property(oc, PROP_NAME, NM_VPN_EDITOR_PLUGIN_NAME);
    g_object_class_override_property(oc, PROP_DESC, NM_VPN_EDITOR_PLUGIN_DESCRIPTION);
    g_object_class_override_property(oc, PROP_SERVICE,
                                     NM_VPN_EDITOR_PLUGIN_SERVICE);
}

static void
openfortivpn_plugin_init(OpenfortivpnPlugin *self)
{
}

static void
openfortivpn_plugin_iface_init(NMVpnEditorPluginInterface *iface)
{
    iface->get_editor = get_editor;
    iface->get_capabilities = get_capabilities;
}

G_MODULE_EXPORT NMVpnEditorPlugin *
nm_vpn_editor_plugin_factory(GError **error)
{
    g_return_val_if_fail(!error || !*error, NULL);
    return g_object_new(TYPE_OPENFORTIVPN_PLUGIN, NULL);
}
