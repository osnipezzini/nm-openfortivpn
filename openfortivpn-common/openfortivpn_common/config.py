"""
Lê/escreve o formato de config nativo do openfortivpn.
Referência: man openfortivpn(1), seção CONFIGURATION.
"""
from __future__ import annotations
from dataclasses import dataclass, field, fields
from pathlib import Path
import re


# Chaves booleanas que o openfortivpn aceita como 0/1
BOOL_KEYS = {
    "set-routes", "set-dns", "half-internet-routes",
    "pppd-use-peerdns", "pppd-accept-remote",
    "use-resolvconf", "insecure-ssl", "no-ftm-push",
    "use-syslog", "seclevel-1", "persistent",
}

# Chaves que podem aparecer múltiplas vezes (lista)
MULTI_KEYS = {"trusted-cert"}


@dataclass
class VpnConfig:
    host: str = ""
    port: int = 443
    username: str = ""
    password: str = ""
    realm: str = ""
    otp: str = ""
    otp_delay: int = 0
    otp_prompt: str = ""
    no_ftm_push: bool = False
    cookie: str = ""
    saml_login: int | None = None
    pinentry: str = ""
    ifname: str = ""
    ca_file: str = ""
    user_cert: str = ""
    user_key: str = ""
    pem_passphrase: str = ""
    trusted_cert: list[str] = field(default_factory=list)
    insecure_ssl: bool = False
    cipher_list: str = ""
    min_tls: str = ""
    seclevel_1: bool = False
    set_routes: int = 1
    no_routes: bool = False
    half_internet_routes: int = 0
    set_dns: int = 1
    no_dns: bool = False
    use_resolvconf: int = 1
    pppd_use_peerdns: int = 0
    pppd_log: str = ""
    pppd_plugin: str = ""
    pppd_ipparam: str = ""
    pppd_ifname: str = ""
    pppd_call: str = ""
    pppd_accept_remote: int = 1
    ppp_system: str = ""
    use_syslog: bool = False
    persistent: int = 0
    verbosity: int = 0

    @classmethod
    def from_file(cls, path: str | Path) -> "VpnConfig":
        cfg = cls()
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([\w-]+)\s*=\s*(.*)$", line)
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            attr = key.replace("-", "_")
            if key in MULTI_KEYS:
                getattr(cfg, attr).append(val)
            elif hasattr(cfg, attr):
                cur = getattr(cfg, attr)
                if isinstance(cur, bool):
                    setattr(cfg, attr, val not in ("0", "false", "no", ""))
                elif isinstance(cur, int):
                    setattr(cfg, attr, int(val))
                else:
                    setattr(cfg, attr, val)
        return cfg

    def to_tempfile(self) -> Path:
        """Gera arquivo de config temporário para o openfortivpn."""
        import tempfile
        lines = []
        port_line = str(self.port)
        if self.host:
            host_line = self.host.strip()
            # Se o host já vem com ":porta" (ex.: NM grava "teste.com:8443" no
            # gateway), normaliza para host + port separados; caso contrário o
            # openfortivpn monta URL com porta duplicada (":8443:443").
            m = re.match(r"^(.*):(\d+)$", host_line)
            if m:
                lines.append(f"host = {m.group(1)}")
                port_line = m.group(2)
            else:
                lines.append(f"host = {host_line}")
        lines.append(f"port = {port_line}")
        if self.username:
            lines.append(f"username = {self.username}")
        if self.password:
            lines.append(f"password = {self.password}")
        for cert in self.trusted_cert:
            lines.append(f"trusted-cert = {cert}")
        for key, val in [
            ("realm", self.realm),
            ("otp", self.otp),
            ("pinentry", self.pinentry),
            ("ca-file", self.ca_file),
            ("user-cert", self.user_cert),
            ("user-key", self.user_key),
            ("pem-passphrase", self.pem_passphrase),
            ("cipher-list", self.cipher_list),
            ("min-tls", self.min_tls),
            ("pppd-log", self.pppd_log),
            ("pppd-plugin", self.pppd_plugin),
            ("pppd-ipparam", self.pppd_ipparam),
            ("pppd-ifname", self.pppd_ifname),
            ("pppd-call", self.pppd_call),
            ("ppp-system", self.ppp_system),
            ("ifname", self.ifname),
        ]:
            if val:
                lines.append(f"{key} = {val}")
        for key, val in [
            ("set-routes", self.set_routes),
            ("set-dns", self.set_dns),
            ("half-internet-routes", self.half_internet_routes),
            ("use-resolvconf", self.use_resolvconf),
            ("pppd-use-peerdns", self.pppd_use_peerdns),
            ("pppd-accept-remote", self.pppd_accept_remote),
            ("persistent", self.persistent),
            ("otp-delay", self.otp_delay),
        ]:
            lines.append(f"{key} = {val}")
        for key, val in [
            ("insecure-ssl", self.insecure_ssl),
            ("no-ftm-push", self.no_ftm_push),
            ("use-syslog", self.use_syslog),
            ("seclevel-1", self.seclevel_1),
        ]:
            lines.append(f"{key} = {int(val)}")

        tmp = tempfile.NamedTemporaryFile(
            mode="w", prefix="openfortivpn-", suffix=".conf",
            delete=False
        )
        tmp.write("\n".join(lines) + "\n")
        tmp.flush()
        return Path(tmp.name)
