"""
Armazenamento persistente de certificados confiáveis (hash trust-cert).

O daemon roda como root; grava em /var/lib/nm-openfortivpn/trusted-certs.json.
Em execuções sem privilégio (testes/dev) usa ~/.config/nm-openfortivpn/trusted-certs.json.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_JSON_PATH = Path("/var/lib/nm-openfortivpn/trusted-certs.json")


def _store_path() -> Path:
    try:
        _JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        probe = _JSON_PATH.parent / ".write-test"
        probe.write_text("")
        probe.unlink()
        return _JSON_PATH
    except PermissionError:
        fallback = Path.home() / ".config" / "nm-openfortivpn" / "trusted-certs.json"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback


def _load() -> dict:
    path = _store_path()
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        log.exception("falha ao ler %s", path)
        return {}


def _save(data: dict) -> None:
    path = _store_path()
    try:
        path.write_text(json.dumps(data, indent=2) + "\n")
    except OSError:
        log.exception("falha ao gravar %s", path)


def key_for(host: str, port: int | str) -> str:
    """Chave do certificado: host:porta (sem normalizar)."""
    return f"{host}:{port}"


def get_trusted(host: str, port: int | str) -> list[str]:
    """Digests confiados para o gateway (host:porta)."""
    return list(_load().get(key_for(host, port), []))


def add_trusted(host: str, port: int | str, digest: str) -> None:
    data = _load()
    key = key_for(host, port)
    digests = data.setdefault(key, [])
    if digest not in digests:
        digests.append(digest)
        _save(data)
        log.info("Certificado confiado salvo: key=%s digest=%s", key, digest[:16])


if __name__ == "__main__":
    print("path:", _store_path())