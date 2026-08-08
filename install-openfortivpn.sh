#!/usr/bin/env bash
# Instala o plugin plasma-nm openfortivpn + o backend do NetworkManager
# (serviço openfortivpn em python + daemon D-Bus) de forma idempotente.
#
# Uso:
#   ./install-openfortivpn.sh                 instala tudo (pede sudo)
#   ./install-openfortivpn.sh --dry-run       sugere o que seria feito, sem executar
#   ./install-openfortivpn.sh --skip-plugin-build  só config do NM, sem recompilar plugin
#
# Variável de ambiente opcional:
#   NM_OPENFORTIVPN_PROJECT   diretório com os fontes python do serviço
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DRY_RUN=0
SKIP_PLUGIN=0
for a in "$@"; do
    case "$a" in
        --dry-run) DRY_RUN=1 ;;
        --skip-plugin-build) SKIP_PLUGIN=1 ;;
        *) echo "Argumento desconhecido: $a" >&2; exit 1 ;;
    esac
done

# ----------------------------- configuração -------------------------------
PROJECT="${NM_OPENFORTIVPN_PROJECT:-${SCRIPT_DIR}}"
MINICONDA="${HOME}/miniconda3"
CONDA_ENV="${MINICONDA}/envs/openfortivpn"
PLUGINSO_DIR="/usr/lib/x86_64-linux-gnu/qt6/plugins/plasma/network/vpn"
NM_VPN_DIR="/usr/lib/NetworkManager/VPN"
SERVICE_PROG="/usr/bin/openfortivpn-service"
NM_PROG="/usr/bin/openfortivpn-nm"
UNIT="/etc/systemd/system/nm-openfortivpn-service.service"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✔${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }
err()  { echo -e "  ${RED}✘${NC} $*"; }

run() {
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  (dry-run) $*"
        return 0
    fi
    "$@"
}

# --------------------------- 1. plugin plasma ------------------------------
install_plasma_plugin() {
    echo "==> [1/7] Plugin plasma (plasmanetworkmanagement_openfortivpnui)"
    if [ "${SKIP_PLUGIN}" = "1" ]; then
        ok "pulando build (--skip-plugin-build)"
    elif ! command -v docker >/dev/null 2>&1; then
        warn "docker não instalado; usando .so já existente em ./dist"
    else
        run bash "${SCRIPT_DIR}/build-docker.sh"
    fi

    if [ -f "${SCRIPT_DIR}/dist/plasmanetworkmanagement_openfortivpnui.so" ]; then
        run sudo install -m755 -D "${SCRIPT_DIR}/dist/plasmanetworkmanagement_openfortivpnui.so" \
            "${PLUGINSO_DIR}/plasmanetworkmanagement_openfortivpnui.so"
        ok "plugin instalado em ${PLUGINSO_DIR}"
    else
        err "Sem dist/...so — faça ./build-docker.sh antes ou não use --skip-plugin-build"
        return 1
    fi
}

# --------------------------- 2) arquivo .name -----------------------------
install_nm_name() {
    echo
    echo "==> [2/7] Arquivo .name do NetworkManager"
    cat > /tmp/nm-openfortivpn-service.name <<'EOF'
[VPN Connection]
name=openfortivpn
service=org.freedesktop.NetworkManager.openfortivpn
program=/usr/bin/openfortivpn-service
supports-multiple-connections=true
EOF
    run sudo install -m644 -D /tmp/nm-openfortivpn-service.name "${NM_VPN_DIR}/nm-openfortivpn-service.name"
    ok ".name instalado → ${NM_VPN_DIR} (program=/usr/bin/openfortivpn-service)"
}

# --------------------------- 3) wrappers /usr/bin -------------------------
install_wrappers() {
    echo
    echo "==> [3/7] Wrappers em /usr/bin"
    if [ ! -x "${CONDA_ENV}/bin/python" ]; then
        err "env conda 'openfortivpn' não encontrada em ${CONDA_ENV}"
        return 1
    fi
    if ! /usr/bin/python3 -c "import gi; gi.require_version('NM','1.0')" >/dev/null 2>&1; then
        warn "system python3 sem PyGObject; instalando python3-gi (recomendado)"
        run sudo apt-get install -y --no-install-recommends python3-gi python3-gi-cairo >/dev/null 2>&1 || true
    fi

    # O daemon D-Bus usa libnm via PyGObject (gi). O system python3 já tem o
    # binding; os pacotes do projeto são editable-install, então basta apontar
    # PYTHONPATH para os fontes.
    SRC_PY="${PROJECT}/openfortivpn-service:${PROJECT}/openfortivpn-common"

    cat > /tmp/openfortivpn-service.wrapper <<EOF
#!/usr/bin/env bash
source "${MINICONDA}/etc/profile.d/conda.sh"
conda activate openfortivpn
export PYTHONPATH="${SRC_PY}\${PYTHONPATH:+:\${PYTHONPATH}}"
exec /usr/bin/python3 -m openfortivpn_service.cli "\$@"
EOF

    cat > /tmp/openfortivpn-nm.wrapper <<EOF
#!/usr/bin/env bash
source "${MINICONDA}/etc/profile.d/conda.sh"
conda activate openfortivpn
export PYTHONPATH="${SRC_PY}\${PYTHONPATH:+:\${PYTHONPATH}}"
exec /usr/bin/python3 -m openfortivpn_service.cli --nm-dbus-service "\$@"
EOF

    run sudo install -m755 /tmp/openfortivpn-service.wrapper "${SERVICE_PROG}"
    run sudo install -m755 /tmp/openfortivpn-nm.wrapper "${NM_PROG}"
    ok "${SERVICE_PROG} e ${NM_PROG} criados (system python3 + PyGObject)"
}

# --------------------------- 4) polkit + dbus -----------------------------
install_policy() {
    echo
    echo "==> [4/7] Polkit + policy D-Bus"
    if [ -f "${PROJECT}/openfortivpn-service/data/nm-openfortivpn-service.conf" ]; then
        run sudo install -D "${PROJECT}/openfortivpn-service/data/nm-openfortivpn-service.conf" \
            /usr/share/polkit-1/actions/nm-openfortivpn-service.conf
        ok "polkit action instalado"
    else
        warn "polkit do projeto não encontrado; pulando"
    fi

    if [ ! -f /etc/dbus-1/system.d/org.freedesktop.NetworkManager.openfortivpn.conf ]; then
        run sudo tee /etc/dbus-1/system.d/org.freedesktop.NetworkManager.openfortivpn.conf > /dev/null << 'EOF'
<!DOCTYPE busconfig PUBLIC
 "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
    <policy user="root">
        <allow own_prefix="org.freedesktop.NetworkManager.openfortivpn"/>
        <allow send_destination="org.freedesktop.NetworkManager.openfortivpn"/>
    </policy>
    <policy context="default">
        <deny own_prefix="org.freedesktop.NetworkManager.openfortivpn"/>
        <deny send_destination="org.freedesktop.NetworkManager.openfortivpn"/>
    </policy>
</busconfig>
EOF
        ok "policy D-Bus instalado"
    else
        ok "policy D-Bus já presente"
    fi
}

# --------------------------- 5) systemd unit ------------------------------
install_systemd() {
    echo
    echo "==> [5/7] systemd (nm-openfortivpn-service, ativado via D-Bus)"
    if [ -f "${PROJECT}/openfortivpn-service/systemd/nm-openfortivpn-service.service" ]; then
        run sudo cp "${PROJECT}/openfortivpn-service/systemd/nm-openfortivpn-service.service" "${UNIT}"
    else
        warn "unit do projeto não encontrado; criando unit padrão"
        cat > /tmp/nm-openfortivpn-service.service <<'EOF'
[Unit]
Description=NetworkManager VPN plugin for openfortivpn
After=network.target

[Service]
Type=dbus
BusName=org.freedesktop.NetworkManager.openfortivpn
ExecStart=/usr/bin/openfortivpn-service --nm-dbus-service --bus-name org.freedesktop.NetworkManager.openfortivpn
EOF
        run sudo install -m644 /tmp/nm-openfortivpn-service.service "${UNIT}"
    fi
    # O NetworkManager ativa o plugin via D-Bus; para o systemd conseguir
    # ativá-lo sob demanda precisa do alias 'dbus-org.freedesktop.NetworkManager.openfortivpn.service'.
    run sudo ln -sf "${UNIT}" /etc/systemd/system/dbus-org.freedesktop.NetworkManager.openfortivpn.service
    run sudo systemctl daemon-reload || true
    run sudo systemctl restart NetworkManager || true
    ok "unit + alias D-Bus instalados (ativado sob demanda)"
}

# --------------------------- 6) plugin C libnm ----------------------------
install_libnm_plugin() {
    echo
    echo "==> [6/7] Plugin C libnm (libnm-vpn-plugin-openfortivpn, opcional)"
    C_SO="${PROJECT}/openfortivpn-service/libnm/builddir/libnm-vpn-plugin-openfortivpn.so"
    if [ -f "${C_SO}" ]; then
        run sudo install -m755 "${C_SO}" /usr/lib/x86_64-linux-gnu/NetworkManager/
        ok "libnm plugin C instalado a partir do build existente"
    else
        warn "build do libnm não encontrado; pulando (o daemon python já cobre a conexão)"
    fi
}

# --------------------------- 7) diagnóstico -------------------------------
diagnosis() {
    echo
    echo "==================== DIAGNÓSTICO ===================="
    local fail=0

    echo "· Plugin plasma"
    if [ -f "${PLUGINSO_DIR}/plasmanetworkmanagement_openfortivpnui.so" ]; then ok "plugin .so presente"; else err "plugin .so FALTANDO"; fail=1; fi

    echo "· .name NM"
    if [ -f "${NM_VPN_DIR}/nm-openfortivpn-service.name" ] && grep -q openfortivpn "${NM_VPN_DIR}/nm-openfortivpn-service.name"; then
        ok ".name ok (program=$(grep '^program' "${NM_VPN_DIR}/nm-openfortivpn-service.name" | cut -d= -f2))"
    else err ".name NM FALTANDO"; fail=1; fi

    echo "· programas"
    for p in "${SERVICE_PROG}" "${NM_PROG}"; do
        if [ -x "$p" ]; then ok "$p"; else err "$p FALTANDO"; fail=1; fi
    done

    echo "· daemon D-Bus (gi + libnm no system python3)"
    if /usr/bin/python3 -c "import gi; gi.require_version('NM','1.0')" >/dev/null 2>&1; then
        ok "system python3 + PyGObject ok"
    else
        err "PyGObject ausente no system python3 — instale python3-gi"; fail=1
    fi
    SRC_PY="${PROJECT}/openfortivpn-service:${PROJECT}/openfortivpn-common"
    if PYTHONPATH="${SRC_PY}" /usr/bin/python3 -c "from openfortivpn_service.nm.service import run_service" >/dev/null 2>&1; then
        ok "openfortivpn_service.nm.service importável"
    else
        err "openfortivpn_service.nm.service NÃO importável"; fail=1
    fi

    echo "· systemd"
    if systemctl is-active nm-openfortivpn-service >/dev/null 2>&1; then
        ok "unit ativa"
    elif [ "$(systemctl show nm-openfortivpn-service -p LoadState --value 2>/dev/null)" = "loaded" ]; then
        if [ -L /etc/systemd/system/dbus-org.freedesktop.NetworkManager.openfortivpn.service ]; then
            ok "unit carregada + alias D-Bus ok (ativada sob demanda)"
        else
            err "unit carregada mas SEM alias D-Bus (crítico!)"; fail=1
        fi
    else
        err "unit não carregada — confira /etc/systemd/system/nm-openfortivpn-service.service"; fail=1
    fi

    echo "· plugin libnm C"
    if find /usr/lib /usr/lib/x86_64-linux-gnu -name 'libnm-vpn-plugin-openfortivpn*' 2>/dev/null | grep -q .; then
        ok "libnm-vpn-plugin presente"
    else warn "libnm-vpn-plugin ausente (pode funcionar mesmo assim)"; fi

    echo "· teste real do daemon (systemctl start)"
    if sudo systemctl start nm-openfortivpn-service 2>/dev/null; then
        ok "daemon subiu com sucesso"
        sudo systemctl stop nm-openfortivpn-service 2>/dev/null || true
    else
        err "daemon falhou ao iniciar — veja journal abaixo"; fail=1
    fi

    echo "· Journal (últimas linhas)"
    sudo journalctl -u nm-openfortivpn-service -n 20 --no-pager 2>/dev/null | tail -15 || true

    echo "============================================================="
    if [ "${fail}" = "1" ]; then
        echo -e " ${RED}FALTA CORRIGIR itens acima. Rode de novo.${NC}"
    else
        echo -e " ${GREEN}TUDO OK. Teste: System Settings → Rede → Adicionar...${NC}"
    fi
    echo "=================================================================="
}

# ---------------------------------------------------------------------------
if [ "${DRY_RUN}" = "1" ]; then
    echo ">>> MODO ENSAIO (dry-run) — nada será alterado. <<<"
fi

install_plasma_plugin
install_nm_name
install_wrappers
install_policy
install_systemd
install_libnm_plugin
diagnosis