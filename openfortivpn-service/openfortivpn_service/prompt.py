"""
Dialogo com o usuário, exibido na sessão gráfica ativa (KDE: kdialog).

O daemon é root; o dialogo é disparado no systemd --user do usuário da sessão
gráfica detectado via loginctl (mecanismo análogo ao BrowserOpener).
"""
from __future__ import annotations
import logging
import subprocess

log = logging.getLogger(__name__)

_DIALOG = "/usr/bin/kdialog"


def _desktop_session() -> tuple[str | None, str]:
    """Retorna (usuário, uid) da sessão gráfica ativa via loginctl."""
    try:
        result = subprocess.run(
            ["loginctl", "list-sessions", "--no-legend"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, OSError):
        return None, ""
    if result.returncode != 0:
        return None, ""
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        _sid, uid, user, seat, _leader, cls = parts[:6]
        if cls == "user" and seat and seat != "-":
            return user, uid
    return None, ""


def ask_trust_cert(host: str, digest: str) -> tuple[bool, bool]:
    """
    Pergunta ao usuário se confia no certificado do gateway.

    Retorna (aceito, persistir). `persistir=True` ⇛ o usuário marcou a caixa
    "salvar o hash no trusted-cert" (conexões futuras confiam sem perguntar).
    """
    user, uid = _desktop_session()
    if not uid:
        log.error("Sem sessão gráfica para perguntar sobre o certificado do host %s", host)
        return False, False

    text = (
        f"O certificado do gateway VPN '{host}' não é confiável.\n\n"
        f"SHA-256: {digest}\n\n"
        "Confia neste certificado e deseja conectar?"
    )

    cmd = [
        "systemd-run", "--user", "--collect", "-M", f"{uid}@",
        _DIALOG, "--title", "Conexão VPN (openfortivpn)",
        "--checklist", text,
        "persist", "Salvar o hash no trusted-cert (conexões futuras)", "on",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        log.error("%s não encontrado", _DIALOG)
        return False, False
    except subprocess.TimeoutExpired:
        log.warning("ecg na pergunta sobre o certificado (%s)", host)
        return False, False

    if result.returncode != 0:
        log.info("Usuário não confiou no certificado do host %s", host)
        return False, False

    selected = set(result.stdout.split())
    persist = "persist" in selected
    log.info("Usuário confiou no certificado do host %s (persistir=%s)", host, persist)
    return True, persist