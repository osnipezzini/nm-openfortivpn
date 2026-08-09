# Patches aplicados sobre o plasma-nm upstream (clone no docker build)

O `docker/entrypoint.sh` aplica estes patches sobre o clone do plasma-nm
(default `KDE/plasma-nm`, tag `v6.6.6`) **antes** do `cmake configure`, de
forma idempotente (`git apply` com checagem reversa para não duplicar).

## 0001-networkmodelitem-vpn-device-fallback.patch

**Sintoma:** com a VPN conectada, a janela de detalhes do applet não mostra a
seção IPv4/IPv6 (fica vazia) para conexões VPN.

**Causa:** o `NetworkModel` mantém itens VPN *sem* `devicePath`
(`addActiveConnection` em `libs/models/networkmodel.cpp` comentava "not
necessary to have device for VPN connections"). Então
`NetworkModelItem::detailsList()` chamava
`findNetworkInterface(m_devicePath)` com path vazio → `device == nullptr` →
`getConnectionDetails()` nunca chegava ao `ipV4Config()` do device (o IP
"vive" na interface do túnel, `ppp0/tun0`).

**Correção:** em `detailsList()`, quando o item é VPN/WireGuard e o
`devicePath` está vazio, resolve o device a partir do
`ActiveConnection::devices()` do túnel antes de montar os detalhes.

## 0002-connectiondetails-show-private-ipv4.patch

**Sintoma:** mesmo com o device do túnel resolvido, o endereço IPv4 da VPN
não aparecia.

**Causa:** a linha "IPv4 Address" exigia `QHostAddress::isGlobal()`, que é
`false` para endereços privados RFC1918 (ex.: `10.255.255.1`) — o caso mais
comum de túnel VPN. Gateway e nameservers não tinham esse filtro, então a
linha do IP ficava inconsistente com o resto da seção.

**Correção:** mostrar o endereço atribuído independente de ser público/privado,
pulando apenas endereços inúteis (loopback, link-local, multicast, broadcast).

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
