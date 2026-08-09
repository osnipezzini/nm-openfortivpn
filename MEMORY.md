# MEMORY — Contexto do Projeto plasma-nm / OpenFortiVPN

> Documento de memória do agente. Mantém o contexto do trabalho já feito,
> arquitetura, decisões e pendências. Atualizar sempre que algo mudar.

## Visão geral

Este repositório é um **fork do plasma-nm** (KDE) com um **plugin VPN OpenFortiVPN** adicionado.
O objetivo é integrar o `openfortivpn` ao NetworkManager do Plasma (UI no applet/kcm) usando um
**daemon D-Bus em Python** que atua como plugin de VPN do NM.

- Remote `origin`: `git@github.com:osnipezzini/plasma-nm.git`
- Remote `upstream`: `https://github.com/KDE/plasma-nm.git`
- Branch atual: `master`
- Base do upstream: master (fork commit `4a6e95b47 "Criado plugin dedicado ao OpenFortiVPN"`)

## Restrições do ambiente do agente

- **O agente está rodando em um HOME VIRTUAL.** Só tem acesso garantido a
  `/home/osni/projetos/sodevs/plasma-nm/`. NÃO tentar acessar pastas fora disso
  (ex.: `~/projetos/sodevs/nm_openfortivpn`, conda, `/usr/lib/...`) — elas podem
  não existir no filesystem virtual.
- **Todo teste/build deve ser feito via DOCKER.** Não há toolchain Qt6/KF6 no host
  do agente (nada de `g++`, `cmake`, `qt6-*` direto). Para testar código C++ do
  plugin, usar o container `plasma-nm-openfortivpn-builder`.
- Pedir ao usuário quando precisar de informações do host real (journal do
  systemd, estado da VPN, `nmcli`, etc.).

## Arquitetura / fluxo da VPN

1. **Usuario conecta** a conexão VPN no Plasma (applet ou System Settings).
2. O plugin de VPN do NM (daemon D-Bus, código Python em outro repo
   `nm_openfortivpn`) é chamado pelo NetworkManager via D-Bus.
3. O daemon executa `/usr/bin/openfortivpn` e publica o IP config via
   `set_ip4_config` (libnm/NmVpnServicePlugin). O NM cria o device `ppp0`
   (tipo Ppp, marcado "external"). Obs.: para VPN, `networkmodel.cpp` **não**
   associa device ao item (ver "Pendências/Investigação").
4. Interface de rede é publicada corretamente — o journal mostra
   `address=10.255.255.1`, `gateway=138.94.113.106`, `dns=8.8.8.8`.

## Componentes deste repo

- `vpn/openfortivpn/` — widget QML editor do plugin (Qt6). Alvo:
  `plasmanetworkmanagement_openfortivpnui.so`.
- `vpn/openfortivpn/CMakeLists.txt` — MODULE library; liga com `plasmanm_internal`,
  `plasmanm_editor`, KF6 providers; instala em `${KDE_INSTALL_PLUGINDIR}/plasma/network/vpn`.
- `CMakeLists.txt` (raiz) — `project(plasma-networkmanagement)`, versão 6.6.80,
  **modificado**: KF6 find_package NÃO exige KCMUtils nem Svg (apenas se
  `BUILD_MOBILE`); ordem: `ColorScheme Completion CoreAddons DBusAddons I18n
  JobWidgets KIO NetworkManagerQt Notifications Service Solid WidgetsAddons
  WindowSystem ModemManagerQt`.
- `vpn/CMakeLists.txt` — `add_subdirectory(openfortivpn)` adicionado.
- `build-docker.sh` — build via docker (usa compose se disponível). Sem args
  só builda o widget; com `--install` faz **instalação completa**: plugin `.so`,
  `.name` do NM, wrappers, polkit/dbus, unit systemd e o serviço Python num
  **dir dedicado fora de $HOME** (`NM_OPENFORTIVPN_INSTALL_DIR`, default
  `/opt/openfortivpn-nm`, sem conda; system python3 + PYTHONPATH pro dir).
  Env `NM_OPENFORTIVPN_FULL_PLASMA=1` → build do plasma-nm inteiro (com os
  patches) e instala em `/usr` (necessário pro fix dos detalhes valer). Tem
  trava de segurança p/ não `rm -rf` `/`/`$HOME`.
- `debug-openfortivpn.sh` — diagnóstico read-only da instalação (plugin, `.name`,
  pacotes, wrappers, polkit/dbus, unit systemd) + teste real do daemon
  (`systemctl start` e journal). Rodar `sudo ./debug-openfortivpn.sh`.
- `install-openfortivpn.sh` — caminho DEV/conda (editable no `$HOME`/miniconda).
  Não usa o dir dedicado. Em geral prefira `build-docker.sh --install` na VM.
- `install-openfiventivpn.sh` — script antigo/legacy (nome com typo), não usar.
- `build-test/`, `vpn/build/` — árvores de build locais (gitignored no gitignore
  via `/build*`).

## Build via Docker

- `./build-docker.sh` — usa `docker compose` (ou `docker-compose`, ou docker
  puro). Compose mounts `./` → `/src` e `./dist` → `/dist`. Env repassadas:
  `BUILD_UID`/`BUILD_GID`, `BUILD_ALL` (full em), `PATCHES_DIR`.
- Entrypoint aplica os patches do repo (`patches/plasma-nm/*.patch`) no clone
  ANTES do `cmake configure` (idempotente: `git apply`, re-check se já aplicado).
  Se `BUILD_ALL=1` faz `cmake --build` de tudo e `cmake --install` com DESTDIR
  `$DIST/root` (árvore `dist/root/usr` para copiar no host), além de deixar o
  plugin `.so` ao nível de `./dist`.
- `docker/Dockerfile` — base `ubuntu:26.04`, instala todo o toolchain Qt6/KF6
  (qt6-base-dev, qt6-declarative-dev, qtkeychain-qt6-dev, qcoro-qt6-dev,
  libnm-dev, libssl-dev, libkf6*-dev, libplasma-dev, etc.). Entrypoint:
  `/usr/local/bin/plasma-nm-build`.
- `docker/entrypoint.sh` — roda `cmake -S /src -B /build` com
  `-DBUILD_VPN_PLUGINS=ON -DBUILD_OPENCONNECT=OFF -DBUILD_TESTING=OFF`, build o
  alvo `plasmanetworkmanagement_openfortivpnui`, copia o `.so` para `/dist`
  (mount host `./dist`). Entradas por env: `SRC_DIR`, `BUILD_DIR`, `DIST_DIR`,
  `TARGET`, `BUILD_UID`/`BUILD_GID`.
- `.dockerignore` — `.git`, `build*`, `dist`, `docker/README.md`.

Imagem local: `plasma-nm-openfortivpn-builder`. Para testar código Qt/C++ direto
no container (ex.: comportamento de `QHostAddress`) sem rebuild:
```
docker run --rm -v "$PWD:/src" -w /src plasma-nm-openfortivpn-builder bash -c 'g++ ... && ./bin'
```
Dica: usar `$(pkg-config --cflags --libs Qt6Network)` para compilar test com Qt. O
repo raiz precisa estar montado em `/src` (entrypoint exige `CMakeLists.txt`).

## Serviço / daemon Python (repo `nm_openfortivpn` — NÃO acessível ao agente)

- Módulo: `openfortivpn_service.nm.service.run_service` (importado no diagnóstico).
- Pacotes: `openfortivpn-service` (daemon) e `openfortivpn-common` (VpnConfig).
- Wrappers `/usr/bin` fazem `conda activate openfortivpn` + `PYTHONPATH=...` +
  `exec /usr/bin/python3 -m openfortivpn_service.cli`.
  `NM_OPENFORTIVPN_PROJECT` aponta o projeto python, que tem
  `data/nm-openfortivpn-service.conf` (polkit) e `systemd/...service`.
- O daemon publica `set_ip4_config` (com `address=10.255.255.1`, gateway, dns) —
  **isto está funcionando** (observado no journal do host).

## Pendências / Investigações

### IP blank no detalhes da VPN (causa confirmada + fix entregue)

**Causa raiz confirmada (código upstream v6.6.6):**
- `networkmodel.cpp::addActiveConnection` (`libs/models/networkmodel.cpp`) pula o
  device para VPN ("Not necessary to have device for VPN connections") → o item
  VPN fica com `devicePath` vazio.
- `networkmodelitem.cpp::detailsList()` chama `findNetworkInterface(m_devicePath)`
  com path vazio → `device == nullptr`.
- `connectiondetails.cpp::getConnectionDetails()` só monta a seção IPv4 se
  `device && device->ipV4Config().isValid() && isConnectionActive` → nunca roda
  para VPN → seção IP vazia.
- **Bug secundário:** mesmo com o device, `QHostAddress::isGlobal()` é `false`
  para RFC1918 (ex. `10.255.255.1`) → o endereço era ocultado. Gateway/DNS não
  tinham esse filtro.

**Correção implementada (neste monorepo):** patches aplicados no clone upstream
durante o docker build:
- `patches/plasma-nm/0001-networkmodelitem-vpn-device-fallback.patch` — em
  `detailsList()`, resolve o device do túnel via `ActiveConnection::devices()`
  quando o item é VPN/WireGuard e `devicePath` vazio.
- `patches/plasma-nm/0002-connectiondetails-show-private-ipv4.patch` — mostra o
  IPv4 atribuído mesmo privado (pula só loopback/link-local/multicast/broadcast).

**Aviso runtime:** o `.deb`/build entrega só o widget; o fix vive nas libs
`models`/`editor` do plasma-nm. Para valer no host, rebuild do plasma-nm com os
patches (ver `patches/plasma-nm/README.md`).

Arquivos-chave (upstream):
  - `libs/models/networkmodelitem.cpp` — `detailsList()`
  - `libs/editor/connectiondetails.cpp` — seção IPv4
  - `libs/models/networkmodel.cpp` — `addActiveConnection` (pula device na VPN)

## Root-cause já descartada

- `QHostAddress::isGlobal()` em `connectiondetails.cpp` — para um IP privado
  (RFC1918, ex. 10.255.255.1), `isGlobal()` retorna `false`, o que ocultaria
  o endereço. **CONFIRMADO como bug secundário** e corrigido no patch 0002.
- O caso principal (devicePath vazio) confirmado e corrigido no patch 0001.

## Decisões técnicas

- Plugin vpn compilado como parte do superprojeto plasma-nm (cmake na raiz);
  não tem como build binário isolado (usa macros/do superprojeto).
- Correções no código do plasma-nm são entregues como **patches** em
  `patches/plasma-nm/` (gerados com `git format-patch` contra v6.6.6) e
  aplicados no `docker/entrypoint.sh` antes do configure.
- Base image Docker = mesma distro do host (26.04) para garantir ABI.
- Python do serviço usa system python3 + PyGObject (gi) para libnm, não o
  conda python (para evitar mismatch com o libnm instalado).

## Git log (relevante)

- `4a6e95b47` Criado plugin dedicado ao OpenFortiVPN (commit original do fork).
- Upstream recentes: `86e96ac83` GIT_SILENT Sync po/docbooks, `45cd79a1d` Fix
  SecretAgents::killDialogs, ...

---

_Última atualização: 2026-08-08. Trabalho atual acontece neste monorepo
`openfortivpn-nm` (branch `fix/ip-detalhes-vpn`), que contém só o widget
`vpn/openfortivpn` + serviço python; o plasma-nm inteiro é clonado no
docker build e os fixes no código dele são entregues como patches._