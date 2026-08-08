"""
Plugin VPN para NetworkManager via pygobject / libnm.
"""
from __future__ import annotations
import logging
import threading

import gi
gi.require_version("NM", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import NM, GLib

from openfortivpn_common.config import VpnConfig
from openfortivpn_service import certstore, prompt
from openfortivpn_service.process import VpnProcess

log = logging.getLogger(__name__)

SERVICE_NAME = "org.freedesktop.NetworkManager.openfortivpn"


def _ip_bytes(ip: str) -> bytes | None:
    try:
        import socket
        return socket.inet_aton(ip)
    except OSError:
        return None


def _ipv4_uint(ip: str) -> int:
    """Converte '10.0.0.1' no uint32 em network byte order esperado pelo NM."""
    packed = _ip_bytes(ip)
    return int.from_bytes(packed, "big") if packed else 0


class OpenFortivpnPlugin(NM.VpnServicePlugin):
    """
    Implementa NM.VpnServicePlugin — a interface que o NetworkManager
    chama para controlar o ciclo de vida da VPN.
    """

    def __init__(self, service_name: str = SERVICE_NAME):
        super().__init__(service_name=service_name)
        self._vpn_proc: VpnProcess | None = None
        self._connection: NM.Connection | None = None
        self._last_cfg: VpnConfig | None = None

    def do_connect(self, connection: NM.Connection) -> bool:
        log.info("NM solicitou conexão: %s", connection.get_id())
        self._connection = connection
        s_vpn = connection.get_setting_vpn()
        cfg = self._setting_to_config(s_vpn)
        return self._start_vpn(cfg)

    def do_connect_interactive(
        self, connection: NM.Connection, details: GLib.Variant
    ) -> bool:
        return self.do_connect(connection)

    def do_disconnect(self) -> bool:
        log.info("NM solicitou desconexão")
        if self._vpn_proc:
            self._vpn_proc.stop()
            self._vpn_proc = None
        return True

    def do_need_secrets(
        self, connection: NM.Connection, setting_name: str
    ) -> str:
        """
        Retorna o nome do setting que precisa de secrets, ou "" se já tiver tudo.
        """
        s_vpn = connection.get_setting_vpn()
        saml_enabled = self._saml_enabled(s_vpn)
        if saml_enabled:
            return ""
        if not s_vpn.get_secret("password") and not s_vpn.get_data_item("cookie"):
            return NM.SETTING_VPN_SETTING_NAME
        return ""

    @staticmethod
    def _saml_enabled(s_vpn: NM.SettingVpn) -> bool:
        """A UI plasma grava 'saml-login' como 'true'/'false' (bool)."""
        value = s_vpn.get_data_item("saml-login")
        return (value or "").strip().lower() in ("true", "1", "yes", "on")

    @staticmethod
    def _saml_port(s_vpn: NM.SettingVpn) -> int:
        """Porta do webserver SAML local ('saml-port' ou default 8020)."""
        raw = s_vpn.get_data_item("saml-port")
        try:
            return int(raw) if raw else 8020
        except ValueError:
            return 8020

    def _setting_to_config(self, s_vpn: NM.SettingVpn) -> VpnConfig:
        """Converte NM.SettingVpn → VpnConfig."""
        def d(key: str, default: str = "") -> str:
            return s_vpn.get_data_item(key) or default

        cfg = VpnConfig(
            host=d("gateway"),
            port=int(d("port", "443")),
            username=d("username"),
            password=s_vpn.get_secret("password") or "",
            realm=d("realm"),
            otp=s_vpn.get_secret("otp") or "",
            cookie=s_vpn.get_secret("cookie") or "",
            ca_file=d("ca-file"),
            user_cert=d("user-cert"),
            user_key=d("user-key"),
            trusted_cert=[v for v in d("trusted-cert").split(";") if v],
            insecure_ssl=d("insecure-ssl") == "yes",
            set_routes=int(d("set-routes", "1")),
            set_dns=int(d("set-dns", "1")),
        )
        if self._saml_enabled(s_vpn):
            cfg.saml_login = self._saml_port(s_vpn)
        return cfg

    def _start_vpn(self, cfg: VpnConfig) -> bool:
        self._last_cfg = cfg
        self._seed_trusted_certs(cfg)
        config_file = cfg.to_tempfile()
        self._vpn_proc = VpnProcess(
            config_file=config_file,
            saml_port=cfg.saml_login,
            on_connected=self._on_vpn_connected,
            on_disconnected=self._on_vpn_disconnected,
            on_error=self._on_vpn_error,
            on_cert_challenge=self._on_cert_challenge,
        )
        return self._vpn_proc.start()

    def _seed_trusted_certs(self, cfg: VpnConfig) -> None:
        """Se não há trusted-cert no perfil, usa os já confiados pelo usuário."""
        if cfg.trusted_cert:
            return
        cfg.trusted_cert = certstore.get_trusted(cfg.host, cfg.port)

    def _persist_trusted_cert(self, digest: str) -> None:
        if self._last_cfg:
            certstore.add_trusted(self._last_cfg.host, self._last_cfg.port, digest)
            # também atualiza o campo no config atual para não repedir o prompt
            if digest not in self._last_cfg.trusted_cert:
                self._last_cfg.trusted_cert.append(digest)

    def _on_cert_challenge(self, digest: str) -> None:
        if not self._last_cfg:
            self._on_vpn_error("certificado não confiável (sem config)")
            return
        host = self._last_cfg.host
        log.info("Certificado não confiável detectado: host=%s sha256=%s", host, digest[:16])

        def _ask() -> None:
            accepted, persist = prompt.ask_trust_cert(host, digest)
            GLib.idle_add(self._handle_cert_answer, digest, accepted, persist)

        threading.Thread(target=_ask, daemon=True).start()

    def _handle_cert_answer(self, digest: str, accepted: bool, persist: bool) -> None:
        if not accepted:
            self._on_vpn_error(
                f"o certificado do gateway {self._last_cfg.host} não foi aceito pelo usuário"
            )
            return
        if persist:
            self._persist_trusted_cert(digest)
        # esta tentativa já confia mesmo sem persistir (evita prompt em loop)
        if digest not in self._last_cfg.trusted_cert:
            self._last_cfg.trusted_cert.append(digest)
        self._start_vpn(self._last_cfg)

    def _on_vpn_connected(self) -> None:
        # A partir daqui publicamos o IP4 config completo — é isso que leva o
        # NM a transitar o plugin para VpnServiceState.STARTED (sem IP config
        # ele falha com "no valid IP config information" na ativação).
        dns_servers: list[str] = []
        local_ip: str | None = None
        if self._vpn_proc:
            local_ip = getattr(self._vpn_proc, "_local_ip", None)
            dns_servers = list(getattr(self._vpn_proc, "_dns_servers", []) or [])
        builder = {
            "tundev": GLib.Variant("s", "ppp0"),
            "never-default": GLib.Variant("b", True),
        }
        gw_ip = None
        if self._last_cfg:
            try:
                import socket
                gw_host = self._last_cfg.host
                # o NM grava o gateway como "host:porta" — tira a porta antes
                # de resolver, senão gethostbyname falha e o gateway some do
                # IP4Config (NM fica travado em "Conectando").
                if ":" in gw_host:
                    gw_host = gw_host.rsplit(":", 1)[0]
                gw_ip = socket.gethostbyname(gw_host)
            except Exception as e:
                log.warning("falha ao resolver gateway %s: %s", gw_host, e)
                gw_ip = None
        if gw_ip:
            builder["gateway"] = GLib.Variant("u", _ipv4_uint(gw_ip))
        if local_ip:
            builder["address"] = GLib.Variant("u", _ipv4_uint(local_ip))
            builder["prefix"] = GLib.Variant("u", 32)
        if dns_servers:
            builder["dns"] = GLib.Variant("au", [_ipv4_uint(d) for d in dns_servers if _ipv4_uint(d)])
        log.info("IP4Config para NM: %s", {k: str(v) for k, v in builder.items()})
        self.set_ip4_config(GLib.Variant("a{sv}", dict(builder)))

    def _on_vpn_disconnected(self) -> None:
        log.info("VPN desconectada; NM detecta via término do D-Bus")

    def _on_vpn_error(self, msg: str) -> None:
        log.error("Erro VPN: %s", msg)
        self.failure(NM.VpnPluginFailure.CONNECT_FAILED)