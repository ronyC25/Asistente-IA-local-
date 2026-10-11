"""Notificaciones nativas de Windows (toast) con fallback a consola."""
from __future__ import annotations

import os
import shutil
import subprocess

# AppUserModelID de PowerShell: garantiza que el toast se muestre sin
# necesidad de instalar/registrar una aplicacion propia.
_APP_ID = (
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
)

_SCRIPT = r"""
$ErrorActionPreference = "Stop"
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $template.GetElementsByTagName("text")
$texts.Item(0).AppendChild($template.CreateTextNode($env:JARVIS_TITLE)) | Out-Null
$texts.Item(1).AppendChild($template.CreateTextNode($env:JARVIS_MSG)) | Out-Null
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:JARVIS_APPID)
$notifier.Show([Windows.UI.Notifications.ToastNotification]::new($template))
"""


def _fallback(titulo: str, mensaje: str, error: str | None = None) -> dict:
    print(f"[NOTIFICACION] {titulo}: {mensaje}")
    return {
        "ok": False,
        "canal": "windows",
        "titulo": titulo,
        "mensaje": mensaje,
        "error": error,
        "fallback": "consola",
    }


def notify_windows(titulo: str, mensaje: str) -> dict:
    """Muestra un toast de Windows. Devuelve un dict con el resultado."""
    if os.name != "nt" or not shutil.which("powershell"):
        return _fallback(titulo, mensaje, error="powershell no disponible")

    env = os.environ.copy()
    env["JARVIS_TITLE"] = str(titulo)
    env["JARVIS_MSG"] = str(mensaje)
    env["JARVIS_APPID"] = _APP_ID
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _SCRIPT,
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        return _fallback(titulo, mensaje, error=str(exc))

    if proc.returncode != 0:
        return _fallback(titulo, mensaje, error=(proc.stderr or "").strip())
    return {"ok": True, "canal": "windows", "titulo": titulo}


def enviar_notificacion_windows(titulo: str, mensaje: str) -> dict:
    return notify_windows(titulo, mensaje)
