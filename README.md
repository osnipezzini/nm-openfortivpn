# openfortivpn-nm

Plugin de rede do Plasma (plasma-nm) para conexões FortiGate via `openfortivpn`,
com backend de serviço em Python + daemon D-Bus para o NetworkManager.

Este é um monorepo enxuto com o **código necessário** para o plugin funcionar.
Ele NÃO contém o fork inteiro do plasma-nm — apenas o widget e o serviço.

## Estrutura

```
vpn/openfortivpn/          Widget Qt6 (editor de conexão + auth SAML)
                          → compila apenas dentro do superprojeto plasma-nm
openfortivpn-service/     Daemon D-Bus (python) + plugin libnm do NM
openfortivpn-common/      VpnConfig — estrutura de config compartilhada
docker/ + build-docker.sh Build do widget em container (clona plasma-nm upstream)
install-openfortivpn.sh   Instalação idempotente (plugin .so + serviço + NM)
package-deb.sh           Gera um .deb com UI + serviço + config (teste/instalação fácil)
```

## Build do widget (docker)

```bash
./build-docker.sh         # gera ./dist/plasmanetworkmanagement_openfortivpnui.so
```

O container clona o plasma-nm **upstream** (default `KDE/plasma-nm` tag `v6.6.6`,
compatível com KF6 6.24 do Ubuntu 26.04), aplica `vpn/openfortivpn` como overlay,
registra o `add_subdirectory(openfortivpn)` e compila só o plugin.

Env opcionais do build: `PLASMA_NM_UPSTREAM`, `PLASMA_NM_REF` (tag/branch).

## Pacote .deb

```bash
./package-deb.sh              # build docker + gera dist/openfortivpn-nm_*.deb
./package-deb.sh --no-build   # reusa o dist/*.so existente (mais rápido)
```

O pacote contém: plugin plasma `.so`, `.name` do NM, wrappers `/usr/bin`,
pacotes python no dist-packages, polkit, policy D-Bus e unit systemd
(ativação sob demanda). Dependências: `python3-gi`, `gir1.2-nm-1.0`,
`network-manager`, `openfortivpn`.

```bash
sudo dpkg -i dist/openfortivpn-nm_*.deb   # instala
# desinstala com: sudo apt purge openfortivpn-nm
```

## Instalação (script manual, alternativa ao .deb)

```bash
./install-openfortivpn.sh             # instala tudo (pede sudo)
./install-openfortivpn.sh --dry-run   # ensaio, sem alterar nada
```

O script:
1. Builda o plugin plasma via `build-docker.sh` (ou usa `dist/*.so` existente)
2. Instala o `.name` do NetworkManager
3. Cria os wrappers `/usr/bin/openfortivpn-service` e `/usr/bin/openfortivpn-nm`
4. Instala polkit + policy D-Bus + unit systemd (ativação sob demanda)
5. Diagnostica a instalação

## Build do widget (opcional, sem docker)

O widget exige o superprojeto plasma-nm:

```bash
git clone https://github.com/KDE/plasma-nm.git
cp -r vpn/openfortivpn plasma-nm/vpn/openfortivpn
# adicionar `add_subdirectory(openfortivpn)` em plasma-nm/vpn/CMakeLists.txt
cd plasma-nm/build && cmake .. -DBUILD_VPN_PLUGINS=ON && make plasmanetworkmanagement_openfortivpnui
```

## Dependências do serviço

- Python >= 3.11 (system python3)
- PyGObject (`python3-gi`) com libnm bindings
- Env conda `openfortivpn` (default) com os pacotes `openfortivpn-service` +
  `openfortivpn-common` instalados em editable mode
- `openfortivpn` (CLI) no PATH
