#!/usr/bin/env bash
# Empacota openfortivpn-nm (UI plasma + serviço D-Bus) em um único .deb.
#
# O pacote contém:
#   · plugin plasma  plasmanetworkmanagement_openfortivpnui.so
#   · plugins GTK    libnm-vpn-plugin-openfortivpn.so + editores (GTK3, GTK4)
#   · wrapper auth-dialog /usr/libexec/nm-openfortivpn-auth-dialog
#   · .name do NetworkManager (program=/usr/bin/openfortivpn-service)
#   · wrappers /usr/bin/openfortivpn-service e /usr/bin/openfortivpn-nm
#   · pacotes python openfortivpn_service + openfortivpn_common no dist-packages
#   · polkit action + policy D-Bus + unit systemd (ativação sob demanda)
#
# Uso:
#   ./package-deb.sh             builda o plugin (docker) + gera o .deb em ./dist/
#   ./package-deb.sh --no-build  usa o dist/*.so existente, sem rebuild
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

NO_BUILD=0
for a in "$@"; do
    case "$a" in
        --no-build) NO_BUILD=1 ;;
        -h|--help) sed -n '1,12p' "$0"; exit 0 ;;
        *) echo "Argumento desconhecido: $a" >&2; exit 1 ;;
    esac
done

ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
VERSION="0.1.0"
PKG="openfortivpn-nm_${VERSION}_${ARCH}.deb"
OUT_DIR="dist"

PLUGIN_SO="dist/plasmanetworkmanagement_openfortivpnui.so"
PLUGIN_DEST="usr/lib/x86_64-linux-gnu/qt6/plugins/plasma/network/vpn"
GTK_SO_BASE="dist/libnm-vpn-plugin-openfortivpn"
GTK_DEST="usr/lib/NetworkManager"
NAME_DEST="usr/lib/NetworkManager/VPN"
PY_DEST="usr/lib/python3/dist-packages"
WRAPPER_SERVICE="usr/bin/openfortivpn-service"
WRAPPER_NM="usr/bin/openfortivpn-nm"
WRAPPER_AUTH="usr/libexec/nm-openfortivpn-auth-dialog"
POLKIT_DEST="usr/share/polkit-1/actions"
DBUS_DEST="etc/dbus-1/system.d"
SYSTEMD_DEST="lib/systemd/system"

# ------------------------------ 1. plugins .so (plasma + GTK) ----------------
echo "==> [1/6] Plugins .so (plasma + GTK)"
if [ ! -f "${PLUGIN_SO}" ] && [ "${NO_BUILD}" = "0" ]; then
    bash ./build-docker.sh
elif [ ! -f "${PLUGIN_SO}" ]; then
    echo "error: ${PLUGIN_SO} não existe. Rode ./build-docker.sh antes." >&2
    exit 1
fi
echo "  ok: ${PLUGIN_SO}"

[ -f "${GTK_SO_BASE}.so" ] || echo "  warning: ${GTK_SO_BASE}.so não encontrado — pacote sem editor GTK"

# ------------------------------ 2. árvore ----------------------------------
echo "==> [2/6] Montando árvore do pacote"
ROOT="$(mktemp -d /tmp/openfortivpn-nm-deb.XXXXXX)"
trap 'rm -rf "${ROOT}"' EXIT

install -m755 -D "${PLUGIN_SO}" "${ROOT}/${PLUGIN_DEST}/plasmanetworkmanagement_openfortivpnui.so"

# Install GTK plugins if they exist
if [ -f "${GTK_SO_BASE}.so" ]; then
    install -m644 -D "${GTK_SO_BASE}.so" "${ROOT}/${GTK_DEST}/libnm-vpn-plugin-openfortivpn.so"
fi
if [ -f "${GTK_SO_BASE}-editor.so" ]; then
    install -m644 -D "${GTK_SO_BASE}-editor.so" "${ROOT}/${GTK_DEST}/libnm-vpn-plugin-openfortivpn-editor.so"
fi
if [ -f "dist/libnm-gtk4-vpn-plugin-openfortivpn-editor.so" ]; then
    install -m644 -D "dist/libnm-gtk4-vpn-plugin-openfortivpn-editor.so" "${ROOT}/${GTK_DEST}/libnm-gtk4-vpn-plugin-openfortivpn-editor.so"
fi

mkdir -p "${ROOT}/usr/libexec"
cat > "${ROOT}/${WRAPPER_AUTH}" <<'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 -m openfortivpn_service.auth_dialog "$@"
EOF
chmod 755 "${ROOT}/${WRAPPER_AUTH}"

install -m644 -D openfortivpn-service/data/nm-openfortivpn-service.name "${ROOT}/${NAME_DEST}/nm-openfortivpn-service.name"

# pacotes python -> dist-packages (system python3, sem conda)
install -m644 -D openfortivpn-common/openfortivpn_common/__init__.py "${ROOT}/${PY_DEST}/openfortivpn_common/__init__.py"
install -m644 -D openfortivpn-common/openfortivpn_common/config.py   "${ROOT}/${PY_DEST}/openfortivpn_common/config.py"
for f in openfortivpn-service/openfortivpn_service/*.py; do
    install -m644 -D "$f" "${ROOT}/${PY_DEST}/openfortivpn_service/$(basename "$f")"
done
for f in openfortivpn-service/openfortivpn_service/nm/*.py; do
    install -m644 -D "$f" "${ROOT}/${PY_DEST}/openfortivpn_service/nm/$(basename "$f")"
done

# wrappers /usr/bin
mkdir -p "${ROOT}/usr/bin"
cat > "${ROOT}/${WRAPPER_SERVICE}" <<'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 -m openfortivpn_service.cli "$@"
EOF
cat > "${ROOT}/${WRAPPER_NM}" <<'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 -m openfortivpn_service.cli --nm-dbus-service "$@"
EOF
chmod 755 "${ROOT}/${WRAPPER_SERVICE}" "${ROOT}/${WRAPPER_NM}"

# polkit + dbus + systemd
install -m644 -D openfortivpn-service/data/nm-openfortivpn-service.conf \
    "${ROOT}/${POLKIT_DEST}/nm-openfortivpn-service.conf"

install -m644 -D docker/dbus/org.freedesktop.NetworkManager.openfortivpn.conf \
    "${ROOT}/${DBUS_DEST}/org.freedesktop.NetworkManager.openfortivpn.conf"

install -m644 -D openfortivpn-service/systemd/nm-openfortivpn-service.service \
    "${ROOT}/${SYSTEMD_DEST}/nm-openfortivpn-service.service"

echo "  árvore em ${ROOT}"

# ------------------------------ 3. control ----------------------------------
echo "==> [3/6] DEBIAN/control"
mkdir -p "${ROOT}/DEBIAN"
cat > "${ROOT}/DEBIAN/control" <<EOF
Package: openfortivpn-nm
Version: ${VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-3.0, gir1.2-nm-1.0, network-manager, openfortivpn
Recommends: libnma0, libnma-gtk4-0, kdialog | zenity
Maintainer: Osni Pezzini <osni@example.com>
Description: openfortivpn VPN support for Plasma NetworkManager
 Plasma widget (editor de conexão + SAML) e backend de serviço D-Bus para
 conexões FortiGate via openfortivpn, integrados ao NetworkManager do Plasma 6.
EOF

# ------------------------------ 4. conffiles --------------------------------
echo "==> [4/6] DEBIAN/conffiles"
cat > "${ROOT}/DEBIAN/conffiles" <<EOF
/etc/dbus-1/system.d/org.freedesktop.NetworkManager.openfortivpn.conf
EOF

# ------------------------------ 5. postinst ---------------------------------
echo "==> [5/6] DEBIAN/postinst"
cat > "${ROOT}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
# alias D-Bus -> ativação sob demanda pelo systemd
ln -sf /lib/systemd/system/nm-openfortivpn-service.service \
    /etc/systemd/system/dbus-org.freedesktop.NetworkManager.openfortivpn.service
systemctl daemon-reload >/dev/null 2>&1 || true
systemctl restart NetworkManager >/dev/null 2>&1 || true
exit 0
EOF
chmod 755 "${ROOT}/DEBIAN/postinst"

# ------------------------------ 6. dpkg-deb --------------------------------
echo "==> [6/6] Gerando ${OUT_DIR}/${PKG}"
mkdir -p "${OUT_DIR}"
dpkg-deb --root-owner-group --build "${ROOT}" "${OUT_DIR}/${PKG}" >/dev/null
dpkg-deb --info "${OUT_DIR}/${PKG}" | sed -n '1,12p'
echo
echo "OK: ${OUT_DIR}/${PKG}"
