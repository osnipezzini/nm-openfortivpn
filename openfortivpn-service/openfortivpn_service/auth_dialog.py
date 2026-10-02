"""
Auth-dialog do NetworkManager (protocolo de stdin/stdout do NetworkManager-openvpn).

Pede senha e/ou OTP. Com --external-ui-mode só descreve os campos (keyfile)
para o GNOME Shell desenhar o diálogo; com -i abre um diálogo Gtk 3.
"""
from __future__ import annotations
import argparse
import sys

NOT_SAVED, NOT_REQUIRED, AGENT_OWNED = 2, 4, 1
LABELS = {"password": "Senha", "otp": "Código OTP / 2FA",
          "pem-passphrase": "Senha da chave privada"}


def _read_stdin() -> tuple[dict, dict, bool]:
    # NM manda dados, DONE, secrets, DONE
    data, secrets, key, done = {}, {}, None, 0
    for line in sys.stdin:
        line = line.rstrip("\n")
        if line == "DONE":
            done += 1
            if done == 2:
                break
        elif line == "QUIT":  # entrada curta, sem a seção de secrets
            return data, secrets, True
        if line.startswith("DATA_KEY="):
            key = ("d", line[9:])
        elif line.startswith("SECRET_KEY="):
            key = ("s", line[11:])
        elif line.startswith("DATA_VAL=") and key and key[0] == "d":
            data[key[1]] = line[9:]
        elif line.startswith("SECRET_VAL=") and key and key[0] == "s":
            secrets[key[1]] = line[11:]
    return data, secrets, False


def _flags(data: dict, name: str) -> int:
    try:
        return int(data.get(name + "-flags", 0))
    except ValueError:
        return 0


def _keyring(uuid: str, key: str) -> str | None:
    """Busca o secret no keyring do usuário (schema do NM)."""
    try:
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret
        schema = Secret.Schema.new(
            "org.freedesktop.NetworkManager.Connection", Secret.SchemaFlags.DONT_MATCH_NAME,
            {"connection-uuid": Secret.SchemaAttributeType.STRING,
             "setting-name": Secret.SchemaAttributeType.STRING,
             "setting-key": Secret.SchemaAttributeType.STRING})
        return Secret.password_lookup_sync(
            schema, {"connection-uuid": uuid, "setting-name": "vpn", "setting-key": key}, None)
    except Exception:
        return None


def _needed(args, data: dict, secrets: dict) -> list[str]:
    """Secrets que ainda precisam ser pedidos ao usuário."""
    need = []
    saml = data.get("saml-login", "").lower() in ("true", "1", "yes", "on")
    pf = _flags(data, "password")
    if not saml and not pf & NOT_REQUIRED:
        if args.reprompt or not secrets.get("password"):
            stored = pf & AGENT_OWNED and not args.reprompt and _keyring(args.uuid, "password")
            if stored:
                secrets["password"] = stored  # devolvido ao NM junto com os demais
            else:
                need.append("password")
    if (_flags(data, "otp") == NOT_SAVED or {"otp", "2fa"} & set(args.hints)) and not saml:
        need.append("otp")
    if _flags(data, "pem-passphrase") & NOT_SAVED and data.get("key") and not secrets.get("pem-passphrase"):
        need.append("pem-passphrase")
    return need


def _external_ui(args, need: list[str]) -> None:
    out = ["[VPN Plugin UI]", "Version=2", f"Description=Autenticação da VPN {args.name}",
           f"Title=Autenticar VPN {args.name}", ""]
    for k in need:
        out += [f"[{k}]", "Value=", f"Label={LABELS[k]}", "IsSecret=true", "ShouldAsk=true", ""]
    sys.stdout.write("\n".join(out) + "\n")


def _gtk_dialog(args, need: list[str]) -> dict | None:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    dlg = Gtk.Dialog(title=f"Autenticar VPN {args.name}")
    dlg.add_button("Cancelar", Gtk.ResponseType.CANCEL)
    dlg.add_button("OK", Gtk.ResponseType.OK).set_can_default(True)
    dlg.set_default_response(Gtk.ResponseType.OK)
    grid = Gtk.Grid(row_spacing=6, column_spacing=6, margin=12)
    entries = {}
    for i, k in enumerate(need):
        e = Gtk.Entry(visibility=False, activates_default=True, hexpand=True)
        grid.attach(Gtk.Label(label=LABELS[k], xalign=1), 0, i, 1, 1)
        grid.attach(e, 1, i, 1, 1)
        entries[k] = e
    dlg.get_content_area().add(grid)
    dlg.show_all()
    ok = dlg.run() == Gtk.ResponseType.OK
    result = {k: e.get_text() for k, e in entries.items()} if ok else None
    dlg.destroy()
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-u", "--uuid", required=True)
    ap.add_argument("-n", "--name", required=True)
    ap.add_argument("-s", "--service", required=True)
    ap.add_argument("-i", "--allow-interaction", action="store_true")
    ap.add_argument("-r", "--reprompt", action="store_true")
    ap.add_argument("-t", "--hint", dest="hints", action="append", default=[])
    ap.add_argument("--external-ui-mode", action="store_true")
    args = ap.parse_args()

    data, secrets, quit_ = _read_stdin()
    need = _needed(args, data, secrets)

    if args.external_ui_mode:
        _external_ui(args, need)
        return 0

    if need and args.allow_interaction:
        answers = _gtk_dialog(args, need)
        if answers is None:
            return 1
        secrets.update(answers)
    elif need:
        return 1
    # secrets já fornecidos pelo NM mas não pedidos agora são devolvidos como estão
    for k, v in secrets.items():
        sys.stdout.write(f"{k}\n{v}\n")
    sys.stdout.write("\n\n")
    sys.stdout.flush()
    # NM manda QUIT quando terminou de ler
    for line in sys.stdin if not quit_ else ():
        if line.strip() == "QUIT":
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
