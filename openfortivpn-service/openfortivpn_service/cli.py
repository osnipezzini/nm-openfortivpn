import argparse
import sys
from openfortivpn_service.core import VpnCore


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openfortivpn-service",
        description="NetworkManager VPN service wrapper para openfortivpn",
    )

    # --- Conexão ---
    p.add_argument("host_port", nargs="?", metavar="<host>[:<port>]",
                   help="Gateway VPN (ex: vpn.example.com:443)")
    p.add_argument("-u", "--username", metavar="<user>")
    p.add_argument("-p", "--password", metavar="<pass>")
    p.add_argument("-c", "--config", metavar="<file>",
                   default="/etc/openfortivpn/config")
    p.add_argument("--realm", metavar="<realm>", default="")
    p.add_argument("--ifname", metavar="<interface>")
    p.add_argument("--persistent", metavar="<interval>", type=int, default=0)

    # --- Autenticação especial ---
    p.add_argument("--cookie", metavar="<cookie>")
    p.add_argument("--cookie-on-stdin", action="store_true")
    p.add_argument("--saml-login", nargs="?", const=8020, type=int,
                   metavar="<port>",
                   help="Inicia webserver SAML local na porta (padrão: 8020)")
    p.add_argument("--pinentry", metavar="<name>")
    p.add_argument("-o", "--otp", metavar="<otp>")
    p.add_argument("--otp-prompt", metavar="<prompt>")
    p.add_argument("--otp-delay", metavar="<delay>", type=int, default=0)
    p.add_argument("--no-ftm-push", action="store_true")

    # --- TLS / Certificados ---
    p.add_argument("--ca-file", metavar="<file>")
    p.add_argument("--user-cert", metavar="<file|pkcs11:...>")
    p.add_argument("--user-key", metavar="<file>")
    p.add_argument("--pem-passphrase", metavar="<pass>")
    p.add_argument("--trusted-cert", metavar="<digest>", action="append",
                   default=[])
    p.add_argument("--insecure-ssl", action="store_true")
    p.add_argument("--cipher-list", metavar="<ciphers>")
    p.add_argument("--min-tls", metavar="<version>",
                   choices=["1.0", "1.1", "1.2", "1.3"])
    p.add_argument("--seclevel-1", action="store_true")

    # --- Rede ---
    p.add_argument("--set-routes", metavar="<bool>", type=int)
    p.add_argument("--no-routes", action="store_true")
    p.add_argument("--half-internet-routes", metavar="<bool>", type=int)
    p.add_argument("--set-dns", metavar="<bool>", type=int)
    p.add_argument("--no-dns", action="store_true")
    p.add_argument("--use-resolvconf", metavar="<bool>", type=int)

    # --- pppd ---
    p.add_argument("--pppd-use-peerdns", metavar="<bool>", type=int)
    p.add_argument("--pppd-no-peerdns", action="store_true")
    p.add_argument("--pppd-log", metavar="<file>")
    p.add_argument("--pppd-plugin", metavar="<file>")
    p.add_argument("--pppd-ipparam", metavar="<string>")
    p.add_argument("--pppd-ifname", metavar="<string>")
    p.add_argument("--pppd-call", metavar="<name>")
    p.add_argument("--pppd-accept-remote", metavar="<bool>", type=int)
    p.add_argument("--ppp-system", metavar="<string>")

    # --- Verbosidade e log ---
    p.add_argument("--use-syslog", action="store_true")
    p.add_argument("-v", dest="verbosity", action="count", default=0)
    p.add_argument("-q", dest="quiet", action="count", default=0)

    # --- Modo NM service (interno) ---
    p.add_argument("--nm-dbus-service", action="store_true",
                   help=argparse.SUPPRESS)
    p.add_argument("--bus-name", metavar="<name>", default=None,
                   help=argparse.SUPPRESS)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.nm_dbus_service or args.bus_name:
        from openfortivpn_service.nm.service import run_service
        sys.exit(run_service(args.bus_name))

    core = VpnCore(args)
    sys.exit(core.run())


if __name__ == "__main__":
    sys.exit(main())
