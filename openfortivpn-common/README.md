# openfortivpn-common

Biblioteca compartilhada para projetos openfortivpn.

## Conteúdo

- `config.py` - VpnConfig: leitura/escrita de config nativo do openfortivpn
- `fields.py` - ConnectionFields e ABCs para editores de conexão VPN

## Uso

```python
from openfortivpn_common.config import VpnConfig
from openfortivpn_common.fields import ConnectionFields, VpnEditorBase
```
