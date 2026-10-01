# Patches aplicados sobre o plasma-nm upstream (clone no docker build)

O `docker/entrypoint.sh` aplica estes patches sobre o clone do plasma-nm
(default `KDE/plasma-nm`, tag `v6.6.6`) **antes** do `cmake configure`, de
forma idempotente (`git apply` com checagem reversa para não duplicar).

## 0001-connectiondetails-vpn-ip-config.patch

**Sintoma:** com a VPN conectada, a janela de detalhes do applet/KCM não mostra
IP, gateway nem DNS da VPN.

**Causa:** `getConnectionDetails()` (`libs/editor/connectiondetails.cpp`) só lê
IP do `device` e só monta a seção se `device->activeConnection()` for a conexão
exibida. VPN não tem device próprio: o `NetworkModel` mantém o item sem
`devicePath`, e o `Devices` da conexão ativa da VPN é o device **pai**
(wlan0/eth0), cuja conexão ativa é o Wi-Fi/cabo — não a VPN. A configuração IP
do túnel fica na própria conexão ativa da VPN (`ActiveConnection::ipV4Config()`).
Além disso, a linha "IPv4 Address" exigia `isGlobal()`, falso para RFC1918.

**Correção:** para VPN, acha a conexão ativa pelo UUID e usa o
`ipV4Config()`/`ipV6Config()` dela; mostra o IPv4 mesmo privado (pula só
loopback/link-local/multicast/broadcast). Substitui os antigos 0001
(fallback de device, que pegava o device pai) e 0002.

## Regenerar / validar

Os patches foram gerados com `git format-patch` contra a tag `v6.6.6` e
validados com `git apply --check`. Para validar de novo contra outra ref:

```bash
git clone --depth 1 --branch v6.6.6 https://github.com/KDE/plasma-nm.git /tmp/pnm
cd /tmp/pnm
for p in /path/to/patches/plasma-nm/*.patch; do git apply --check "$p"; done
```

## Aviso sobre o runtime

O `.deb` e o `build-docker.sh` entregam apenas o plugin
`plasmanetworkmanagement_openfortivpnui.so`. O código alterado vive nas libs
compartilhadas do plasma-nm (`libplasmanm_internal`/`libplasmanm_editor`, as
libs `models`/`editor`). Para o fix valer no Plasma do host é preciso que o
plasma-nm instalado venha da árvore com os patches aplicados — por exemplo
rebuild completo do plasma-nm a partir do clone patchado dentro do container
(`cmake --build ... --target all && cmake --install ...`) e substituir as
libs do sistema (ou `apt build-dep plasma-nm` + build local). Sem isso, o
applet continua usando as libs antigas do KDE e o IP segue vazio.
