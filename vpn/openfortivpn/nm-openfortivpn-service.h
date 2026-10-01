/* nm-openfortivpn-service - OpenFortiVPN integration with NetworkManager

    SPDX-License-Identifier: GPL-2.0-or-later

    SPDX-FileCopyrightText: 2008 Red Hat Inc.
    SPDX-FileCopyrightText: Dan Williams <dcbw@redhat.com>
    SPDX-FileCopyrightText: 2015 Lubomir Rintel <lkundrak@v3.sk>
*/

#ifndef __NM_OPENFORTIVPN_SERVICE_H__
#define __NM_OPENFORTIVPN_SERVICE_H__

/* For the NM <-> VPN plugin service */
#define NM_DBUS_SERVICE_OPENFORTIVPN "org.freedesktop.NetworkManager.openfortivpn"
#define NM_DBUS_INTERFACE_OPENFORTIVPN "org.freedesktop.NetworkManager.openfortivpn"
#define NM_DBUS_PATH_OPENFORTIVPN "/org/freedesktop/NetworkManager/openfortivpn"

#define NM_OPENFORTIVPN_KEY_GATEWAY "gateway"
#define NM_OPENFORTIVPN_KEY_USER "user"
#define NM_OPENFORTIVPN_KEY_PASSWORD "password"
#define NM_OPENFORTIVPN_KEY_OTP "otp"
#define NM_OPENFORTIVPN_KEY_2FA "2fa"
#define NM_OPENFORTIVPN_KEY_CA "ca"
#define NM_OPENFORTIVPN_KEY_CERT "cert"
#define NM_OPENFORTIVPN_KEY_KEY "key"
#define NM_OPENFORTIVPN_KEY_TRUSTED_CERT "trusted-cert"
#define NM_OPENFORTIVPN_KEY_REALM "realm"
#define NM_OPENFORTIVPN_KEY_SAML_LOGIN "saml-login"
#define NM_OPENFORTIVPN_KEY_SAML_PORT "saml-port"

/* Demais opções: mesmo nome da chave do config do openfortivpn (man openfortivpn).
 * Booleanos gravados como "1"/"0"; a UI só grava a chave quando difere do default
 * (entre parênteses). */
#define NM_OPENFORTIVPN_KEY_PEM_PASSPHRASE "pem-passphrase" /* secret */
#define NM_OPENFORTIVPN_KEY_OTP_PROMPT "otp-prompt"
#define NM_OPENFORTIVPN_KEY_OTP_DELAY "otp-delay" /* int (0) */
#define NM_OPENFORTIVPN_KEY_NO_FTM_PUSH "no-ftm-push" /* bool (0) */
#define NM_OPENFORTIVPN_KEY_SNI "sni"
#define NM_OPENFORTIVPN_KEY_INSECURE_SSL "insecure-ssl" /* bool (0) */
#define NM_OPENFORTIVPN_KEY_CIPHER_LIST "cipher-list"
#define NM_OPENFORTIVPN_KEY_MIN_TLS "min-tls" /* "", 1.0, 1.1, 1.2, 1.3 */
#define NM_OPENFORTIVPN_KEY_SECLEVEL_1 "seclevel-1" /* bool (0) */
#define NM_OPENFORTIVPN_KEY_SET_ROUTES "set-routes" /* bool (1) */
#define NM_OPENFORTIVPN_KEY_HALF_INTERNET_ROUTES "half-internet-routes" /* bool (0) */
#define NM_OPENFORTIVPN_KEY_SET_DNS "set-dns" /* bool (1) */
#define NM_OPENFORTIVPN_KEY_USE_RESOLVCONF "use-resolvconf" /* bool (1) */
#define NM_OPENFORTIVPN_KEY_PPPD_USE_PEERDNS "pppd-use-peerdns" /* bool (0) */
#define NM_OPENFORTIVPN_KEY_PPPD_LOG "pppd-log"
#define NM_OPENFORTIVPN_KEY_PPPD_PLUGIN "pppd-plugin"
#define NM_OPENFORTIVPN_KEY_PPPD_IPPARAM "pppd-ipparam"
#define NM_OPENFORTIVPN_KEY_PPPD_IFNAME "pppd-ifname"
#define NM_OPENFORTIVPN_KEY_PPPD_CALL "pppd-call"
#define NM_OPENFORTIVPN_KEY_PPPD_ACCEPT_REMOTE "pppd-accept-remote" /* bool (1) */
#define NM_OPENFORTIVPN_KEY_IFNAME "ifname"
#define NM_OPENFORTIVPN_KEY_PERSISTENT "persistent" /* int segundos (0) */

/* SAML default port */
#define NM_OPENFORTIVPN_SAML_PORT_DEFAULT 8020

#endif /* __NM_OPENFORTIVPN_SERVICE_H__ */