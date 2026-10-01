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


_TRUE = ("1", "yes", "true", "on")
_GENERIC_KEYS = {
    "realm": str, "otp-prompt": str, "otp-delay": int, "no-ftm-push": bool,
    "sni": str, "insecure-ssl": bool, "cipher-list": str, "min-tls": str,
    "seclevel-1": bool, "set-routes": bool, "half-internet-routes": bool,
    "set-dns": bool, "use-resolvconf": bool, "pppd-use-peerdns": bool,
    "pppd-log": str, "pppd-plugin": str, "pppd-ipparam": str, "pppd-ifname": str,
    "pppd-call": str, "pppd-accept-remote": bool, "ifname": str, "persistent": int,
}


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
        self._last_cfg = None
        return True

    def do_need_secrets(
        self, connection: NM.Connection, setting_name: str
    ) -> str:
        """
        Retorna o nome do setting que precisa de secrets, ou "" se já tiver tudo.
        """
        s_vpn = connection.get_setting_vpn()
        if self._saml_enabled(s_vpn):
            return ""
        flags = lambda k: int(s_vpn.get_data_item(k + "-flags") or 0)
        if not (flags("password") & NM.SettingSecretFlags.NOT_REQUIRED):
            if not s_vpn.get_secret("password") and not s_vpn.get_data_item("cookie"):
                return NM.SETTING_VPN_SETTING_NAME
        if flags("otp") == NM.SettingSecretFlags.NOT_SAVED and not s_vpn.get_secret("otp"):
            return NM.SETTING_VPN_SETTING_NAME
        if (flags("pem-passphrase") & NM.SettingSecretFlags.NOT_SAVED
                and s_vpn.get_data_item("key") and not s_vpn.get_secret("pem-passphrase")):
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
        def d(key: str, default: str = "", old: str = "") -> str:
            # chave canônica (nm-openfortivpn-service.h), com fallback para o nome antigo
            return s_vpn.get_data_item(key) or (old and s_vpn.get_data_item(old)) or default

        cfg = VpnConfig(
            host=d("gateway"),
            port=int(d("port", "443")),
            username=d("user", old="username"),
            password=s_vpn.get_secret("password") or "",
            otp=s_vpn.get_secret("otp") or "",
            cookie=s_vpn.get_secret("cookie") or "",
            pem_passphrase=s_vpn.get_secret("pem-passphrase") or "",
            ca_file=d("ca", old="ca-file"),
            user_cert=d("cert", old="user-cert"),
            user_key=d("key", old="user-key"),
            trusted_cert=[v for v in d("trusted-cert").split(";") if v],
        )
        # chaves genéricas (default do VpnConfig quando ausente); bool/int gravam int
        for key, kind in _GENERIC_KEYS.items():
            raw = d(key)
            if raw == "":
                continue
            attr = key.replace("-", "_")
            try:
                val = (raw.strip().lower() in _TRUE) if kind is bool else kind(raw)
            except ValueError:
                continue
            setattr(cfg, attr, int(val) if isinstance(getattr(cfg, attr), (bool, int)) else val)
        if self._saml_enabled(s_vpn):
            cfg.saml_login = self._saml_port(s_vpn)
        return cfg

    def _start_vpn(self, cfg: VpnConfig) -> bool:
        self._last_cfg = cfg
        self._seed_trusted_certs(cfg)
        if cfg.insecure_ssl:
            self._spawn(cfg)
            return True
        # Checa o certificado ANTES do openfortivpn: no SAML ele só valida o
        # cert depois do login no browser, e a falha mata o processo (o login
        # se perde e o usuário teria que autenticar de novo).
        threading.Thread(target=self._precheck_cert, args=(cfg,), daemon=True).start()
        return True

    def _precheck_cert(self, cfg: VpnConfig) -> None:
        res = certstore.server_digest(cfg.host, cfg.port, cfg.ca_file)
        if res and not res[1] and res[0] not in cfg.trusted_cert:
            GLib.idle_add(self._on_cert_challenge, res[0])
        else:
            GLib.idle_add(self._spawn, cfg)

    def _spawn(self, cfg: VpnConfig) -> bool:
        if cfg is not self._last_cfg:  # desconectado durante a pré-checagem
            return False
        config_file = cfg.to_tempfile()
        self._vpn_proc = VpnProcess(
            config_file=config_file,
            saml_port=cfg.saml_login,
            on_connected=self._on_vpn_connected,
            on_disconnected=self._on_vpn_disconnected,
            on_error=self._on_vpn_error,
            on_cert_challenge=self._on_cert_challenge,
            ifname=cfg.ifname,
        )
        self._vpn_proc.start()  # falha já reporta via on_error
        return False  # GLib.idle_add: não repetir

    def _seed_trusted_certs(self, cfg: VpnConfig) -> None:
        """Soma ao trusted-cert do perfil os já confiados pelo usuário."""
        for digest in certstore.get_trusted(cfg.host, cfg.port):
            if digest not in cfg.trusted_cert:
                cfg.trusted_cert.append(digest)

    def _persist_trusted_cert(self, digest: str) -> None:
        if self._last_cfg:
            certstore.add_trusted(self._last_cfg.host, self._last_cfg.port, digest)
            # também atualiza o campo no config atual para não repedir o prompt
            if digest not in self._last_cfg.trusted_cert:
                self._last_cfg.trusted_cert.append(digest)

    def _on_cert_challenge(self, digest: str) -> bool:
        if not self._last_cfg:
            return False
        host = self._last_cfg.host
        log.info("Certificado não confiável detectado: host=%s sha256=%s", host, digest[:16])

        def _ask() -> None:
            accepted, persist = prompt.ask_trust_cert(host, digest)
            GLib.idle_add(self._handle_cert_answer, digest, accepted, persist)

        threading.Thread(target=_ask, daemon=True).start()
        return False  # GLib.idle_add: não repetir

    def _handle_cert_answer(self, digest: str, accepted: bool, persist: bool) -> bool:
        if not self._last_cfg:
            return False
        if not accepted:
            self._on_vpn_error(
                f"o certificado do gateway {self._last_cfg.host} não foi aceito pelo usuário"
            )
            return False
        if persist:
            self._persist_trusted_cert(digest)
        # esta tentativa já confia mesmo sem persistir (evita prompt em loop)
        if digest not in self._last_cfg.trusted_cert:
            self._last_cfg.trusted_cert.append(digest)
        self._spawn(self._last_cfg)
        return False

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