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
./build-docker.sh --install   # build + instalação COMPLETA na máquina (VM)
./build-docker.sh --no-build --install   # instala TUDO SEM recompilar (reusa o .so em ./dist)
sudo ./debug-openfortivpn.sh # valida a instalação (read-only, roda quantas vezes quiser)
```

O container clona o plasma-nm **upstream** (default `KDE/plasma-nm` tag `v6.6.6`,
compatível com KF6 6.24 do Ubuntu 26.04), aplica `vpn/openfortivpn` como overlay,
aplica os patches em `patches/plasma-nm/` (ver abaixo), registra o
`add_subdirectory(openfortivpn)` e compila o plugin.

Env opcionais do build: `PLASMA_NM_UPSTREAM`, `PLASMA_NM_REF` (tag/branch).

## Instalação completa na VM (`./build-docker.sh --install`)

Além do plugin `.so`, instala **todo o backend** com o serviço Python em um
diretório dedicado **fora de `$HOME`** (sem conda, sem editable-links):

- plugin → `/usr/lib/.../qt6/plugins/plasma/network/vpn/`
- `.name` do NM + policy D-Bus + polkit (dos `data/` e `docker/dbus/`)
- serviço Python copiado para o dir dedicado
  `NM_OPENFORTIVPN_INSTALL_DIR` (default `/opt/openfortivpn-nm/python`)
- wrappers `/usr/bin/openfortivpn-service` e `/usr/bin/openfortivpn-nm`
  usando **system python3** (sem conda) com `PYTHONPATH` apontando pro dir
- unit systemd `nm-openfortivpn-service` + alias D-Bus (ativação sob demanda)
- reinicia NetworkManager e o Plasma

Validação: `sudo ./debug-openfortivpn.sh` — checa plugin, `.name`, pacotes do
serviço, wrappers, polkit/dbus, unit systemd e faz um teste real de
`systemctl start` do daemon (mostra o journal).

### Opcional: rebuildar o plasma-nm inteiro (fix do IP valer no Plasma)

O código do bug (IP vazio nos detalhes) vive nas **libs do plasma-nm**
(`models`/`editor`), não no widget. Para o fix valer é preciso instalar as
libs construídas com os patches:

```bash
NM_OPENFORTIVPN_FULL_PLASMA=1 ./build-docker.sh --install   # build all + instala em /usr
```

O container então compila o projeto inteiro (ainda com os patches) e entrega a
árvore staged em `dist/root/usr`, que o script copia sobre `/usr`. **Faça
re-login** da sessão depois. Isso substitui as libs do plasma-nm do sistema
pela versão com o patch.

## Patches sobre o plasma-nm (IP dos detalhes da VPN)

Corrige o bug de **IP vazio nos detalhes** da conexão VPN no applet:

1. `patches/plasma-nm/0001-networkmodelitem-vpn-device-fallback.patch` — resolve o
   device do túnel (`ppp0`/`tun0`) via `ActiveConnection::devices()` ao montar os
   detalhes, já que os itens VPN ficam sem `devicePath` no modelo.
2. `patches/plasma-nm/0002-connectiondetails-show-private-ipv4.patch` — mostra o
   IPv4 mesmo quando privado (RFC1918): o antigo `QHostAddress::isGlobal()` ocultava
   o IP de túneis (ex.: `10.255.255.1`).

Veja `patches/plasma-nm/README.md` para detalhes, regeneração e o aviso sobre a
necessidade de rebuild do plasma-nm no host para o fix valer no Plasma instalado.

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

- Python >= 3.11 (system python3) — usado pelos wrappers do `build-docker.sh --install`
- PyGObject (`python3-gi`) com libnm bindings (`gir1.2-nm-1.0`)
- `openfortivpn` (CLI) no PATH
- (caminho dev `install-openfortivpn.sh`: pacotes editable no projeto/conda;
  caminho de deploy `build-docker --install`: pacotes em `/opt/openfortivpn-nm/python`, sem conda)
