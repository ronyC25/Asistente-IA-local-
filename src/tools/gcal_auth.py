"""Autorizacion OAuth de Google Calendar (se hace una sola vez).

Uso:
    .\\.venv\\Scripts\\python.exe -m src.tools.gcal_auth
"""
from __future__ import annotations

import sys
from pathlib import Path

from ..config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("[!] Faltan las dependencias de Google. Instala:")
        print(
            "    .\\.venv\\Scripts\\python.exe -m pip install -r requirements-google.txt"
        )
        return 1

    cfg = settings.google_calendar
    cred = Path(cfg["credentials_file"])
    token = Path(cfg["token_file"])

    if not cred.exists():
        print(f"[!] No encuentro las credenciales OAuth: {cred}")
        print("    En Google Cloud Console crea un 'ID de cliente OAuth' de tipo")
        print("    'App de escritorio', descarga el JSON y guardalo con ese nombre.")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(cred), SCOPES)
    print("[i] Se abrira el navegador para autorizar el acceso al calendario...")
    creds = flow.run_local_server(port=0)
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    print(f"[ok] Autorizado. Token guardado en: {token}")
    print(
        "     Activa la sincronizacion en config/settings.yaml "
        "(google_calendar.enabled: true)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
