"""
Serviço D-Bus para NetworkManager VPN plugin.
"""
from __future__ import annotations
import logging
import signal
import sys

import gi
gi.require_version("NM", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gio, NM

from openfortivpn_service.nm.plugin import OpenFortivpnPlugin, SERVICE_NAME

log = logging.getLogger(__name__)


def run_service(bus_name: str | None = None):
    """Inicia o serviço D-Bus e roda o loop principal."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    name = bus_name or SERVICE_NAME
    log.info("Iniciando serviço NM VPN: %s", name)

    plugin = OpenFortivpnPlugin(service_name=name)

    # O init (GInitable) do NMVpnServicePlugin exporta a interface
    # org.freedesktop.NetworkManager.VPN.Plugin em
    # /org/freedesktop/NetworkManager/VPN/Plugin e requisita o nome D-Bus.
    # Requer root: usuário comum não pode ser dono de org.freedesktop.NetworkManager.*
    try:
        Gio.Initable.init(plugin, None)
    except GLib.Error as e:
        log.error("Falha ao registrar plugin D-Bus: %s", e.message)
        return 1

    if plugin.get_connection() is None:
        log.error("Falha ao registrar plugin D-Bus: sem conexão")
        return 1

    log.info("Serviço D-Bus registrado com sucesso: %s", name)

    loop = GLib.MainLoop()

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, loop.quit)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, loop.quit)

    try:
        loop.run()
    finally:
        loop.quit()
    return 0