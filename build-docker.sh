#!/usr/bin/env bash
# Build e instalação completa do plugin openfortivpn para o plasma-nm.
#
# O container clona o plasma-nm upstream, aplica vpn/openfortivpn como overlay,
# aplica os patches em patches/plasma-nm (fix do IP dos detalhes), e compila.
# Em modo --install, também instala POR COMPLETO, com o serviço Python do
# NetworkManager em um diretório dedicado fora de $HOME (default /opt/openfortivpn-nm).
#
#   ./build-docker.sh               build do plugin (dist/…)
#   ./build-docker.sh --install     build + instala TUDO (plugin .so, .name NM,
#                                   serviço python, polkit, dbus policy, systemd)
#   ./build-docker.sh --no-build --install   instala TUDO SEM recompilar
#                                   (reusa dist/plasmanetworkmanagement_openfortivpnui.so já buildado)
#
# Env:
#   NM_OPENFORTIVPN_INSTALL_DIR     dir dedicado do serviço (default /opt/openfortivpn-nm)
#   NM_OPENFORTIVPN_FULL_PLASMA=1   além do plugin, build+instala o plasma-nm
#                                   INTEIRO (com os patches) em /usr — necessário
#                                   para o fix dos detalhes valer no Plasma.
#   PLASMA_NM_UPSTREAM / PLASMA_NM_REF   origem e ref do clone upstream.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Só para nunca rodar "mudo": confirma a raiz do repo e da os próximos passos.
if [ ! -d "openfortivpn-service" ] || [ ! -d "patches" ]; then
    echo "erro: este não é o diretório-raiz do repo (faltam openfortivpn-service/ e patches/)." >&2
    echo "      rode o script de DENTRO da pasta do projeto:  ~/projetos/sodevs/openfortivpn-nm/" >&2
    exit 1
fi
echo "→ repo root: ${PWD}"

INSTALL=0
NO_BUILD=0
for a in "${@:-}"; do
    case "$a" in
        --install) INSTALL=1 ;;
        --no-build|--skip-build) NO_BUILD=1 ;;
        -h|--help)
            echo "Uso: $0 [--install] [--no-build]"
            echo "Env: NM_OPENFORTIVPN_INSTALL_DIR, NM_OPENFORTIVPN_FULL_PLASMA, PLASMA_NM_UPSTREAM, PLASMA_NM_REF"
            exit 0
            ;;
        --*) echo "Argumento desconhecido: $a" >&2; exit 1 ;;
    esac
done

# ----------------------------- configuração -------------------------------
plugin_dir="/usr/lib/x86_64-linux-gnu/qt6/plugins/plasma/network/vpn"
name_dir="/usr/share/NetworkManager/VPN"
dbus_policy_dir="/etc/dbus-1/system.d"
polkit_dir="/usr/share/polkit-1/actions"
unit_dir="/etc/systemd/system"

SERVICE_INSTALL_DIR="${NM_OPENFORTIVPN_INSTALL_DIR:-/opt/openfortivpn-nm}"
PYTHON_DIR="${SERVICE_INSTALL_DIR}/python"
SERVICE_PROG="/usr/bin/openfortivpn-service"
NM_PROG="/usr/bin/openfortivpn-nm"
NM_BUS="org.freedesktop.NetworkManager.openfortivpn"
FULL_PLASMA="${NM_OPENFORTIVPN_FULL_PLASMA:-0}"

# Trava de segurança: o instalador faz `rm -rf` no dir dedicado.
if [[ "${SERVICE_INSTALL_DIR}" == "/" || "${SERVICE_INSTALL_DIR}" == "$HOME" || "${SERVICE_INSTALL_DIR}" == "$HOME/"* || -z "${SERVICE_INSTALL_DIR}" ]]; then
    echo "erro: NM_OPENFORTIVPN_INSTALL_DIR inválido (não pode ser / nem \$HOME): ${SERVICE_INSTALL_DIR}" >&2
    exit 1
fi

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✔${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }
err()  { echo -e "  ${RED}✘${NC} $*"; }

# ----------------------------- build docker -------------------------------

build_plugin() {
    echo "==> Building openfortivpn plugin (docker) ..."
    export BUILD_UID="$(id -u)" BUILD_GID="$(id -g)"
    export BUILD_ALL="${FULL_PLASMA:-0}"
    export PATCHES_DIR  # pass-through se definido, senão default no entrypoint

    # Prefer compose, fall back to plain docker build + run.
    if docker compose version >/dev/null 2>&1; then
        docker compose build
        docker compose run --rm build
    elif docker-compose version >/dev/null 2>&1; then
        docker-compose build
        docker-compose run --rm build
    else
        docker build -t plasma-nm-openfortivpn-builder -f docker/Dockerfile .
        docker run --rm \
            -e BUILD_UID -e BUILD_GID -e BUILD_ALL -e PATCHES_DIR \
            -v "$(pwd):/src" \
            -v "$(pwd)/dist:/dist" \
            plasma-nm-openfortivpn-builder
    fi

    PLUGIN_SO="$(find dist -maxdepth 1 -name 'plasmanetworkmanagement_openfortivpnui.so' 2>/dev/null | head -n1 || true)"
    if [ -z "${PLUGIN_SO}" ]; then
        err "plugin não encontrado em ./dist/ — build falhou?"
        return 1
    fi
    echo "==> Built: ${PLUGIN_SO}"
}

# ------------------------------ instalação --------------------------------

install_plugin() {
    echo "==> Plugin plasma ..."
    sudo install -m755 -D "${PLUGIN_SO}" "${plugin_dir}/${PLUGIN_SO##*/}"
    ok "plugin instalado em ${plugin_dir}"
}

install_gtk_plugins() {
    echo "==> Plugins GTK (libnm-vpn-plugin-openfortivpn* em /usr/lib/NetworkManager) ..."
    local gtk_dir="/usr/lib/NetworkManager"
    sudo mkdir -p "${gtk_dir}"

    local count=0
    for so in dist/libnm-vpn-plugin-openfortivpn.so \
              dist/libnm-vpn-plugin-openfortivpn-editor.so \
              dist/libnm-gtk4-vpn-plugin-openfortivpn-editor.so; do
        if [ -f "${so}" ]; then
            sudo install -m644 "${so}" "${gtk_dir}/${so##*/}"
            count=$((count + 1))
        fi
    done

    if [ ${count} -gt 0 ]; then
        ok "${count} plugin(s) GTK instalado(s) em ${gtk_dir}"
    else
        warn "nenhum plugin GTK encontrado em dist/"
    fi
}

install_auth_dialog() {
    echo "==> Wrapper auth-dialog (/usr/libexec/nm-openfortivpn-auth-dialog) ..."
    local wrapper="/usr/libexec/nm-openfortivpn-auth-dialog"
    sudo mkdir -p "$(dirname "${wrapper}")"
    sudo tee "${wrapper}" > /dev/null <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${PYTHON_DIR}\${PYTHONPATH:+:\${PYTHONPATH}}"
exec /usr/bin/python3 -m openfortivpn_service.auth_dialog "\$@"
EOF
    sudo chmod 755 "${wrapper}"
    ok "auth-dialog wrapper instalado em ${wrapper}"
}

install_name() {
    echo "==> Arquivo .name do NetworkManager ..."
    sudo mkdir -p "${name_dir}"
    if [ -f "${name_dir}/nm-fortisslvpn-service.name" ]; then
        sudo rm -f "${name_dir}/nm-fortisslvpn-service.name"
    fi
    sudo tee "${name_dir}/nm-openfortivpn-service.name" > /dev/null << 'EOF'
[VPN Connection]
name=openfortivpn
service=org.freedesktop.NetworkManager.openfortivpn
program=/usr/bin/openfortivpn-service
supports-multiple-connections=true
EOF
    ok ".name instalado → ${name_dir}"
}

install_service_dedicated() {
    echo "==> Serviço Python em dir dedicado ${SERVICE_INSTALL_DIR} ..."
    echo "    (usa system python3 + PyGObject/libnm; sem conda, sem $HOME)"
    if ! /usr/bin/python3 -c "import gi; gi.require_version('NM','1.0')" >/dev/null 2>&1; then
        warn "system python3 sem PyGObject/libnm — tentando instalar"
        sudo apt-get install -y --no-install-recommends python3-gi python3-gi-cairo gir1.2-nm-1.0 >/dev/null 2>&1 \
            || warn "apt falhou — instale manualmente: python3-gi gir1.2-nm-1.0"
    fi

    sudo rm -rf "${SERVICE_INSTALL_DIR}"
    sudo install -d -m755 "${SERVICE_INSTALL_DIR}" "${PYTHON_DIR}"

    sudo cp -r openfortivpn-service/openfortivpn_service "${PYTHON_DIR}/"
    sudo cp -r openfortivpn-common/openfortivpn_common   "${PYTHON_DIR}/"
    sudo chown -R root:root "${PYTHON_DIR}"
    ok "pacotes python em ${PYTHON_DIR}"

    # wrappers /usr/bin (system python3 + PYTHONPATH apontando pro dir dedicado)
    # Escritores via mktemp (em /tmp, dono = usuário) → sudo install; o rm não
    # precisa de sudo e não falha com permission em /usr.
    SERVICE_WRAP="$(mktemp)"
    cat > "${SERVICE_WRAP}" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${PYTHON_DIR}\${PYTHONPATH:+:\${PYTHONPATH}}"
exec /usr/bin/python3 -m openfortivpn_service.cli "\$@"
EOF
    sudo install -m755 "${SERVICE_WRAP}" "${SERVICE_PROG}"
    rm -f "${SERVICE_WRAP}"

    NM_WRAP="$(mktemp)"
    cat > "${NM_WRAP}" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${PYTHON_DIR}\${PYTHONPATH:+:\${PYTHONPATH}}"
exec /usr/bin/python3 -m openfortivpn_service.cli --nm-dbus-service "\$@"
EOF
    ok "${SERVICE_PROG} e ${NM_PROG} criados"
}

install_openfortivpn_cli() {
    echo "==> binário openfortivpn (CLI) ..."
    if command -v openfortivpn >/dev/null 2>&1; then
        ok "openfortivpn já no PATH: $(command -v openfortivpn)"
        return 0
    fi
    warn "openfortivpn ausente — instalando via apt"
    sudo apt-get update -qq >/dev/null 2>&1 || true
    if ! sudo apt-get install -y --no-install-recommends openfortivpn >/dev/null 2>&1; then
        warn "apt falhou — instale manualmente: sudo apt install openfortivpn"
        return 0
    fi
    if command -v openfortivpn >/dev/null 2>&1; then
        ok "openfortivpn instalado: $(command -v openfortivpn)"
    fi
}

install_policy() {
    echo "==> Polkit + policy D-Bus ..."
    if [ -f "openfortivpn-service/data/nm-openfortivpn-service.conf" ]; then
        sudo install -m644 -D "openfortivpn-service/data/nm-openfortivpn-service.conf" \
            "${polkit_dir}/nm-openfortivpn-service.conf"
    else
        warn "polkit do projeto não encontrado — pulando"
    fi

    if [ ! -f "${dbus_policy_dir}/org.freedesktop.NetworkManager.openfortivpn.conf" ]; then
        if [ -f "docker/dbus/org.freedesktop.NetworkManager.openfortivpn.conf" ]; then
            sudo install -m644 -D "docker/dbus/org.freedesktop.NetworkManager.openfortivpn.conf" \
                "${dbus_policy_dir}/org.freedesktop.NetworkManager.openfortivpn.conf"
        else
            sudo tee "${dbus_policy_dir}/org.freedesktop.NetworkManager.openfortivpn.conf" > /dev/null << 'EOF'
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
        fi
    fi
    ok "polkit + policy D-Bus ok"
}

install_systemd() {
    echo "==> systemd unit (ativação sob demanda via D-Bus) ..."
    sudo tee "${unit_dir}/nm-openfortivpn-service.service" > /dev/null << 'EOF'
[Unit]
Description=NetworkManager VPN plugin for openfortivpn
After=network.target

[Service]
Type=dbus
BusName=org.freedesktop.NetworkManager.openfortivpn
ExecStart=/usr/bin/openfortivpn-service --nm-dbus-service --bus-name org.freedesktop.NetworkManager.openfortivpn

[Install]
WantedBy=multi-user.target
EOF
    sudo ln -sf "${unit_dir}/nm-openfortivpn-service.service" \
        "${unit_dir}/dbus-org.freedesktop.NetworkManager.openfortivpn.service"
    sudo systemctl daemon-reload || true
    ok "unit + alias D-Bus instalados"
}

install_full_plasma() {
    if [ "${FULL_PLASMA}" != "1" ]; then
        return 0
    fi
    echo "==> Instalando plasma-nm completo (construído com os patches) em /usr ..."
    if [ ! -d "dist/root/usr" ]; then
        if [ "${NO_BUILD}" = "1" ]; then
            warn "--no-build: dist/root/usr não existe — pulando o plasma-nm completo."
            return 0
        fi
        err "árvore staged não encontrada em dist/root/usr — build completo falhou?"
        return 1
    fi
    sudo cp -a "dist/root/usr/." /usr/
    ok "plasma-nm rebuild instalado — faça RE-LOGIN da sessão para recarregar as libs."
}

restart_services() {
    echo "==> Reiniciando serviços ..."
    sudo systemctl daemon-reload || true
    sudo systemctl restart NetworkManager 2>/dev/null || true
    sudo systemctl --user restart plasma-kcmshell6 2>/dev/null || true
    sudo systemctl --user restart plasmashell 2>/dev/null || true
}

# ------------------------------ execução --------------------------------
echo "→ args: ${*:-NENHUM} | install=$([ "${INSTALL}" = "1" ] && echo sim || echo nao) | no-build=$([ "${NO_BUILD}" = "1" ] && echo sim || echo nao)"
if [ "${NO_BUILD}" = "1" ]; then
    PLUGIN_SO="$(find dist -maxdepth 1 -name 'plasmanetworkmanagement_openfortivpnui.so' 2>/dev/null | head -n1 || true)"
    if [ -z "${PLUGIN_SO}" ]; then
        err "sem build: não há .so em ./dist/ (rode ./build-docker.sh antes, ou remova --no-build)"
        exit 1
    fi
    echo "==> --no-build: usando plugin existente: ${PLUGIN_SO}"
else
    build_plugin
fi
if [ "${INSTALL}" = "1" ]; then
    echo
    echo "========== Instalação completa (plugin + serviço) =========="
    install_openfortivpn_cli
    install_plugin
    install_gtk_plugins
    install_auth_dialog
    install_name
    install_service_dedicated
    install_policy
    install_systemd
    install_full_plasma
    restart_services

    echo ""
    echo "Instalação concluída."
    echo "  · serviço Python dedicado: ${SERVICE_INSTALL_DIR}"
    echo "  · valide com:              sudo ./debug-openfortivpn.sh"
    if [ "${FULL_PLASMA}" = "1" ]; then
        echo "  · plasma-nm rebuilt instalado — faça re-login da sessão."
    fi
else
    echo ""
    if [ "${NO_BUILD}" = "1" ]; then
        echo "Plugin existente reutilizado (sem novo build). Use --install para instalar tudo."
    else
        echo "Apenas build do plugin (instalação não executada). Use --install para instalar tudo."
    fi
fi