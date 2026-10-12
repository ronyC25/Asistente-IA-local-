# PROGRESS - Asistente IA local "Jarvis"

Documento de traspaso para retomar el proyecto. Resume que hay hecho, como
arrancarlo, la configuracion necesaria y lo que queda pendiente.

## Resumen

Asistente personal **100% local** (sin nube) para gestionar tareas,
recordatorios, calendario, notificaciones, Telegram y correo, con interfaz de
**texto** (CLI / API web) y de **voz** (wake word + STT + TTS).

- LLM local: **Ollama + `qwen3:8b`** (function calling).
- Agente propio con **confirmacion obligatoria** antes de ejecutar acciones que
  modifican datos.
- Datos en **SQLite** (`data/assistant.db`).

## Estado por fases

| Fase | Descripcion | Estado |
|------|-------------|--------|
| 0 | Entorno (Ollama, venv, deps) | Hecho |
| 1 | Nucleo de texto + tareas | Hecho |
| 2 | Recordatorios + notificaciones Windows | Hecho |
| 3 | Telegram + email | Hecho (email sin configurar) |
| 4 | Calendario local (SQLite + export .ics) | Hecho |
| 5 | Voz (wake word + STT + TTS) | Hecho |
| 6 | UI web + pulido | Hecho (UI de chat web) |
| 7 | Avatar Live2D + overlay Electron + lip-sync | Hecho |
| Extra | Bot Telegram bidireccional | Pendiente |
| Extra | Google Calendar API (OAuth) | Pendiente |
| Extra | Wake word en el navegador | Pendiente (cambio futuro) |

## Estructura

```
src/
  config.py          # carga settings.yaml + .env
  db.py              # conexion SQLite
  timeutil.py        # parseo de fechas
  factory.py         # construye el agente
  api.py             # FastAPI (/chat, /health)
  scheduler.py       # APScheduler (recordatorios)
  main.py            # CLI / --web / --voice
  brain/
    agent.py         # loop de tool-calling + confirmacion + guardarrailes
    prompts.py       # system prompt
    schema.py        # definicion JSON de las 18 herramientas
    registry.py      # registro de tools (read/write)
    confirm.py       # clasificacion si/no + deteccion de intencion
  tools/
    tasks.py         # tareas (CRUD)
    reminders.py     # recordatorios (CRUD)
    notify.py        # notificaciones Windows (toast)
    messaging.py     # Telegram
    email_tool.py    # email IMAP/SMTP
    calendar.py      # calendario local + export .ics
  voice/
    wake.py          # openWakeWord (hey_jarvis)
    stt.py           # faster-whisper
    tts.py           # Piper (+ fallback SAPI)
    loop.py          # orquestador de voz
config/settings.yaml # modelo, web, voz
web/index.html       # UI de chat en el navegador
avatar/              # app Live2D + overlay Electron (Fase 7)
  index.html main.js #   escena Live2D + WebSocket + microfono + lip-sync
  electron/          #   ventana overlay transparente y click-through
  setup_assets.ps1   #   descarga librerias + modelo Mao (no versionados)
tests/               # 72 tests (pytest)
```

## Herramientas del agente (18)

- **Tareas**: `crear_tarea`, `listar_tareas`, `completar_tarea`, `editar_tarea`, `eliminar_tarea`
- **Recordatorios**: `crear_recordatorio`, `listar_recordatorios`, `cancelar_recordatorio`
- **Notif/Mensajeria/Email**: `enviar_notificacion_windows`, `enviar_telegram`, `leer_email`, `enviar_email`
- **Calendario**: `crear_evento`, `listar_eventos`, `editar_evento`, `cancelar_evento`, `exportar_ics`
- **Sistema**: `fecha_hora_actual`

Regla: las de **lectura** se ejecutan al instante; las de **escritura** piden
confirmacion ("si/no").

## Como arrancar

```powershell
# CLI interactiva
.\.venv\Scripts\python.exe -m src.main

# Servidor web (POST /chat, /health, /docs)
.\.venv\Scripts\python.exe -m src.main --web

# Modo voz (wake word "hey jarvis")
.\.venv\Scripts\python.exe -m src.main --voice
.\.venv\Scripts\python.exe -m src.main --voice --debug        # ver puntuacion wake
.\.venv\Scripts\python.exe -m src.main --list-audio           # listar microfonos
.\.venv\Scripts\python.exe -m src.main --voice --device 2     # elegir microfono

# Tests
.\.venv\Scripts\python.exe -m pytest -q
```

Requisitos: Ollama en ejecucion con `qwen3:8b` (`ollama pull qwen3:8b`).

## Avatar Live2D (Fase 7)

- **Backend**: `src/avatar.py` expone `WS /ws` (mic -> wake word -> Whisper ->
  agente -> Piper) y `POST /tts` (WAV). El parser `src/brain/emotions.py` extrae
  etiquetas `[joy]`... para expresiones.
- **Frontend**: `avatar/` (Pixi + pixi-live2d-display + Cubism Core + wLipSync),
  servido en `/avatar/`. Modelo: **Mao** (ejemplo oficial, Cubism 3.x).
- **Overlay**: `avatar/electron/` (ventana transparente, siempre visible,
  click-through con `setIgnoreMouseEvents(forward)`).
- **Assets** (no versionados): descargar con `avatar/setup_assets.ps1`
  (librerias JS, Cubism Core, perfil wLipSync y modelo Mao). Electron via `npm install`.

### Protocolo `/ws`
- Entrada: binario PCM int16 16 kHz (microfono) + JSON `{"type":"text"|"mic"|"barge_in"}`.
- Salida: `{"type":"state","value":...}`, `{"type":"reply","text":...}`,
  `{"type":"expression","value":...}`, `{"type":"pending","active":bool}`, y WAV binario.

## Configuracion

### `config/settings.yaml`
Modelo, temperatura, contexto, nombre, ruta de BD, host/puerto web y bloque
`voice` (whisper_model, tts_voice, wake_model, wake_threshold, input_device...).

### `.env` (no se versiona; copia de `.env.example`)
| Clave | Estado |
|-------|--------|
| `ASSISTANT_MODEL` | `qwen3:8b` |
| `TELEGRAM_BOT_TOKEN` | Configurado |
| `TELEGRAM_CHAT_ID` | Configurado |
| `EMAIL_ADDRESS` / `EMAIL_PASSWORD` | **Vacio (pendiente)** |
| `IMAP_HOST` / `SMTP_HOST` | **Vacio (pendiente)** |

Para Gmail: `imap.gmail.com:993`, `smtp.gmail.com:587` y una **contrasena de
aplicacion** (requiere verificacion en 2 pasos).

## Dependencias

- `requirements.txt`: ollama, fastapi, uvicorn, pydantic, PyYAML, python-dotenv,
  python-dateutil, APScheduler, httpx
- `requirements-voice.txt`: faster-whisper, openwakeword, sounddevice, numpy, piper-tts
- `requirements-dev.txt`: pytest, httpx

## Pendientes / proximos pasos

1. **Gmail**: rellenar los 5 campos de `.env` y verificar `leer_email`/`enviar_email`.
2. **Pulido de la UI web**: memoria de conversacion persistente, visor de logs e
   icono en la bandeja del sistema.
3. **Bot Telegram bidireccional**: escuchar mensajes entrantes (long polling de
   `getUpdates`) para controlar el asistente desde el chat de Telegram.
4. **Google Calendar API**: sincronizacion real (OAuth en Google Cloud) en lugar
   del export manual a `.ics`.
5. **Wake word personalizado**: entrenar un modelo para activarlo diciendo solo
   "Jarvis" en espanol.

## Notas conocidas / problemas

- **Wake word**: el modelo `hey_jarvis` esta entrenado en **ingles**. Con
  pronunciacion espanola la puntuacion cae (~0.002); con inglesa detecta ~0.998.
  Usar `--debug` para ver la puntuacion. Para espanol, entrenar modelo propio.
- **Whisper**: corre en **CPU** por defecto. Para GPU hay que instalar el runtime
  CUDA 12 + cuDNN y poner `whisper_device: cuda` (con fallback automatico a CPU).
- **Scheduler**: los recordatorios solo se disparan mientras la app esta abierta.
- **Modelo**: `qwen3:8b` a veces necesita el guardarrail de "nudge" para completar
  acciones de escritura tras una lectura (ya implementado en `agent.py`).
- **Secretos**: `.env`, `data/*.db` y `data/voices/` estan en `.gitignore`.
- **Avatar**: los assets (`avatar/vendor`, `avatar/public/models`, `node_modules`)
  no se versionan; usar `avatar/setup_assets.ps1`. El lip-sync usa el perfil de
  ejemplo de wLipSync (el mio viene de su repo; si no cargara, se puede ajustar).
  Modelo Mao = Cubism 3.x (compatible con el runtime Cubism 4 de pixi-live2d-display).

## Estado de datos

- `data/assistant.db`: contiene tareas/recordatorios/eventos del usuario.
- `data/voices/`: voces Piper descargadas (120 MB, regenerables).
- `data/calendario.ics`: export del calendario.
