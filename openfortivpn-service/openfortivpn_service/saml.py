"""
Fluxo SAML para openfortivpn.
"""
from __future__ import annotations
import json
import logging
import os
import re
import subprocess
import threading
from pathlib import Path

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gio
from openfortivpn_service.prompt import _desktop_session

log = logging.getLogger(__name__)

# O openfortivpn (>=1.24) imprime:  Authenticate at 'https://.../remote/saml/start...'
# Versões antigas podiam usar:      Please open the following URL: https://...
SAML_URL_PATTERNS = (
    re.compile(r"Authenticate at\s+'?([^'\s]*https?://\S+)'?"),
    re.compile(r"Please open the following URL:\s*(https?://\S+)"),
)

PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT = "/org/freedesktop/portal/desktop"
PORTAL_IFACE_URI = "org.freedesktop.portal.OpenURI"


def extract_saml_url(line: str) -> str | None:
    """Extrai a URL SAML de uma linha de stdout/stderr do openfortivpn."""
    for pattern in SAML_URL_PATTERNS:
        m = pattern.search(line)
        if m:
            return m.group(1).strip("'\"").strip()
    return None


class BrowserOpener:
    """
    Abre uma URL no browser do usuário da sessão gráfica ativa.
    """

    def __init__(self):
        self._session_user, self._uid = self._detect_desktop_session()
        self._dbus = self._bus_address_for()
        log.info(
            "BrowserOpener: user=%s uid=%s dbus=%s",
            self._session_user, self._uid, self._dbus,
        )

    # ------------------------------------------------------------ detecção
    @staticmethod
    def _detect_desktop_session() -> tuple[str | None, str]:
        """Usa a mesma detecção logind do diálogo de certificado."""
        return _desktop_session()

    def _bus_address_for(self) -> str | None:
        if addr := os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            return addr
        if self._uid:
            sock = Path(f"/run/user/{self._uid}/bus")
            if sock.exists():
                return f"unix:path={sock}"
        return None

    # --------------------------------------------------------------- ações
    def open(self, url: str) -> None:
        log.info("Abrindo URL SAML no browser da sessão do usuário: %s", url)

        def _do():
            # Prioridade: systemd-run no user manager (herda DISPLAY/Wayland
            # da sessão), depois portal OpenURI, depois runuser/xdg-open.
            if self._uid and self._uid != str(os.getuid()):
                if self._open_via_systemd_run(url):
                    return
                if self._open_via_portal(url):
                    return
                if self._open_via_runuser(url):
                    return
            else:
                if self._open_via_portal(url):
                    return
                try:
                    subprocess.Popen(["xdg-open", url])
                except OSError as e:
                    log.error("Falha ao abrir browser via xdg-open: %s", e)
            log.error("NENHUM método abriu o browser; URL SAML: %s", url)

        threading.Thread(target=_do, daemon=True).start()

    def _open_via_systemd_run(self, url: str) -> bool:
        runner = ["systemd-run", "--user", "--collect", "--wait", "--pipe",
                  "--quiet", "-M", f"{self._uid}@"]
        try:
            # Consulte a preferência na sessão do usuário, não na conta root.
            default = subprocess.run(
                [*runner, "xdg-mime", "query", "default", "x-scheme-handler/https"],
                capture_output=True, text=True, timeout=10,
            )
            commands = []
            # No Cinnamon, xdg-open/gio pode retornar sucesso sem encaminhar
            # a URL à janela existente. O comando remoto do Firefox abre a aba.
            if default.returncode == 0 and default.stdout.strip() == "firefox.desktop":
                commands.append(["firefox", "--new-tab", url])
            commands.append(["xdg-open", url])
            for command in commands:
                result = subprocess.run(
                    [*runner, *command], capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    log.info("%s concluiu via systemd --user (%s)", command[0], self._uid)
                    return True
                log.info("%s falhou: %s", command[0], (result.stderr or "").strip())
        except Exception as e:
            log.info("systemd-run indisponível: %s", e)
        return False

    def _open_via_portal(self, url: str) -> bool:
        if not self._dbus:
            return False
        try:
            conn = Gio.DBusConnection.new_for_address_sync(
                self._dbus,
                Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT,
                None, None,
            )
            conn.call_sync(
                PORTAL_BUS_NAME, PORTAL_OBJECT, PORTAL_IFACE_URI, "OpenURI",
                GLib.Variant("(ssa{sv})", ("", url, {})),
                Gio.DBusCallFlags.NONE, 8000, None,
            )
            log.info("Browser aberto via portal OpenURI")
            return True
        except GLib.Error as e:
            log.info("portal OpenURI indisponível: %s", e.message)
        except Exception as e:
            log.info("portal OpenURI erro: %s", e)
        return False

    def _open_via_runuser(self, url: str) -> bool:
        try:
            env = os.environ.copy()
            if self._dbus:
                env["DBUS_SESSION_BUS_ADDRESS"] = self._dbus
            result = subprocess.run(
                ["runuser", "-u", self._session_user,
                 "--", "xdg-open", url],
                env=env, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                log.info("Browser aberto via runuser (%s)", self._session_user)
                return True
            log.info("runuser falhou: %s", (result.stderr or "").strip())
        except Exception as e:
            log.info("runuser indisponível: %s", e)
        return False
