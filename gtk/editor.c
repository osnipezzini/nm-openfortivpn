/* SPDX-License-Identifier: GPL-2.0-or-later
 * NMVpnEditor for openfortivpn. Built twice from this file: GTK3 and GTK4. */
#include <gtk/gtk.h>
#include <gmodule.h>
#include <NetworkManager.h>
#include <nm-vpn-editor-plugin.h>
#include <nma-ui-utils.h>

#include "nm-openfortivpn-service.h"

#if GTK_CHECK_VERSION(4, 0, 0)
#define GET_TEXT(w) gtk_editable_get_text(GTK_EDITABLE(w))
#define SET_TEXT(w, t) gtk_editable_set_text(GTK_EDITABLE(w), (t))
#define GET_ACTIVE(w) gtk_check_button_get_active(GTK_CHECK_BUTTON(w))
#define SET_ACTIVE(w, a) gtk_check_button_set_active(GTK_CHECK_BUTTON(w), (a))
#else
#define GET_TEXT(w) gtk_entry_get_text(GTK_ENTRY(w))
#define SET_TEXT(w, t) gtk_entry_set_text(GTK_ENTRY(w), (t))
#define GET_ACTIVE(w) gtk_toggle_button_get_active(GTK_TOGGLE_BUTTON(w))
#define SET_ACTIVE(w, a) gtk_toggle_button_set_active(GTK_TOGGLE_BUTTON(w), (a))
#endif

#define PASSWORD_FLAGS NM_OPENFORTIVPN_KEY_PASSWORD "-flags"
#define OTP_FLAGS NM_OPENFORTIVPN_KEY_OTP "-flags"
#define TFA_FLAGS NM_OPENFORTIVPN_KEY_2FA "-flags"

static void openfortivpn_editor_iface_init(NMVpnEditorInterface *iface);

typedef struct {
    GObject parent;
    GtkWidget *root;
    GtkWidget *gateway, *user, *password, *ca, *cert, *key, *trusted_cert, *realm;
    GtkWidget *otp, *tfa, *saml, *saml_port;
    NMSettingVpn *tmp; /* stand-in for nma's password menu on new connections */
} OpenfortivpnEditor;

typedef struct { GObjectClass parent; } OpenfortivpnEditorClass;

GType openfortivpn_editor_get_type(void);
G_DEFINE_TYPE_WITH_CODE(OpenfortivpnEditor, openfortivpn_editor, G_TYPE_OBJECT,
                        G_IMPLEMENT_INTERFACE(NM_TYPE_VPN_EDITOR, openfortivpn_editor_iface_init))
#define OPENFORTIVPN_EDITOR(o) \
    (G_TYPE_CHECK_INSTANCE_CAST((o), openfortivpn_editor_get_type(), OpenfortivpnEditor))

static void
emit_changed(gpointer self)
{
    g_signal_emit_by_name(self, "changed");
}

static void
saml_toggled(GtkWidget *w, gpointer user_data)
{
    OpenfortivpnEditor *self = user_data;
    gboolean on = GET_ACTIVE(self->saml);

    gtk_widget_set_sensitive(self->user, !on);
    gtk_widget_set_sensitive(self->password, !on);
    gtk_widget_set_sensitive(self->saml_port, on);
    emit_changed(self);
}

static void
chooser_response(GtkNativeDialog *dlg, int response, gpointer entry)
{
    if (response == GTK_RESPONSE_ACCEPT) {
        GFile *f = gtk_file_chooser_get_file(GTK_FILE_CHOOSER(dlg));
        char *path = f ? g_file_get_path(f) : NULL;

        if (path)
            SET_TEXT(entry, path);
        g_free(path);
        g_clear_object(&f);
    }
    g_object_unref(dlg);
}

static void
browse_clicked(GtkWidget *btn, gpointer entry)
{
    GtkWindow *parent;
    GtkFileChooserNative *dlg;

#if GTK_CHECK_VERSION(4, 0, 0)
    GtkRoot *r = gtk_widget_get_root(btn);
    parent = GTK_IS_WINDOW(r) ? GTK_WINDOW(r) : NULL;
#else
    GtkWidget *t = gtk_widget_get_toplevel(btn);
    parent = GTK_IS_WINDOW(t) ? GTK_WINDOW(t) : NULL;
#endif
    dlg = gtk_file_chooser_native_new("Selecionar arquivo", parent, GTK_FILE_CHOOSER_ACTION_OPEN,
                                      "_Abrir", "_Cancelar");
    g_signal_connect(dlg, "response", G_CALLBACK(chooser_response), entry);
    gtk_native_dialog_show(GTK_NATIVE_DIALOG(dlg));
}

static GObject *
get_object(GtkBuilder *b, const char *id)
{
    return gtk_builder_get_object(b, id);
}

static const char *
get_data(NMSettingVpn *s, const char *key)
{
    return s ? nm_setting_vpn_get_data_item(s, key) : NULL;
}

static gboolean
init_editor(OpenfortivpnEditor *self, NMConnection *connection, GError **error)
{
    NMSettingVpn *s_vpn = nm_connection_get_setting_vpn(connection);
    GtkBuilder *b = gtk_builder_new();
    const char *v;
    NMSettingSecretFlags pw_flags = NM_SETTING_SECRET_FLAG_NONE;
    guint port = NM_OPENFORTIVPN_SAML_PORT_DEFAULT;

    if (!gtk_builder_add_from_resource(b, "/org/freedesktop/NetworkManager/openfortivpn/editor.ui",
                                       error)) {
        g_object_unref(b);
        return FALSE;
    }

#define W(f, id) self->f = GTK_WIDGET(get_object(b, id))
    W(root, "root");
    W(gateway, "gateway");
    W(user, "user");
    W(password, "password");
    W(ca, "ca");
    W(cert, "cert");
    W(key, "key");
    W(trusted_cert, "trusted_cert");
    W(realm, "realm");
    W(otp, "otp");
    W(tfa, "tfa");
    W(saml, "saml");
    W(saml_port, "saml_port");
#undef W
    g_object_ref_sink(self->root);

    if ((v = get_data(s_vpn, NM_OPENFORTIVPN_KEY_GATEWAY)))
        SET_TEXT(self->gateway, v);
    if ((v = get_data(s_vpn, NM_OPENFORTIVPN_KEY_USER)))
        SET_TEXT(self->user, v);
    if ((v = get_data(s_vpn, NM_OPENFORTIVPN_KEY_CA)))
        SET_TEXT(self->ca, v);
    if ((v = get_data(s_vpn, NM_OPENFORTIVPN_KEY_CERT)))
        SET_TEXT(self->cert, v);
    if ((v = get_data(s_vpn, NM_OPENFORTIVPN_KEY_KEY)))
        SET_TEXT(self->key, v);
    if ((v = get_data(s_vpn, NM_OPENFORTIVPN_KEY_TRUSTED_CERT)))
        SET_TEXT(self->trusted_cert, v);
    if ((v = get_data(s_vpn, NM_OPENFORTIVPN_KEY_REALM)))
        SET_TEXT(self->realm, v);
    if (s_vpn && (v = nm_setting_vpn_get_secret(s_vpn, NM_OPENFORTIVPN_KEY_PASSWORD)))
        SET_TEXT(self->password, v);

    if ((v = get_data(s_vpn, OTP_FLAGS)))
        SET_ACTIVE(self->otp, (g_ascii_strtoull(v, NULL, 10) & NM_SETTING_SECRET_FLAG_NOT_SAVED) != 0);
    if ((v = get_data(s_vpn, TFA_FLAGS)))
        SET_ACTIVE(self->tfa, (g_ascii_strtoull(v, NULL, 10) & NM_SETTING_SECRET_FLAG_AGENT_OWNED) != 0);
    SET_ACTIVE(self->saml, g_strcmp0(get_data(s_vpn, NM_OPENFORTIVPN_KEY_SAML_LOGIN), "true") == 0);
    if ((v = get_data(s_vpn, NM_OPENFORTIVPN_KEY_SAML_PORT)))
        port = g_ascii_strtoull(v, NULL, 10);
    gtk_spin_button_set_value(GTK_SPIN_BUTTON(self->saml_port), port);

    if (s_vpn)
        nm_setting_get_secret_flags(NM_SETTING(s_vpn), NM_OPENFORTIVPN_KEY_PASSWORD, &pw_flags, NULL);
    if (!s_vpn)
        s_vpn = self->tmp = NM_SETTING_VPN(nm_setting_vpn_new());
    nma_utils_setup_password_storage(self->password, pw_flags, NM_SETTING(s_vpn),
                                     NM_OPENFORTIVPN_KEY_PASSWORD, TRUE, FALSE);

    g_signal_connect_swapped(self->gateway, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->user, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->password, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->ca, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->cert, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->key, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->trusted_cert, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->realm, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->otp, "toggled", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->tfa, "toggled", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->saml_port, "value-changed", G_CALLBACK(emit_changed), self);
    g_signal_connect(self->saml, "toggled", G_CALLBACK(saml_toggled), self);
    g_signal_connect(get_object(b, "ca_btn"), "clicked", G_CALLBACK(browse_clicked), self->ca);
    g_signal_connect(get_object(b, "cert_btn"), "clicked", G_CALLBACK(browse_clicked), self->cert);
    g_signal_connect(get_object(b, "key_btn"), "clicked", G_CALLBACK(browse_clicked), self->key);
    saml_toggled(NULL, self);

    g_object_unref(b);
    return TRUE;
}

static GObject *
get_widget(NMVpnEditor *iface)
{
    OpenfortivpnEditor *self = OPENFORTIVPN_EDITOR(iface);

#if !GTK_CHECK_VERSION(4, 0, 0)
    gtk_widget_show_all(self->root);
#endif
    return G_OBJECT(self->root);
}

static gboolean
update_connection(NMVpnEditor *iface, NMConnection *connection, GError **error)
{
    OpenfortivpnEditor *self = OPENFORTIVPN_EDITOR(iface);
    NMSettingVpn *s_vpn;
    gboolean saml = GET_ACTIVE(self->saml);
    NMSettingSecretFlags flags;
    const char *t;

    if (!*GET_TEXT(self->gateway)) {
        g_set_error_literal(error, NM_CONNECTION_ERROR, NM_CONNECTION_ERROR_INVALID_PROPERTY,
                            "Gateway não pode ser vazio");
        return FALSE;
    }

    s_vpn = NM_SETTING_VPN(nm_setting_vpn_new());
    g_object_set(s_vpn, NM_SETTING_VPN_SERVICE_TYPE, NM_DBUS_SERVICE_OPENFORTIVPN, NULL);

#define PUT(key, w)                                              \
    G_STMT_START {                                               \
        t = GET_TEXT(w);                                         \
        if (*t)                                                  \
            nm_setting_vpn_add_data_item(s_vpn, key, t);         \
    } G_STMT_END
    PUT(NM_OPENFORTIVPN_KEY_GATEWAY, self->gateway);
    PUT(NM_OPENFORTIVPN_KEY_CA, self->ca);
    PUT(NM_OPENFORTIVPN_KEY_CERT, self->cert);
    PUT(NM_OPENFORTIVPN_KEY_KEY, self->key);
    PUT(NM_OPENFORTIVPN_KEY_TRUSTED_CERT, self->trusted_cert);
    PUT(NM_OPENFORTIVPN_KEY_REALM, self->realm);
    if (!saml) {
        PUT(NM_OPENFORTIVPN_KEY_USER, self->user);
        t = GET_TEXT(self->password);
        if (*t)
            nm_setting_vpn_add_secret(s_vpn, NM_OPENFORTIVPN_KEY_PASSWORD, t);
        nm_setting_set_secret_flags(NM_SETTING(s_vpn), NM_OPENFORTIVPN_KEY_PASSWORD,
                                    nma_utils_menu_to_secret_flags(self->password), NULL);
    }
#undef PUT

    if (saml) {
        char *port = g_strdup_printf("%d", gtk_spin_button_get_value_as_int(GTK_SPIN_BUTTON(self->saml_port)));

        nm_setting_vpn_add_data_item(s_vpn, NM_OPENFORTIVPN_KEY_SAML_PORT, port);
        g_free(port);
    }
    nm_setting_vpn_add_data_item(s_vpn, NM_OPENFORTIVPN_KEY_SAML_LOGIN, saml ? "true" : "false");

    flags = GET_ACTIVE(self->otp) ? NM_SETTING_SECRET_FLAG_NOT_SAVED : NM_SETTING_SECRET_FLAG_NONE;
    nm_setting_set_secret_flags(NM_SETTING(s_vpn), NM_OPENFORTIVPN_KEY_OTP, flags, NULL);
    if (GET_ACTIVE(self->tfa)) {
        /* same as the Plasma widget: 2FA wins over OTP */
        nm_setting_set_secret_flags(NM_SETTING(s_vpn), NM_OPENFORTIVPN_KEY_2FA,
                                    NM_SETTING_SECRET_FLAG_AGENT_OWNED, NULL);
        nm_setting_set_secret_flags(NM_SETTING(s_vpn), NM_OPENFORTIVPN_KEY_OTP,
                                    NM_SETTING_SECRET_FLAG_NONE, NULL);
    }

    nm_connection_add_setting(connection, NM_SETTING(s_vpn));
    return TRUE;
}

static void
dispose(GObject *object)
{
    OpenfortivpnEditor *self = OPENFORTIVPN_EDITOR(object);

    g_clear_object(&self->root);
    g_clear_object(&self->tmp);
    G_OBJECT_CLASS(openfortivpn_editor_parent_class)->dispose(object);
}

static void
openfortivpn_editor_class_init(OpenfortivpnEditorClass *klass)
{
    G_OBJECT_CLASS(klass)->dispose = dispose;
}

static void
openfortivpn_editor_init(OpenfortivpnEditor *self)
{
}

static void
openfortivpn_editor_iface_init(NMVpnEditorInterface *iface)
{
    iface->get_widget = get_widget;
    iface->update_connection = update_connection;
}

G_MODULE_EXPORT NMVpnEditor *
nm_vpn_editor_factory_openfortivpn(NMVpnEditorPlugin *editor_plugin, NMConnection *connection,
                                   GError **error)
{
    OpenfortivpnEditor *self;

    g_return_val_if_fail(!error || !*error, NULL);
    self = g_object_new(openfortivpn_editor_get_type(), NULL);
    if (!init_editor(self, connection, error)) {
        g_object_unref(self);
        return NULL;
    }
    return NM_VPN_EDITOR(self);
}
