#!/usr/bin/env bash
# Builds the plasma-nm openfortivpn plugin inside Docker.
# The container clones plasma-nm upstream, overlays vpn/openfortivpn from this
# repo, and compiles the plugin (outputs ./dist/...).
#
#   ./build-docker.sh            build the plugin (outputs ./dist/...)
#   ./build-docker.sh --install  build and then install plugin + NM config
#                                on the host (prompts for sudo)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

INSTALL=0
case "${1:-}" in
    --install) INSTALL=1 ;;
    -h|--help)
        echo "Usage: $0 [--install]"
        exit 0
        ;;
    "") ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
esac

plugin_dir="/usr/lib/x86_64-linux-gnu/qt6/plugins/plasma/network/vpn"
name_dir="/usr/share/NetworkManager/VPN"
dbus_policy_dir="/etc/dbus-1/system.d"

echo "==> Building openfortivpn plugin (docker) ..."
export BUILD_UID="$(id -u)" BUILD_GID="$(id -g)"

# Prefer the compose plugin, fall back to standalone docker-compose, and
# finally to plain docker build + docker run (no compose at all).
if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
elif docker-compose version >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
fi

if [ -n "${COMPOSE:-}" ]; then
    "${COMPOSE[@]}" build
    "${COMPOSE[@]}" run --rm build
else
    docker build -t plasma-nm-openfortivpn-builder -f docker/Dockerfile .
    docker run --rm \
        -e BUILD_UID -e BUILD_GID \
        -v "$(pwd):/src" \
        -v "$(pwd)/dist:/dist" \
        plasma-nm-openfortivpn-builder
fi

PLUGIN_SO="$(find dist -maxdepth 1 -name 'plasmanetworkmanagement_openfortivpnui.so' | head -n1)"
if [ -z "${PLUGIN_SO}" ]; then
    echo "error: plugin not found in ./dist/" >&2
    exit 1
fi
echo "==> Built: ${PLUGIN_SO}"

if [ "${INSTALL}" = "1" ]; then
    echo "==> Installing plugin ..."
    sudo install -m755 -D "${PLUGIN_SO}" "${plugin_dir}/${PLUGIN_SO##*/}"

    echo "==> Installing NM .name file ..."
    sudo mkdir -p "${name_dir}"
    if [ -f "${name_dir}/nm-fortisslvpn-service.name" ]; then
        sudo rm -f "${name_dir}/nm-fortisslvpn-service.name"
    fi
    sudo tee "${name_dir}/nm-openfortivpn-service.name" > /dev/null << 'EOF'
[VPN Connection]
name=openfortivpn
service=org.freedesktop.NetworkManager.openfortivpn
program=/usr/libexec/nm-openfortivpn-service
supports-multiple-connections=true
EOF

    echo "==> Installing D-Bus policy ..."
    sudo mkdir -p "${dbus_policy_dir}"
    if [ ! -f "${dbus_policy_dir}/org.freedesktop.NetworkManager.openfortivpn.conf" ]; then
        sudo tee "${dbus_policy_dir}/org.freedesktop.NetworkManager.openfortivpn.conf" > /dev/null << 'EOF'
<!DOCTYPE busconfig PUBLIC
 "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
    <policy user="root">
        <allow own_prefix="org.freedesktop.NetworkManager.openfortivpn"/>
        <allow send_destination="org.freedesktop.NetworkManager.openfortivpn"/>
        <allow send_interface="org.freedesktop.NetworkManager.openfortivpn"/>
    </policy>
    <policy context="default">
        <deny own_prefix="org.freedesktop.NetworkManager.openfortivpn"/>
        <deny send_destination="org.freedesktop.NetworkManager.openfortivpn"/>
    </policy>
</busconfig>
EOF
    fi

    echo "==> Reloading Plasma ..."
    sudo systemctl --user restart plasma-kcmshell6 2>/dev/null || true
    sudo systemctl --user restart plasmashell 2>/dev/null || true

    echo ""
    echo "OpenFortiVPN plugin installed. Make sure the nm-openfortivpn-service"
    echo "binary is installed at /usr/libexec/nm-openfortivpn-service."
fi