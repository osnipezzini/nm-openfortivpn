"""
Orquestrador principal que une CLI args, config, e processo VPN.
"""
from __future__ import annotations
import logging
import signal
import sys
from pathlib import Path

import gi
gi.require_version("GLib", "2.0")
from gi.repository import GLib

from openfortivpn_common.config import VpnConfig

log = logging.getLogger(__name__)


class VpnCore:
    def __init__(self, args):
        self._args = args
        self._vpn_proc = None
        self._loop: GLib.MainLoop | None = None
        self._setup_logging()

    def _setup_logging(self):
        level = logging.WARNING
        if self._args.verbosity >= 2:
            level = logging.DEBUG
        elif self._args.verbosity == 1:
            level = logging.INFO
        if self._args.quiet:
            level = logging.ERROR

        logging.basicConfig(
            level=level,
            format="%(levelname)s: %(message)s"
        )

    def _args_to_config(self) -> VpnConfig:
        """Converte argparse.Namespace para VpnConfig."""
        cfg = VpnConfig()

        # Parse host:port
        if self._args.host_port:
            if ":" in self._args.host_port:
                host, port = self._args.host_port.split(":", 1)
                cfg.host = host
                try:
                    cfg.port = int(port)
                except ValueError:
                    log.error("Porta inválida: %s", port)
                    sys.exit(1)
            else:
                cfg.host = self._args.host_port

        # Conexão
        if self._args.username:
            cfg.username = self._args.username
        if self._args.password:
            cfg.password = self._args.password
        if self._args.realm:
            cfg.realm = self._args.realm
        if self._args.ifname:
            cfg.ifname = self._args.ifname
        if self._args.persistent:
            cfg.persistent = self._args.persistent

        # Autenticação especial
        if self._args.cookie:
            cfg.cookie = self._args.cookie
        if self._args.saml_login:
            cfg.saml_login = self._args.saml_login
        if self._args.pinentry:
            cfg.pinentry = self._args.pinentry
        if self._args.otp:
            cfg.otp = self._args.otp
        if self._args.otp_prompt:
            cfg.otp_prompt = self._args.otp_prompt
        if self._args.otp_delay:
            cfg.otp_delay = self._args.otp_delay
        if self._args.no_ftm_push:
            cfg.no_ftm_push = True

        # TLS / Certificados
        if self._args.ca_file:
            cfg.ca_file = self._args.ca_file
        if self._args.user_cert:
            cfg.user_cert = self._args.user_cert
        if self._args.user_key:
            cfg.user_key = self._args.user_key
        if self._args.pem_passphrase:
            cfg.pem_passphrase = self._args.pem_passphrase
        if self._args.trusted_cert:
            cfg.trusted_cert = self._args.trusted_cert
        if self._args.insecure_ssl:
            cfg.insecure_ssl = True
        if self._args.cipher_list:
            cfg.cipher_list = self._args.cipher_list
        if self._args.min_tls:
            cfg.min_tls = self._args.min_tls
        if self._args.seclevel_1:
            cfg.seclevel_1 = True

        # Rede
        if self._args.set_routes is not None:
            cfg.set_routes = self._args.set_routes
        if self._args.no_routes:
            cfg.no_routes = True
        if self._args.half_internet_routes is not None:
            cfg.half_internet_routes = self._args.half_internet_routes
        if self._args.set_dns is not None:
            cfg.set_dns = self._args.set_dns
        if self._args.no_dns:
            cfg.no_dns = True
        if self._args.use_resolvconf is not None:
            cfg.use_resolvconf = self._args.use_resolvconf

        # pppd
        if self._args.pppd_use_peerdns is not None:
            cfg.pppd_use_peerdns = self._args.pppd_use_peerdns
        if self._args.pppd_no_peerdns:
            cfg.pppd_use_peerdns = 0
        if self._args.pppd_log:
            cfg.pppd_log = self._args.pppd_log
        if self._args.pppd_plugin:
            cfg.pppd_plugin = self._args.pppd_plugin
        if self._args.pppd_ipparam:
            cfg.pppd_ipparam = self._args.pppd_ipparam
        if self._args.pppd_ifname:
            cfg.pppd_ifname = self._args.pppd_ifname
        if self._args.pppd_call:
            cfg.pppd_call = self._args.pppd_call
        if self._args.pppd_accept_remote is not None:
            cfg.pppd_accept_remote = self._args.pppd_accept_remote
        if self._args.ppp_system:
            cfg.ppp_system = self._args.ppp_system

        # Verbosidade
        if self._args.use_syslog:
            cfg.use_syslog = True
        cfg.verbosity = self._args.verbosity

        return cfg

    def run(self) -> int:
        """Ponto de entrada principal. Retorna exit code."""
        cfg = self._args_to_config()

        if not cfg.host:
            log.error("Gateway não especificado")
            return 1

        config_file = cfg.to_tempfile()
        log.info("Config file temporário: %s", config_file)

        from openfortivpn_service.process import VpnProcess

        self._vpn_proc = VpnProcess(
            config_file=config_file,
            saml_port=cfg.saml_login,
            on_connected=self._on_connected,
            on_disconnected=self._on_disconnected,
            on_error=self._on_error,
        )

        if not self._vpn_proc.start():
            return 1

        self._loop = GLib.MainLoop()
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._loop.quit)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._loop.quit)

        try:
            self._loop.run()
        except KeyboardInterrupt:
            log.info("Interrupção recebida")
        finally:
            if self._vpn_proc:
                self._vpn_proc.stop()
            self._loop.quit()

        return 0

    def _on_connected(self):
        log.info("VPN conectada com sucesso")

    def _on_disconnected(self):
        log.info("VPN desconectada")
        if self._loop:
            self._loop.quit()

    def _on_error(self, msg: str):
        log.error("Erro VPN: %s", msg)
