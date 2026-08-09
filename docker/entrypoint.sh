#!/usr/bin/env bash
# Runs inside the container. The openfortivpn widget lives in this repo at
# vpn/openfortivpn, but it only compiles as part of the plasma-nm superproject
# (it links plasmanm_internal/plasmanm_editor and needs the KF6 macros like
# ki18n_wrap_ui). So this script:
#   1. clones plasma-nm (upstream) into the container
#   2. overlays vpn/openfortivpn from /src onto the clone
#   3. registers add_subdirectory(openfortivpn) in the clone's vpn/CMakeLists.txt
#   4. builds the plugin and drops the .so into /dist (host-mounted folder)
set -euo pipefail

SRC="${SRC_DIR:-/src}"
BUILD="${BUILD_DIR:-/build}"
DIST="${DIST_DIR:-/dist}"
TARGET="${TARGET:-plasmanetworkmanagement_openfortivpnui}"
PLASMA_NM_UPSTREAM="${PLASMA_NM_UPSTREAM:-https://github.com/KDE/plasma-nm.git}"
PLASMA_NM_REF="${PLASMA_NM_REF:-v6.6.6}"
CLONE_DIR="${CLONE_DIR:-/plasma-nm}"
WIDGET_SRC="${SRC}/vpn/openfortivpn"

if [ ! -d "${WIDGET_SRC}" ]; then
    echo "error: ${WIDGET_SRC} not found. Mount this repo root at ${SRC}." >&2
    exit 1
fi

echo "==> Cloning plasma-nm upstream (ref: ${PLASMA_NM_REF})..."
rm -rf "${CLONE_DIR}"
git clone --depth 1 --branch "${PLASMA_NM_REF}" "${PLASMA_NM_UPSTREAM}" "${CLONE_DIR}"

echo "==> Overlaying vpn/openfortivpn widget..."
rm -rf "${CLONE_DIR}/vpn/openfortivpn"
cp -r "${WIDGET_SRC}" "${CLONE_DIR}/vpn/openfortivpn"

echo "==> Registering add_subdirectory(openfortivpn)..."
if ! grep -q "add_subdirectory(openfortivpn)" "${CLONE_DIR}/vpn/CMakeLists.txt"; then
    sed -i '1i add_subdirectory(openfortivpn)' "${CLONE_DIR}/vpn/CMakeLists.txt"
fi

echo "==> Applying patches onto the plasma-nm clone ..."
PATCHES_DIR="${PATCHES_DIR:-${SRC}/patches/plasma-nm}"
if [ -d "${PATCHES_DIR}" ]; then
    for PATCH in "${PATCHES_DIR}"/*.patch; do
        [ -f "${PATCH}" ] || continue
        if git -C "${CLONE_DIR}" apply --check --reverse "${PATCH}" >/dev/null 2>&1; then
            echo "    $(basename "${PATCH}"): already applied, skipping"
        else
            git -C "${CLONE_DIR}" apply "${PATCH}"
            echo "    applied $(basename "${PATCH}")"
        fi
    done
else
    echo "    no patches in ${PATCHES_DIR}, skipping"
fi

echo "==> Configuring plasma-nm..."
rm -rf "${BUILD}"
cmake -S "${CLONE_DIR}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DBUILD_MOBILE=OFF \
    -DBUILD_MOBILE_PROVIDER_INFO=OFF \
    -DBUILD_VPN_PLUGINS=ON \
    -DBUILD_OPENCONNECT=OFF \
    -DBUILD_TESTING=OFF

echo "==> Building ${TARGET}..."
if [[ "${BUILD_ALL:-0}" == "1" ]]; then
    # Build completo do plasma-nm (todas as libs/aplicativos — inclui os patches)
    # e instala numa árvore staged em ${DIST}/root, para copiar sobre /usr no host.
    echo "==> BUILD_ALL=1: building the whole plasma-nm ..."
    cmake --build "${BUILD}" -j"$(nproc)"
    echo "==> Installing staged tree into ${DIST}/root ..."
    DESTDIR="${DIST}/root" cmake --install "${BUILD}"
    # paridade: também deixa o plugin ao nível de ./dist para o build-docker.sh
    PLUGIN_FULL="$(find "${BUILD}" -name "${TARGET}.so" -print -quit)"
    if [ -n "${PLUGIN_FULL}" ]; then
        mkdir -p "${DIST}"
        cp -v "${PLUGIN_FULL}" "${DIST}/"
    fi
    echo "==> Staged tree at ${DIST}/root/usr"
else
    cmake --build "${BUILD}" --target "${TARGET}" -j"$(nproc)"

    ARTIFACT="$(find "${BUILD}" -name "${TARGET}.so" -print -quit)"
    if [ -z "${ARTIFACT}" ]; then
        echo "error: ${TARGET}.so not found after build" >&2
        exit 1
    fi

    mkdir -p "${DIST}"
    cp -v "${ARTIFACT}" "${DIST}/"
fi

if [ -n "${BUILD_UID:-}" ]; then
    chown -R "${BUILD_UID}:${BUILD_GID:-${BUILD_UID}}" "${DIST}"
fi

echo ""
echo "==> Done. Plugin at: ${DIST}/$(basename "${ARTIFACT:-plasmanetworkmanagement_openfortivpnui.so}")"
