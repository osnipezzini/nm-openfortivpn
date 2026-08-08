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
cmake --build "${BUILD}" --target "${TARGET}" -j"$(nproc)"

ARTIFACT="$(find "${BUILD}" -name "${TARGET}.so" -print -quit)"
if [ -z "${ARTIFACT}" ]; then
    echo "error: ${TARGET}.so not found after build" >&2
    exit 1
fi

mkdir -p "${DIST}"
cp -v "${ARTIFACT}" "${DIST}/"

if [ -n "${BUILD_UID:-}" ]; then
    chown -R "${BUILD_UID}:${BUILD_GID:-${BUILD_UID}}" "${DIST}"
fi

echo ""
echo "==> Done. Plugin at: ${DIST}/$(basename "${ARTIFACT}")"
