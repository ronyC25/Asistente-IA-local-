# Asistente IA local "Jarvis"

Asistente personal **local y privado** (sin nube) para gestionar tareas,
recordatorios, calendario, notificaciones, Telegram y correo, con interfaz de
**texto** y de **voz**.

- LLM local via **Ollama** (`qwen3:8b`) con *function calling*.
- Agente con **confirmacion** antes de ejecutar acciones que cambian datos.
- Voz: wake word (**openWakeWord**) + STT (**faster-whisper**) + TTS (**Piper**).

## Requisitos

- Windows 10/11, Python 3.11
- [Ollama](https://ollama.com) instalado y en ejecucion
- Microfono y altavoces (solo para el modo voz)

## Instalacion

```powershell
# 1) Entorno virtual y dependencias
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 2) (Opcional) dependencias de voz
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt

# 3) Modelo del LLM
ollama pull qwen3:8b

# 4) Configuracion: copia el ejemplo y rellena tus datos
Copy-Item .env.example .env
```

## Uso

```powershell
# Chat por texto (CLI)
.\.venv\Scripts\python.exe -m src.main

# Servidor web  ->  http://127.0.0.1:8000/docs
.\.venv\Scripts\python.exe -m src.main --web

# Modo voz (di "hey jarvis")
.\.venv\Scripts\python.exe -m src.main --voice
.\.venv\Scripts\python.exe -m src.main --voice --debug     # diagnostico del wake word
.\.venv\Scripts\python.exe -m src.main --list-audio        # listar microfonos
.\.venv\Scripts\python.exe -m src.main --voice --device 2  # elegir microfono
```

Escribe (o di) cosas como:

- "Anade una tarea: comprar leche, prioridad alta"
- "Que tareas pendientes tengo?"
- "Recuerdame llamar al banco manana a las 9"
- "Agenda una reunion el martes a las 10 en la oficina"
- "Mandame la lista de recordatorios por Telegram"
- "Lee mis ultimos 3 correos"

Las acciones que modifican datos piden confirmacion (`si` / `no`).

## Configuracion

- `config/settings.yaml`: modelo, parametros web y de voz.
- `.env` (no versionado): credenciales de Telegram y email.

### Telegram
1. Crea un bot con `@BotFather` y copia el token en `TELEGRAM_BOT_TOKEN`.
2. Envia un mensaje a tu bot y ejecuta:
   ```powershell
   .\.venv\Scripts\python.exe -m src.tools.messaging
   ```
   Copia el `chat_id` en `TELEGRAM_CHAT_ID`.

### Email (Gmail)
Rellena en `.env`: `EMAIL_ADDRESS`, `EMAIL_PASSWORD` (contrasena de aplicacion),
`IMAP_HOST=imap.gmail.com`, `SMTP_HOST=smtp.gmail.com`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Estado del proyecto

Ver [PROGRESS.md](PROGRESS.md) para el detalle de fases, pendientes y notas.
