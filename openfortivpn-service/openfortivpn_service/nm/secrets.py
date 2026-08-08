"""
Agente de secrets para NetworkManager.
"""
from __future__ import annotations
import logging
import gi

gi.require_version("NM", "1.0")
gi.require_version("GLib", "2.0")
from gi.repository import NM, GLib, Gio, Secret

log = logging.getLogger(__name__)

SECRET_SCHEMA = Secret.Schema.new(
    "org.freedesktop.NetworkManager.openfortivpn",
    Secret.SchemaFlags.NONE,
    {
        "gateway": Secret.SchemaAttributeType.STRING,
        "username": Secret.SchemaAttributeType.STRING,
    }
)


class SecretsAgent:
    """
    Agente para gerenciar secrets de VPN.
    """

    def __init__(self):
        self._connection: NM.Connection | None = None

    def get_vpn_secrets(self, connection: NM.Connection) -> dict[str, str]:
        """
        Recupera secrets da conexão VPN.
        Retorna dict com keys: password, otp, cookie.
        """
        s_vpn = connection.get_setting_vpn()
        secrets = {}

        if password := s_vpn.get_secret("password"):
            secrets["password"] = password
        else:
            password = self._get_secret_from_keyring(
                s_vpn.get_data_item("gateway") or "",
                s_vpn.get_data_item("username") or ""
            )
            if password:
                secrets["password"] = password

        if otp := s_vpn.get_secret("otp"):
            secrets["otp"] = otp

        if cookie := s_vpn.get_secret("cookie"):
            secrets["cookie"] = cookie

        return secrets

    def save_vpn_secrets(
        self,
        connection: NM.Connection,
        secrets: dict[str, str]
    ) -> None:
        """
        Salva secrets no keyring do sistema.
        """
        s_vpn = connection.get_setting_vpn()
        gateway = s_vpn.get_data_item("gateway") or ""
        username = s_vpn.get_data_item("username") or ""

        if "password" in secrets:
            self._save_secret_to_keyring(
                gateway, username, secrets["password"]
            )

    def _get_secret_from_keyring(
        self, gateway: str, username: str
    ) -> str | None:
        if not gateway or not username:
            return None

        try:
            password = Secret.password_lookup_sync(
                SECRET_SCHEMA,
                None,
                {"gateway": gateway, "username": username},
                None
            )
            return password
        except Exception as e:
            log.debug("Erro ao buscar secret do keyring: %s", e)
            return None

    def _save_secret_to_keyring(
        self, gateway: str, username: str, password: str
    ) -> None:
        if not gateway or not username or not password:
            return

        try:
            Secret.password_store_sync(
                SECRET_SCHEMA,
                {"gateway": gateway, "username": username},
                Secret.COLLECTION_DEFAULT,
                f"openfortivpn: {gateway}",
                password,
                None
            )
            log.info("Secret salvo no keyring para %s@%s", username, gateway)
        except Exception as e:
            log.warning("Erro ao salvar secret no keyring: %s", e)
