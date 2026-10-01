"""
Dialogo com o usuário, exibido na sessão gráfica ativa (kdialog ou zenity).

O daemon é root; o dialogo é disparado no systemd --user do usuário da sessão
gráfica detectado via loginctl (mecanismo análogo ao BrowserOpener).
"""
from __future__ import annotations
import logging
import os
import subprocess

log = logging.getLogger(__name__)

_DIALOG = "/usr/bin/kdialog"
_ZENITY = "/usr/bin/zenity"


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

    title = "Conexão VPN (openfortivpn)"
    label = "Salvar o hash no trusted-cert (conexões futuras)"
    if os.path.exists(_DIALOG):
        dialog = [_DIALOG, "--title", title, "--separate-output", "--checklist", text,
                  "persist", label, "on"]
    elif os.path.exists(_ZENITY):
        dialog = [_ZENITY, "--list", "--checklist", "--title", title, "--text", text,
                  "--column", "", "--column", "id", "--column", "Opção",
                  "--hide-column=2", "--print-column=2", "TRUE", "persist", label]
    else:
        log.error("nem %s nem %s encontrados", _DIALOG, _ZENITY)
        return False, False

    cmd = [
        # --wait --pipe: espera a resposta e repassa exit code/stdout do diálogo
        # (sem isso o systemd-run retorna 0 na hora e a resposta se perde).
        "systemd-run", "--user", "--collect", "--wait", "--pipe", "--quiet",
        "-M", f"{uid}@", *dialog,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        log.error("systemd-run não encontrado")
        return False, False
    except subprocess.TimeoutExpired:
        log.warning("ecg na pergunta sobre o certificado (%s)", host)
        return False, False

    if result.returncode != 0:
        log.info("Usuário não confiou no certificado do host %s", host)
        return False, False

    selected = {s.strip('"') for s in result.stdout.replace("|", " ").split()}
    persist = "persist" in selected
    log.info("Usuário confiou no certificado do host %s (persistir=%s)", host, persist)
    return True, persist