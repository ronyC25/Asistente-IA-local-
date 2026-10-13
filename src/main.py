"""Punto de entrada: CLI interactiva, servidor web o modo voz.

Uso:
    python -m src.main           # CLI interactiva
    python -m src.main --web     # servidor FastAPI
    python -m src.main --voice   # modo voz (wake word + STT + TTS)
    python -m src.main --telegram  # bot de Telegram bidireccional
"""
from __future__ import annotations

import sys

from .config import settings


def _setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _check_ollama() -> bool:
    try:
        import ollama

        client = ollama.Client(host=settings.ollama_host) if settings.ollama_host else ollama.Client()
        models = client.list().get("models", [])
    except Exception as exc:  # noqa: BLE001
        print(f"[!] No se pudo conectar con Ollama: {exc}")
        print("    Asegurate de que Ollama esta instalado y en ejecucion (ollama serve).")
        return False

    names = {m.get("model") or m.get("name") for m in models}
    base = settings.model.split(":")[0]
    if not any(n and (n == settings.model or n.startswith(base)) for n in names):
        print(f"[!] El modelo '{settings.model}' no esta descargado.")
        print(f"    Ejecuta: ollama pull {settings.model}")
        return False
    return True


def cli() -> None:
    from .factory import build_agent
    from .scheduler import shutdown as stop_scheduler
    from .scheduler import start as start_scheduler

    print(f"=== {settings.assistant_name} (modelo: {settings.model}) ===")
    if not _check_ollama():
        sys.exit(1)

    agent = build_agent()
    session = agent.new_session()
    start_scheduler()
    print("Escribe tu mensaje ('salir' para terminar).\n")

    try:
        while True:
            try:
                user = input("Tu > ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user:
                continue
            if user.lower() in {"salir", "exit", "quit", "adios"}:
                break
            reply, pending = agent.handle(session, user)
            from .brain.emotions import limpiar_respuesta

            reply, _emociones = limpiar_respuesta(reply)
            print(f"{settings.assistant_name} > {reply}\n")
    finally:
        stop_scheduler()


def _list_audio() -> None:
    try:
        import sounddevice as sd
    except ImportError:
        print("[!] Falta sounddevice. Instala: pip install -r requirements-voice.txt")
        return
    print("Dispositivos de audio:")
    for i, d in enumerate(sd.query_devices()):
        kinds = []
        if d["max_input_channels"] > 0:
            kinds.append("entrada")
        if d["max_output_channels"] > 0:
            kinds.append("salida")
        print(f"  [{i}] {d['name']} ({', '.join(kinds)})")


def voice() -> None:
    from .factory import build_agent
    from .scheduler import shutdown as stop_scheduler
    from .scheduler import start as start_scheduler
    from .voice.loop import run

    if "--list-audio" in sys.argv:
        _list_audio()
        return
    if not _check_ollama():
        sys.exit(1)
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        print("[!] Faltan las dependencias de voz.")
        print("    Instala:  pip install -r requirements-voice.txt")
        sys.exit(1)

    if "--device" in sys.argv:
        idx = sys.argv.index("--device")
        if idx + 1 < len(sys.argv):
            settings.voice["input_device"] = int(sys.argv[idx + 1])
    debug = "--debug" in sys.argv

    agent = build_agent()
    start_scheduler()
    try:
        run(agent, debug=debug)
    finally:
        stop_scheduler()


def main() -> None:
    _setup_console()
    if "--list-audio" in sys.argv:
        _list_audio()
    elif "--telegram" in sys.argv or "telegram" in sys.argv:
        from .telegram_bot import run as run_telegram

        run_telegram()
    elif "--web" in sys.argv or "web" in sys.argv:
        from .api import run

        run()
    elif "--voice" in sys.argv or "voice" in sys.argv:
        voice()
    else:
        cli()


if __name__ == "__main__":
    main()
