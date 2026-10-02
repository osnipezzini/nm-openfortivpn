#!/usr/bin/env bash
# Diagnóstico / validação da instalação do openfortivpn-nm.
#
# Uso:
#   sudo ./debug-openfortivpn.sh                     valida tudo (root necessário p/ NM/dbus)
#   NM_OPENFORTIVPN_INSTALL_DIR=/opt/... ./debug-openfortivpn.sh   para dir customizado
#
# É read-only: o único efeito é um `systemctl start/stop` do serviço no teste
# final (verificação real do daemon). Pode rodar quantas vezes quiser (idempotente).
set -u

SERVICE_INSTALL_DIR="${NM_OPENFORTIVPN_INSTALL_DIR:-/opt/openfortivpn-nm}"
PYTHON_DIR="${SERVICE_INSTALL_DIR}/python"
PLUGIN_SO="/usr/lib/x86_64-linux-gnu/qt6/plugins/plasma/network/vpn/plasmanetworkmanagement_openfortivpnui.so"
NAME_FILE="/usr/lib/NetworkManager/VPN/nm-openfortivpn-service.name"
DBUS_POLICY="/etc/dbus-1/system.d/org.freedesktop.NetworkManager.openfortivpn.conf"
POLKIT="/usr/share/polkit-1/actions/nm-openfortivpn-service.conf"
UNIT="/etc/systemd/system/nm-openfortivpn-service.service"
UNIT_ALIAS="/etc/systemd/system/dbus-org.freedesktop.NetworkManager.openfortivpn.service"
UNIT_NAME="nm-openfortivpn-service.service"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✔${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }
bad()  { echo -e "  ${RED}✘${NC} $*"; FAIL=1; }

FAIL=0

echo "=============== DIAGNÓSTICO openfortivpn-nm ==============="
echo "  dir dedicado: ${SERVICE_INSTALL_DIR} (run as root sudo p/ teste do daemon)"

echo
echo "· 1) Programas do sistema"
for cmd in openfortivpn; do
    command -v "${cmd}" >/dev/null 2>&1 \
        && ok "${cmd}: $(command -v ${cmd})" \
        || bad "binário '${cmd}' ausente (apt install openfortivpn)"
done
/usr/bin/python3 -c "import gi; gi.require_version('NM','1.0')" >/dev/null 2>&1 \
    && ok "system python3 + PyGObject/libnm" \
    || bad "python3-gi / gir1.2-nm-1.0 ausentes (apt install python3-gi gir1.2-nm-1.0)"

echo
echo "· 2) Plugin plasma (.so)"
if [ -f "${PLUGIN_SO}" ]; then
    ok "${PLUGIN_SO} ($(stat -c %s "${PLUGIN_SO}") bytes)"
else
    bad "plugin não instalado: ${PLUGIN_SO}"
fi

echo
echo "· 3) .name do NetworkManager"
if [ -f "${NAME_FILE}" ]; then
    ok "${NAME_FILE} → program=$(grep '^program' "${NAME_FILE}" | cut -d= -f2)"
    grep -q '^program=/usr/bin/openfortivpn-service' "${NAME_FILE}" \
        || bad "program não aponta para /usr/bin/openfortivpn-service"
else
    bad ".name ausente em ${NAME_FILE}"
fi

echo
echo "· 4) Serviço python (dir dedicado)"
[ -d "${SERVICE_INSTALL_DIR}" ] && ok "dir dedicado: ${SERVICE_INSTALL_DIR}" || bad "dir dedicado ausente"
[ -f "${PYTHON_DIR}/openfortivpn_service/nm/service.py" ] && ok "openfortivpn_service presente" || bad "openfortivpn_service ausente em ${PYTHON_DIR}"
[ -f "${PYTHON_DIR}/openfortivpn_common/__init__.py" ] && ok "openfortivpn_common presente" || bad "openfortivpn_common ausente"
if PYTHONPATH="${PYTHON_DIR}" /usr/bin/python3 -c "from openfortivpn_service.nm.service import run_service" >/dev/null 2>&1; then
    ok "run_service importável (PYTHONPATH=${PYTHON_DIR})"
else
    bad "run_service NÃO importável — confira os pacotes em ${PYTHON_DIR}"
fi

echo
echo "· 5) Wrappers /usr/bin"
for w in /usr/bin/openfortivpn-service /usr/bin/openfortivpn-nm; do
    [ -x "${w}" ] && ok "${w}" || bad "${w} ausente / não-executável"
done

echo
echo "· 6) polkit + policy D-Bus"
[ -f "${POLKIT}" ]    && ok "polkit ${POLKIT}" || bad "polkit ausente: ${POLKIT}"
[ -f "${DBUS_POLICY}" ] && ok "dbus policy ${DBUS_POLICY}" || bad "dbus policy ausente: ${DBUS_POLICY}"

echo
echo "· 7) systemd unit"
[ -f "${UNIT}" ] && ok "unit ${UNIT}" || bad "unit ausente"
[ -L "${UNIT_ALIAS}" ] && ok "alias D-Bus → ${UNIT_ALIAS}" || bad "alias D-Bus ausente (crítico)"
sudo systemctl daemon-reload 2>/dev/null || true
if systemctl show "${UNIT_NAME}" -p LoadState --value 2>/dev/null | grep -q loaded; then
    ok "unit carregada no systemd"
else
    bad "unit não carregada → sudo systemctl daemon-reload"
fi

echo
echo "· 8) Teste real do daemon D-Bus (start + posso parar/stop)"
if [ "$(id -u)" = "0" ]; then
    if systemctl start nm-openfortivpn-service 2>/dev/null; then
        ok "daemon iniciou (systemctl start)"
        sleep 1
        ACTIVE="$(systemctl is-active nm-openfortivpn-service 2>/dev/null || true)"
        echo "     is-active: ${ACTIVE}"
        if busctl --system status org.freedesktop.NetworkManager.openfortivpn >/dev/null 2>&1; then
            ok "nome D-Bus publicado no system bus"
        else
            bad "nome D-Bus NÃO publicado no system bus"
        fi
        echo "--- journal (últimas linhas) ---"
        journalctl -u nm-openfortivpn-service -n 12 --no-pager 2>/dev/null | tail -10 || true
        systemctl stop nm-openfortivpn-service 2>/dev/null || true
    else
        bad "daemon FALHOU ao iniciar — journal:"
        journalctl -u nm-openfortivpn-service -n 60 --no-pager 2>/dev/null | tail -40 || true
    fi
else
    warn "não é root — rode `sudo $0` para o teste final do daemon"
fi

echo
echo "============================================================="
if [ "${FAIL}" = "0" ]; then
    echo -e " ${GREEN} VALIDA.${NC} Teste: System Settings → Rede/Totais → VPN."
else
    echo -e " ${RED} FALHAS acima.${NC} Revise e rode de novo."
    exit 1
fi
