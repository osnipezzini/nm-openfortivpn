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


typedef struct { const char *key, *id; int def; } Field; /* def: so para checkboxes/spins */

/* ids de entries de texto; "browse" = tem botao "..." id_btn */
static const Field entries[] = {
    {NM_OPENFORTIVPN_KEY_GATEWAY, "gateway"}, {NM_OPENFORTIVPN_KEY_USER, "user"},
    {NM_OPENFORTIVPN_KEY_CA, "ca"}, {NM_OPENFORTIVPN_KEY_CERT, "cert"},
    {NM_OPENFORTIVPN_KEY_KEY, "key"}, {NM_OPENFORTIVPN_KEY_TRUSTED_CERT, "trusted_cert"},
    {NM_OPENFORTIVPN_KEY_REALM, "realm"}, {NM_OPENFORTIVPN_KEY_OTP_PROMPT, "otp_prompt"},
    {NM_OPENFORTIVPN_KEY_SNI, "sni"}, {NM_OPENFORTIVPN_KEY_CIPHER_LIST, "cipher_list"},
    {NM_OPENFORTIVPN_KEY_PPPD_LOG, "pppd_log"}, {NM_OPENFORTIVPN_KEY_PPPD_PLUGIN, "pppd_plugin"},
    {NM_OPENFORTIVPN_KEY_PPPD_IPPARAM, "pppd_ipparam"}, {NM_OPENFORTIVPN_KEY_PPPD_IFNAME, "pppd_ifname"},
    {NM_OPENFORTIVPN_KEY_PPPD_CALL, "pppd_call"}, {NM_OPENFORTIVPN_KEY_IFNAME, "ifname"},
};
static const char *const browse_ids[] = {"ca", "cert", "key", "pppd_log", "pppd_plugin"};

static const Field checks[] = {
    {NM_OPENFORTIVPN_KEY_NO_FTM_PUSH, "no_ftm_push", 0},
    {NM_OPENFORTIVPN_KEY_INSECURE_SSL, "insecure_ssl", 0},
    {NM_OPENFORTIVPN_KEY_SECLEVEL_1, "seclevel_1", 0},
    {NM_OPENFORTIVPN_KEY_SET_ROUTES, "set_routes", 1},
    {NM_OPENFORTIVPN_KEY_HALF_INTERNET_ROUTES, "half_internet_routes", 0},
    {NM_OPENFORTIVPN_KEY_SET_DNS, "set_dns", 1},
    {NM_OPENFORTIVPN_KEY_USE_RESOLVCONF, "use_resolvconf", 1},
    {NM_OPENFORTIVPN_KEY_PPPD_USE_PEERDNS, "pppd_use_peerdns", 0},
    {NM_OPENFORTIVPN_KEY_PPPD_ACCEPT_REMOTE, "pppd_accept_remote", 1},
};

static const Field spins[] = {
    {NM_OPENFORTIVPN_KEY_OTP_DELAY, "otp_delay", 0},
    {NM_OPENFORTIVPN_KEY_PERSISTENT, "persistent", 0},
};

/* mesmos valores que o serviço aceita como verdadeiro (insecure-ssl antigo era "yes") */
static const char *const truthy[] = {"1", "yes", "true", "on", NULL};

static const char *const min_tls_values[] = {"", "1.0", "1.1", "1.2", "1.3"};

#define N(a) G_N_ELEMENTS(a)

static void openfortivpn_editor_iface_init(NMVpnEditorInterface *iface);

typedef struct {
    GObject parent;
    GtkWidget *root;
    GtkWidget *ent[N(entries)], *chk[N(checks)], *spin[N(spins)];
    GtkWidget *password, *pem, *min_tls;
    GtkWidget *user, *gateway;
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

    guint i;
    NMSettingSecretFlags pem_flags = NM_SETTING_SECRET_FLAG_NONE;
    NMSetting *s_set;

#define W(f, id) self->f = GTK_WIDGET(get_object(b, id))
    W(root, "root");
    W(password, "password");
    W(pem, "pem_passphrase");
    W(min_tls, "min_tls");
    W(otp, "otp");
    W(tfa, "tfa");
    W(saml, "saml");
    W(saml_port, "saml_port");
#undef W
    for (i = 0; i < N(entries); i++) {
        self->ent[i] = GTK_WIDGET(get_object(b, entries[i].id));
        if ((v = get_data(s_vpn, entries[i].key)))
            SET_TEXT(self->ent[i], v);
        g_signal_connect_swapped(self->ent[i], "changed", G_CALLBACK(emit_changed), self);
    }
    self->gateway = self->ent[0];
    self->user = self->ent[1];
    for (i = 0; i < N(checks); i++) {
        self->chk[i] = GTK_WIDGET(get_object(b, checks[i].id));
        v = get_data(s_vpn, checks[i].key);
        SET_ACTIVE(self->chk[i], v ? g_strv_contains(truthy, v) : checks[i].def);
        g_signal_connect_swapped(self->chk[i], "toggled", G_CALLBACK(emit_changed), self);
    }
    for (i = 0; i < N(spins); i++) {
        self->spin[i] = GTK_WIDGET(get_object(b, spins[i].id));
        v = get_data(s_vpn, spins[i].key);
        gtk_spin_button_set_value(GTK_SPIN_BUTTON(self->spin[i]), v ? g_ascii_strtoull(v, NULL, 10) : spins[i].def);
        g_signal_connect_swapped(self->spin[i], "value-changed", G_CALLBACK(emit_changed), self);
    }
    v = get_data(s_vpn, NM_OPENFORTIVPN_KEY_MIN_TLS);
    gtk_combo_box_set_active(GTK_COMBO_BOX(self->min_tls), 0);
    for (i = 1; v && i < N(min_tls_values); i++)
        if (!g_strcmp0(v, min_tls_values[i]))
            gtk_combo_box_set_active(GTK_COMBO_BOX(self->min_tls), i);
    g_object_ref_sink(self->root);

    if (s_vpn && (v = nm_setting_vpn_get_secret(s_vpn, NM_OPENFORTIVPN_KEY_PASSWORD)))
        SET_TEXT(self->password, v);
    if (s_vpn && (v = nm_setting_vpn_get_secret(s_vpn, NM_OPENFORTIVPN_KEY_PEM_PASSPHRASE)))
        SET_TEXT(self->pem, v);

    if ((v = get_data(s_vpn, OTP_FLAGS)))
        SET_ACTIVE(self->otp, (g_ascii_strtoull(v, NULL, 10) & NM_SETTING_SECRET_FLAG_NOT_SAVED) != 0);
    if ((v = get_data(s_vpn, TFA_FLAGS)))
        SET_ACTIVE(self->tfa, (g_ascii_strtoull(v, NULL, 10) & NM_SETTING_SECRET_FLAG_AGENT_OWNED) != 0);
    SET_ACTIVE(self->saml, g_strcmp0(get_data(s_vpn, NM_OPENFORTIVPN_KEY_SAML_LOGIN), "true") == 0);
    if ((v = get_data(s_vpn, NM_OPENFORTIVPN_KEY_SAML_PORT)))
        port = g_ascii_strtoull(v, NULL, 10);
    gtk_spin_button_set_value(GTK_SPIN_BUTTON(self->saml_port), port);

    if (s_vpn) {
        nm_setting_get_secret_flags(NM_SETTING(s_vpn), NM_OPENFORTIVPN_KEY_PASSWORD, &pw_flags, NULL);
        nm_setting_get_secret_flags(NM_SETTING(s_vpn), NM_OPENFORTIVPN_KEY_PEM_PASSPHRASE, &pem_flags, NULL);
    } else
        s_vpn = self->tmp = NM_SETTING_VPN(nm_setting_vpn_new());
    s_set = NM_SETTING(s_vpn);
    nma_utils_setup_password_storage(self->password, pw_flags, s_set,
                                     NM_OPENFORTIVPN_KEY_PASSWORD, TRUE, FALSE);
    nma_utils_setup_password_storage(self->pem, pem_flags, s_set,
                                     NM_OPENFORTIVPN_KEY_PEM_PASSPHRASE, TRUE, FALSE);

    g_signal_connect_swapped(self->password, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->pem, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->min_tls, "changed", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->otp, "toggled", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->tfa, "toggled", G_CALLBACK(emit_changed), self);
    g_signal_connect_swapped(self->saml_port, "value-changed", G_CALLBACK(emit_changed), self);
    g_signal_connect(self->saml, "toggled", G_CALLBACK(saml_toggled), self);
    for (i = 0; i < N(browse_ids); i++) {
        guint j;
        char *bid = g_strconcat(browse_ids[i], "_btn", NULL);

        for (j = 0; j < N(entries); j++)
            if (!strcmp(entries[j].id, browse_ids[i]))
                g_signal_connect(get_object(b, bid), "clicked", G_CALLBACK(browse_clicked), self->ent[j]);
        g_free(bid);
    }
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
    guint i;

    if (!*GET_TEXT(self->gateway)) {
        g_set_error_literal(error, NM_CONNECTION_ERROR, NM_CONNECTION_ERROR_INVALID_PROPERTY,
                            "Gateway não pode ser vazio");
        return FALSE;
    }

    s_vpn = NM_SETTING_VPN(nm_setting_vpn_new());
    g_object_set(s_vpn, NM_SETTING_VPN_SERVICE_TYPE, NM_DBUS_SERVICE_OPENFORTIVPN, NULL);

    for (i = 0; i < N(entries); i++) {
        if (saml && !strcmp(entries[i].key, NM_OPENFORTIVPN_KEY_USER))
            continue;
        t = GET_TEXT(self->ent[i]);
        if (*t)
            nm_setting_vpn_add_data_item(s_vpn, entries[i].key, t);
    }
    if (!saml) {
        t = GET_TEXT(self->password);
        if (*t)
            nm_setting_vpn_add_secret(s_vpn, NM_OPENFORTIVPN_KEY_PASSWORD, t);
        nm_setting_set_secret_flags(NM_SETTING(s_vpn), NM_OPENFORTIVPN_KEY_PASSWORD,
                                    nma_utils_menu_to_secret_flags(self->password), NULL);
    }
    t = GET_TEXT(self->pem);
    if (*t)
        nm_setting_vpn_add_secret(s_vpn, NM_OPENFORTIVPN_KEY_PEM_PASSPHRASE, t);
    nm_setting_set_secret_flags(NM_SETTING(s_vpn), NM_OPENFORTIVPN_KEY_PEM_PASSPHRASE,
                                nma_utils_menu_to_secret_flags(self->pem), NULL);

    for (i = 0; i < N(checks); i++)
        if (GET_ACTIVE(self->chk[i]) != checks[i].def)
            nm_setting_vpn_add_data_item(s_vpn, checks[i].key, checks[i].def ? "0" : "1");
    for (i = 0; i < N(spins); i++) {
        int n = gtk_spin_button_get_value_as_int(GTK_SPIN_BUTTON(self->spin[i]));

        if (n != spins[i].def) {
            char *num = g_strdup_printf("%d", n);

            nm_setting_vpn_add_data_item(s_vpn, spins[i].key, num);
            g_free(num);
        }
    }
    i = gtk_combo_box_get_active(GTK_COMBO_BOX(self->min_tls));
    if (i > 0 && i < N(min_tls_values))
        nm_setting_vpn_add_data_item(s_vpn, NM_OPENFORTIVPN_KEY_MIN_TLS, min_tls_values[i]);

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
