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
        """Detecta o usuário da sessão gráfica ativa (via logind, que tem
        os dados reais de sessão; o daemon spawnado pelo NM tem USER=root)."""
        try:
            result = subprocess.run(
                ["loginctl", "list-sessions", "--no-legend"],
                capture_output=True, text=True, timeout=5,
            )
        except (FileNotFoundError, OSError):
            result = None

        if result and result.returncode == 0:
            # Linhas: SESSION UID USER SEAT LEADER CLASS TTY IDLE SINCE
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 6:
                    continue
                sid, uid, user, seat, _leader, cls = parts[:6]
                if cls == "user" and seat and seat != "-":
                    return user, uid

        # fallback p/ ambiente local
        for key in ("SUDO_USER", "USER", "LOGNAME"):
            user = os.environ.get(key)
            if user and user != "root":
                return user, ""
        return None, ""

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
        try:
            result = subprocess.run(
                ["systemd-run", "--user", "--collect",
                 "-M", f"{self._uid}@", "xdg-open", url],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                log.info("Browser aberto via systemd --user (%s)", self._uid)
                return True
            log.info("systemd-run falhou: %s", (result.stderr or "").strip())
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
                GLib.Variant("(sssa{sv})", ("", "", url, {})),
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