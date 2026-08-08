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
```

## Instalação

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
git clone https://invent.kde.org/network/plasma-nm.git
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
