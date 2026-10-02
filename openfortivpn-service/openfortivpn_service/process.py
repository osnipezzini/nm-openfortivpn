"""
Spawna o openfortivpn como processo filho e monitora seu ciclo de vida.

Baseado em Gio.Subprocess + callbacks do GLib MainLoop (o NMVpnServicePlugin
roda num GLib.MainLoop, e não num event loop asyncio).
"""
from __future__ import annotations
import logging
import os
import re
import shutil
import signal

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gio

from openfortivpn_service.saml import extract_saml_url, BrowserOpener

log = logging.getLogger(__name__)

# O daemon roda como root: procure apenas nos diretórios do sistema, com
# preferência por instalações compiladas em /usr/local (make install).
OPENFORTIVPN_BIN = os.environ.get("NM_OPENFORTIVPN_BIN") or shutil.which(
    "openfortivpn", path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
) or "/usr/bin/openfortivpn"

# Hash SHA-256 sugerido pelo openfortivpn nas linhas:
#   --trusted-cert d3d990146e4e4fd1ffa9db61f310143e6a241f5bfc0f2d56fdadeae76bac8509
#   trusted-cert = d3d990146e4e4fd1ffa9db61f310143e6a241f5bfc0f2d56fdadeae76bac8509
CERT_DIGEST_PATTERN = re.compile(r"trusted-cert[ =:]*\s*([0-9a-fA-F]{64})")
CERT_FAILED_MARK = "certificate validation failed"

# Linhas do openfortivpn que publicam a configuração de IP do túnel:
#   INFO:  Got V4 addresses: [192.168.60.15], dns [1.2.3.4, 8.8.8.8]
#   local IP address 192.168.60.15
#   primary  DNS address: 1.2.3.4
#   secondary DNS address: 8.8.8.8
GOT_ADDRESSES_PATTERN = re.compile(
    r"(?:got\s+(?:\w+\s+)?)?addresses\s*:\s*\[([0-9.]+)\](?:[^\[]*\[([^\]]*)\])?",
    re.IGNORECASE,
)
LOCAL_IP_PATTERN = re.compile(r"local\s+(?:interface\s+)?IP address\s*:?\s*([0-9.]+)", re.IGNORECASE)
DNS1_PATTERN = re.compile(r"(?:primary|first)\s+DNS address\s*:?\s*([0-9.]+)", re.IGNORECASE)
DNS2_PATTERN = re.compile(r"(?:secondary|second)\s+DNS address\s*:?\s*([0-9.]+)", re.IGNORECASE)


def extract_cert_digest(line: str) -> str | None:
    m = CERT_DIGEST_PATTERN.search(line)
    return m.group(1).lower() if m else None


class VpnProcess:
    def __init__(
        self,
        config_file,
        saml_port: int | None = None,
        on_connected=None,
        on_disconnected=None,
        on_error=None,
        on_cert_challenge=None,
        ifname: str = "",
    ):
        self._config_file = config_file
        self._saml_port = saml_port
        self._ifname = ifname
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
        self._on_cert_challenge = on_cert_challenge
        self._buf_rem = bytearray()
        self._proc: Gio.Subprocess | None = None
        self._buffer = bytearray()
        self._stopping = False
        self._cert_failed = False
        self._cert_digest: str | None = None
        self._stdout_eof = False
        self._finalized = False
        self._pending_rc: int | None = None
        self._browser_opener = BrowserOpener() if saml_port else None
        self._local_ip: str | None = None
        self._dns_servers: list[str] = []

    def _build_cmd(self) -> list[str]:
        cmd = [OPENFORTIVPN_BIN, f"--config={self._config_file}"]
        if self._saml_port:
            cmd.append(f"--saml-login={self._saml_port}")
        if self._ifname:  # o 1.24 não aceita ifname no arquivo de config
            cmd.append(f"--ifname={self._ifname}")
        return cmd

    def start(self) -> bool:
        cmd = self._build_cmd()
        log.info("Iniciando: %s", " ".join(cmd))
        flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
        try:
            self._proc = Gio.Subprocess.new(cmd, flags)
        except GLib.Error as e:
            log.error("Falha ao iniciar openfortivpn: %s", e.message)
            if self._on_error:
                self._on_error(f"falha ao iniciar openfortivpn: {e.message}")
            return False

        self._proc.wait_async(None, self._on_proc_exited, None)

        stream = self._proc.get_stdout_pipe()
        if stream:
            stream.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, None,
                                    self._on_stream_read, None)
        return True

    # ------------------------------------------------------------------ IO
    def _on_stream_read(self, stream: Gio.InputStream, result, user_data):
        try:
            contents = stream.read_bytes_finish(result)
        except GLib.Error:
            self._on_stream_eof()
            return

        data = contents.get_data() if contents else None
        if not data:
            self._on_stream_eof()
            return

        self._buffer += data
        self._drain_lines()

        stream.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, None,
                                self._on_stream_read, None)

    def _drain_lines(self) -> None:
        while b"\n" in self._buffer:
            raw, self._buffer = self._buffer.split(b"\n", 1)
            self._handle_line(raw.decode(errors="replace").rstrip("\r"))

    def _on_stream_eof(self) -> None:
        self._stdout_eof = True
        if self._buffer:
            self._handle_line(self._buffer.decode(errors="replace").rstrip("\r"))
            self._buffer.clear()
# Se o processo já saiu e a falha de cert ainda não foi finalizada
        # (o digest não-pode ter só chegado agora, no EOF), finaliza aqui.
        if self._cert_failed and self._pending_rc is not None and not self._finalized:
            self._finalize_exit(self._pending_rc)

    def _handle_line(self, line: str) -> None:
        log.debug("[openfortivpn] %s", line)

        # Falha de validação do certificado: o openfortivpn imprime o hash e
        # sai com código != 0. A decisão é adiada para _on_proc_exited, quando
        # o diálogo dispara para o usuário confiar ou não.
        if (digest := extract_cert_digest(line)) and not self._cert_digest:
            self._cert_digest = digest
        if CERT_FAILED_MARK in line.lower():
            self._cert_failed = True

        if self._cert_failed:
            return

        if self._saml_port and (url := extract_saml_url(line)):
            log.info("URL SAML detectada, abrindo browser: %s", url)
            try:
                self._browser_opener.open(url)
            except Exception:
                log.exception("falha ao abrir browser da URL SAML")

        if "Tunnel is up and running" in line:
            log.info(
                "VPN conectada (local=%s dns=%s)",
                self._local_ip or "?",
                ",".join(self._dns_servers) or "?",
            )
            if self._on_connected:
                self._on_connected()

        # Captura IP/DNS publicados pelo openfortivpn (usados no IP4Config).
        if (m := GOT_ADDRESSES_PATTERN.search(line)) and not self._local_ip:
            self._local_ip = m.group(1)
            if m.group(2):
                self._dns_servers = [s.strip() for s in m.group(2).split(",") if s.strip()]
        if (m := LOCAL_IP_PATTERN.search(line)):
            self._local_ip = m.group(1)
        if self._local_ip:
            if (m := DNS1_PATTERN.search(line)) and m.group(1) not in self._dns_servers:
                self._dns_servers.append(m.group(1))
            if (m := DNS2_PATTERN.search(line)) and m.group(1) not in self._dns_servers:
                self._dns_servers.append(m.group(1))

        lc = line.lower()
        if "error" in lc or "failed" in lc:
            if self._on_error:
                log.error("Erro do openfortivpn: %s", line)
                self._on_error(line)

    # ------------------------------------------------------------- lifecycle
    def _on_proc_exited(self, proc: Gio.Subprocess, result, user_data):
        try:
            proc.wait_finish(result)
        except GLib.Error:
            pass

        rc = proc.get_exit_status()
        log.info("openfortivpn terminou com código %d", rc)
        self._pending_rc = rc

        try:
            self._config_file.unlink(missing_ok=True)
        except Exception:
            pass

        # O callback de exit pode chegar ANTES da primeira leitura do stdout
        # (especialmente nas falhas de certificado, que terminam em rc != 0).
        # Difere a finalização até o stream dar EOF (onde o último bloco é
        # drenado e o digest do certificado é capturado). Poll ~50ms; aborta
        # após ~4s se o EOF nunca vier, para não travar o erro normal.
        if not self._stdout_eof:
            GLib.timeout_add(50, self._poll_finalize, rc, 80)
            return
        self._finalize_exit(rc)

    def _poll_finalize(self, rc: int, tries: int) -> bool:
        if self._stdout_eof or tries <= 0:
            self._finalize_exit(rc)
            return False
        GLib.timeout_add(50, self._poll_finalize, rc, tries - 1)
        return False

    def _finalize_exit(self, rc: int) -> bool:
        if self._finalized:
            return False
        self._finalized = True

        # Certificado não confiável: entregar ao plugin para perguntar ao
        # usuário; não tratar como erro/desconexão aqui (o fluxo pode
        # recomeçar com --trusted-cert).
        if (
            rc != 0
            and self._cert_failed
            and self._cert_digest
            and not self._stopping
            and self._on_cert_challenge
        ):
            log.info("Certificado do gateway não confiável; encaminhando ao usuário")
            self._on_cert_challenge(self._cert_digest)
            return False

        if rc != 0 and self._on_error and not self._stopping:
            self._on_error(f"openfortivpn saiu com código {rc}")
        if self._on_disconnected:
            self._on_disconnected()
        return False

    def stop(self) -> None:
        if self._proc:
            self._stopping = True
            log.info("Enviando SIGTERM ao openfortivpn")
            try:
                self._proc.send_signal(signal.SIGTERM)
            except GLib.Error:
                pass
