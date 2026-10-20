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
| Extra | Bot Telegram bidireccional | Hecho (modo `--telegram`) |
| Extra | Productividad: notas, listas, recordatorios recurrentes | Hecho |
| Extra | Google Calendar API (OAuth, sincronizacion bidireccional) | Hecho |
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
  telegram_bot.py    # bot bidireccional de Telegram (long polling)
  main.py            # CLI / --web / --voice / --telegram
  brain/
    agent.py         # loop de tool-calling + confirmacion + guardarrailes
    prompts.py       # system prompt
    schema.py        # definicion JSON de las 27 herramientas
    registry.py      # registro de tools (read/write)
    confirm.py       # clasificacion si/no + deteccion de intencion
    capabilities.py  # lista de capacidades (respuesta determinista, sin LLM)
    tooltext.py      # recupera tool-calls escritas como texto (JSON/tags)
    voice_guard.py   # filtro anti-eco del microfono (voz/avatar)
  tools/
    tasks.py         # tareas (CRUD)
    reminders.py     # recordatorios (CRUD + recurrencia)
    notes.py         # notas (consultar/gestionar)
    lists.py         # listas/checklists (consultar/gestionar)
    search.py        # busqueda global (buscar_todo) + listar_etiquetas
    _tags.py         # utilidades de etiquetas (normalizacion/filtro)
    timers.py        # temporizadores y pomodoro (aviso via scheduler)
    notify.py        # notificaciones Windows (toast)
    messaging.py     # Telegram
    email_tool.py    # email IMAP/SMTP
    calendar.py      # calendario local + export .ics
    gcal.py          # sincronizacion con Google Calendar (OAuth, bidireccional)
    gcal_auth.py     # autorizacion OAuth (una vez)
  voice/
    wake.py          # openWakeWord (hey_jarvis)
    stt.py           # faster-whisper
    tts.py           # Piper (+ fallback SAPI)
    loop.py          # orquestador de voz
config/settings.yaml # modelo, web, voz
web/index.html       # UI de chat en el navegador
avatar/              # app Live2D + overlay Electron (Fase 7)
  index.html main.js #   escena Live2D + WebSocket + microfono + lip-sync
  timer.html timer.js #  ventana de temporizador/pomodoro (widget compartido)
  electron/          #   ventana overlay transparente y click-through
  setup_assets.ps1   #   descarga librerias + modelos Haru/Wanko (no versionados)
start*.ps1           # lanzadores (venv + modos + start-all + auth)
tests/               # 382 tests (pytest)
```

## Herramientas del agente (27)

- **Tareas**: `crear_tarea` (con `etiquetas` y `padre_id` para subtareas), `listar_tareas`
  (anida `subtareas`), `completar_tarea` (completa tambien las hijas), `editar_tarea`,
  `eliminar_tarea`
- **Recordatorios**: `crear_recordatorio` (con `recurrencia` y `etiquetas`),
  `listar_recordatorios`, `cancelar_recordatorio`
- **Notas**: `consultar_notas` (read), `gestionar_notas` (write)
- **Listas/checklists**: `consultar_listas` (read), `gestionar_listas` (write)
- **Busqueda/organizacion**: `buscar_todo` (busca texto en todos los datos),
  `listar_etiquetas`
- **Temporizadores/Pomodoro**: `consultar_temporizador` (read), `gestionar_temporizador`
  (iniciar/cancelar, **instantaneo**)
- **Notif/Mensajeria/Email**: `enviar_notificacion_windows`, `enviar_telegram`, `leer_email`, `enviar_email`
- **Calendario**: `crear_evento`, `listar_eventos`, `editar_evento`, `cancelar_evento`, `exportar_ics`, `sincronizar_calendario`
- **Sistema**: `fecha_hora_actual`

Etiquetas/categorias: tareas, notas, eventos y recordatorios aceptan `etiquetas`
(lista) al crear/editar y filtran por `etiqueta` (normalizadas en `_tags.py`).
Subtareas: `crear_tarea(padre_id=...)`; `listar_tareas` devuelve cada tarea con sus
`subtareas` anidadas. Busqueda: `buscar_todo` (dominio `busqueda` + extraccion
determinista del termino en `agent._ajustar_args`).

Temporizadores/Pomodoro: `timers.py` (tabla `timers`). Iniciar/cancelar/pausar/
reanudar se resuelve **deterministicamente** en `agent.handle` (via
`confirm.intencion_temporizador`): **instantaneo, sin confirmacion y sin depender del
modelo**. Pomodoro clasico 25/5 (descanso largo 15 cada 4 ciclos) configurable por
temporizador; se permiten **varios** a la vez (con `etiqueta`).
**Aviso al vencer (inmediato)**: el scheduler revisa cada **1 s** (`scheduler.tick_s`)
y el texto/WAV del aviso se **pre-sintetizan** al crear/avanzar el temporizador
(`pomodoro.presintetizar`), asi el aviso sale en **<1 s** (medido ~0.45 s) por
**Telegram** y por el **avatar** (voz + lip-sync). Como `start-all.ps1` corre **dos
schedulers** (web y Telegram), el aviso del avatar se reenvia por HTTP
(`POST /avatar/say`, con el WAV en `wav_b64`) si el proceso que dispara no tiene los WS,
y el despacho usa **reclamo atomico** (en `timers` y en `reminders`) para no duplicar.
Si el avatar no esta abierto, solo Telegram.
**UI**: ventana Electron aparte (`avatar/timer.html` + `timer.js`, always-on-top y
ocultable) con **anillo de progreso + tarjetas** por temporizador (color por fase),
iniciar/pausar/reanudar/detener y tiempos de trabajo/descanso. Se abre con el boton
**🕐** del avatar (**siempre visible**; cambia de color segun estado: gris sin timers,
azul trabajo, verde descanso, ambar pausado) y tambien en la **web** (`web/index.html`,
panel ⏱). Endpoints: `GET/POST /temporizadores`,
`POST /temporizadores/{id}/{pausar|reanudar|cancelar}`, `POST /avatar/say`.
Config en `settings.yaml` (`pomodoro`). Nota: `aviso_wav` (BLOB) **no** se expone en
las respuestas JSON (`timers._row` lo excluye) para no romper la serializacion; se lee
solo con `timers.aviso()`.

Regla: las de **lectura** se ejecutan al instante; las de **escritura** piden
confirmacion ("si/no"). Las tools de notas/listas estan **agrupadas** (un grupo de
consulta y otro de gestion) para no inflar el prompt de herramientas.

Filtros de fecha: `listar_tareas(vencidas=true)`, `listar_recordatorios(vencidos=true)`
y `listar_eventos(pasados=true)` para lo **ya pasado**; `vencen_hoy` para hoy. La
confirmacion de eliminar/completar/cancelar **resuelve el titulo real por id**
(p. ej. *"Eliminar la tarea 5 «Cenar Broster»"*).

Recordatorios: estado **`historial`** = pendientes + enviados (**sin** cancelados).
El agente lo aplica al pedir "la lista / todos mis recordatorios" (ajuste determinista
`agent._ajustar_args` + `confirm.quiere_historial_recordatorios`), porque el modelo
tendia a dejar el estado por defecto (`pendientes`) y decir "no hay ninguno".

Google Calendar: `sincronizar_calendario` hace **pull incremental** (`syncToken`) y
**push** de lo pendiente. Al crear/editar/cancelar un evento se hace un push
*best-effort* inmediato (si esta conectado) y se marca `pending_push=1` como red de
seguridad. Los conflictos los resuelve `google_calendar.conflict_policy`
(por defecto `last_write_wins`: gana el cambio mas reciente; empate -> local).

Rangos de fecha **deterministas**: las tools de listado aceptan `periodo` (+ `dias`):
`hoy`, `manana`, `pasado_manana`, `fin_de_semana`, `esta_semana`, `semana_que_viene`,
`semana_pasada`, `proximos_dias` (N dias naturales desde hoy), `este_mes`, o un dia
(`lunes`..`domingo`). `src/timeutil.resolver_periodo` calcula el rango (no el modelo) y
el **inicio de semana** es configurable (`week_start: domingo|lunes` en `settings.yaml`;
por defecto **domingo**, asi el domingo ya es "esta semana"). El agente ademas lo fuerza
en `agent._ajustar_args` (via `confirm.periodo_de_texto`), descartando `desde`/`hasta`
mal calculados por el LLM. `desde`/`hasta` quedan solo para fechas explicitas.
`listar_eventos` con `periodo` **excluye los eventos ya pasados** (salvo que el rango
sea del pasado o `pasados=true`), asi "que eventos tengo esta semana" no muestra lo de
ayer; para lo ya ocurrido, `confirm.quiere_eventos_pasados` ("que hubo/tuve/pasaron")
fuerza `pasados=true`.

**Cancelar/editar evento por referencia**: `confirm.referencia_evento` ("el que ya
paso", "el de hoy", "el ultimo", "el proximo", "el mas antiguo") + `calendar.resolver_evento`
resuelven el **id correcto** de forma determinista. `agent.handle` intercepta "cancela
el evento que ya paso"/"cancelalo" y propone el evento correcto (sin depender del
modelo); `agent._ajustar_args` sobrescribe el id si el modelo eligio otro. Ademas
`cancelar_evento` acepta `titulo` (cancelar por titulo).

## Como arrancar

> Usa siempre el Python del `.venv` (`.\.venv\Scripts\python.exe`) o los scripts
> `start-*.ps1`. Ejecutar `python` a secas da `ModuleNotFoundError: No module named 'ollama'`.

```powershell
# Atajos (usan el .venv automaticamente)
.\start-all.ps1        # TODO: Ollama + web + Telegram + avatar (overlay)
.\start-web.ps1        # servidor web
.\start-telegram.ps1   # bot de Telegram bidireccional
.\start.ps1 -Mode web|telegram|voice|cli|auth
.\start.ps1 -Mode auth # autorizar Google Calendar (una vez; abre el navegador)

# CLI interactiva
.\.venv\Scripts\python.exe -m src.main

# Servidor web (POST /chat, /health, /docs)
.\.venv\Scripts\python.exe -m src.main --web

# Modo voz (wake word "hey jarvis")
.\.venv\Scripts\python.exe -m src.main --voice
.\.venv\Scripts\python.exe -m src.main --voice --debug        # ver puntuacion wake
.\.venv\Scripts\python.exe -m src.main --list-audio           # listar microfonos
.\.venv\Scripts\python.exe -m src.main --voice --device 2     # elegir microfono

# Bot de Telegram bidireccional (escribir al bot y responde)
.\.venv\Scripts\python.exe -m src.main --telegram

# Tests
.\.venv\Scripts\python.exe -m pytest -q
```

Requisitos: Ollama en ejecucion con `qwen3:8b` (`ollama pull qwen3:8b`).

## Avatar Live2D (Fase 7)

- **Backend**: `src/avatar.py` expone `WS /ws` (mic -> wake word -> Whisper ->
  agente -> Piper) y `POST /tts` (WAV). El parser `src/brain/emotions.py` extrae
  etiquetas `[joy]`... para expresiones.
- **Frontend**: `avatar/` (Pixi 7 + pixi-live2d-display + Cubism Core 4.2.2 + wLipSync),
  servido en `/avatar/`. **Multi-modelo** (Cubism 2.1/3/4): la lista y la escala se leen
  de `GET /avatar/config` (backend). Avatares: **Haru** (Cubism 3, `LipSync =
  ParamMouthOpenY`, expresiones `f00..f07`) y **Wanko** (Cubism 3, perrito chibi,
  `LipSync = PARAM_MOUTH_OPEN_Y`, **sin expresiones**). El parametro de boca se
  **auto-detecta** del grupo `LipSync` del `model3.json`.
- **Tamano**: `avatar.height` en `settings.yaml` (alto del avatar en px; 350 por
  defecto). La ventana del overlay se ajusta a ese alto (abraza al avatar, sin
  espacio vacio arriba). **Selector** de avatar en la barra (persistido en
  `localStorage`).
- **Overlay**: `avatar/electron/` (ventana transparente, siempre visible,
  click-through con `setIgnoreMouseEvents(forward)`). **Arrastrable** por el handle
  (⠿) de la barra de estado (arrastre custom por IPC); la **posicion se guarda** en
  `data/avatar_pos.json` y el menu contextual permite *Centrar / Esquina inf. derecha
  / Restablecer*.
- **Requisito**: el overlay/navegador necesita el **servidor web** (`--web`) corriendo
  (sirve `/avatar/`, `/ws` y `/tts`). El modo `--telegram` NO sirve el avatar.
  Para levantar todo de una vez: `.\start-all.ps1`.
- **Arranque por gesto**: boton "Iniciar" (necesario para `AudioContext`/wLipSync/micro).
- **Assets** (no versionados): descargar con `avatar/setup_assets.ps1`
  (librerias JS, Cubism Core, perfil wLipSync y modelos **Haru** y **Wanko**).
  Electron via `npm install`.

### Protocolo `/ws`
- Entrada: binario PCM int16 16 kHz (microfono) + JSON `{"type":"text"|"mic"|"barge_in"}`.
- Salida: `{"type":"state","value":...}`, `{"type":"reply","text":...}`,
  `{"type":"expression","value":...}`, `{"type":"pending","active":bool}`, y WAV binario.
- `GET /avatar/config`: modelos disponibles, avatar por defecto, escala y perfil wLipSync.

## Bot de Telegram (bidireccional)

- `src/telegram_bot.py`: hilo *daemon* con **long polling** (`getUpdates`, `offset`,
  `timeout` de `telegram.poll_timeout`). Modo dedicado: `python -m src.main --telegram`.
- **Seguridad**: solo procesa mensajes de `TELEGRAM_CHAT_ID` (ignora el resto).
- **Sesion persistente por chat**: la confirmacion "si/no" de acciones de escritura
  funciona entre mensajes. Comandos `/start` y `/reset` reinician la conversacion.
- **`/ping`**: responde `pong (<modelo>)` para comprobar que el bot esta vivo.
- **Log**: `data/telegram_bot.log` (arranque, mensajes recibidos, errores). `_send`
  verifica la respuesta de Telegram (errores 400 ya no pasan en silencio) y trocea
  mensajes >4096 caracteres.
- **Aviso**: solo puede haber **un** consumidor de `getUpdates` a la vez. Mientras
  corre el bot, no usar `python -m src.tools.messaging` (descubrimiento de chat_id).
- Depuracion: el overlay Electron abre DevTools con **F12 / Ctrl+Shift+I** o el menu
  contextual (clic derecho) -> *Abrir DevTools*.

## Configuracion

### `config/settings.yaml`
Modelo, temperatura, contexto, nombre, ruta de BD, host/puerto web y bloque
`voice` (whisper_model, tts_voice, wake_model, wake_threshold, input_device...) y
`google_calendar` (enabled, calendar_id, credentials_file, token_file, timezone,
conflict_policy).

### `.env` (no se versiona; copia de `.env.example`)
| Clave | Estado |
|-------|--------|
| `ASSISTANT_MODEL` | `qwen3:8b` |
| `TELEGRAM_BOT_TOKEN` | Configurado |
| `TELEGRAM_CHAT_ID` | Configurado |
| `EMAIL_ADDRESS` / `EMAIL_PASSWORD` | **Vacio (pendiente)** |
| `IMAP_HOST` / `SMTP_HOST` | **Vacio (pendiente)** |
| `GOOGLE_CALENDAR_ID` | `primary` (opcional) |

Para Gmail: `imap.gmail.com:993`, `smtp.gmail.com:587` y una **contrasena de
aplicacion** (requiere verificacion en 2 pasos).

## Dependencias

- `requirements.txt`: ollama, fastapi, uvicorn, pydantic, PyYAML, python-dotenv,
  python-dateutil, APScheduler, httpx
- `requirements-voice.txt`: faster-whisper, openwakeword, sounddevice, numpy, piper-tts
- `requirements-google.txt`: google-api-python-client, google-auth-oauthlib,
  google-auth-httplib2, tzlocal (sincronizacion con Google Calendar)
- `requirements-dev.txt`: pytest, httpx

## Pendientes / proximos pasos

1. **Gmail**: rellenar los 5 campos de `.env` y verificar `leer_email`/`enviar_email`.
2. **Pulido de la UI web**: memoria de conversacion persistente, visor de logs e
   icono en la bandeja del sistema.
3. **Bot Telegram bidireccional**: escuchar mensajes entrantes (long polling de
   `getUpdates`) para controlar el asistente desde el chat de Telegram. **Hecho**
   (modo `--telegram`, `src/telegram_bot.py`).
4. **Google Calendar API**: sincronizacion real (OAuth en Google Cloud) en lugar
   del export manual a `.ics`. **Hecho** (modo `auth`, `src/tools/gcal.py`,
   tool `sincronizar_calendario`).
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
- **Rendimiento LLM**: qwen3 con *thinking* ON generaba ~10x mas tokens y ~18x mas
  tiempo (medido: 7.17s/103 tok vs 0.40s/10 tok). Ahora se llama con `think=False`,
  `num_predict: 400`, `keep_alive: 30m`, `num_ctx: 6144` e `history_limit: 16`
  (recorte de historial por sesion). Todo configurable en `settings.yaml`.
- **Guardarrail de consultas**: si el modelo responde una CONSULTA (tareas,
  recordatorios, calendario, correo) sin llamar a la herramienta de lectura, el
  agente le insiste (`_NUDGE_READ`, `looks_like_query`) y, si aun asi no la llama,
  reintenta una vez con `think=True`.
- **Fiabilidad de consultas** (modelo pequeno = inconsistente): sinonimos
  ('notificaciones'/'avisos'/'alarmas' = recordatorios; 'notas', 'listas'...),
  deteccion de dominio (`confirm.dominio_lectura`) e **inyeccion determinista** de la
  herramienta de lectura si el modelo no la llama o llama a la equivocada
  (`agent._ajustar_args`). Si tras los reintentos sigue sin llamar ninguna, el agente
  **ejecuta la lectura y pide el resumen** (fallback). **Cortador de bucle**: si el
  modelo re-llama lecturas ya ejecutadas en el turno, se fuerza un resumen sin
  herramientas (evita "demasiados pasos" en sesiones largas).
- **Parametros inventados por el modelo**: `agent._sanear_args` normaliza alias
  (`pendientes=True` -> `estado='pendientes'`, `completadas=True` -> `estado='completadas'`)
  y **descarta** claves que no existen en el schema de la tool, evitando errores tipo
  "listar_tareas no acepta el parametro pendientes". Ademas `confirm.estado_tareas_de_texto`
  fuerza `estado='completadas'` en "que tareas complete/termine" (tambien en la
  inyeccion determinista `_args_dominio`).
- **Capacidades/ayuda**: "¿que puedes hacer?", "tus funciones", "ayuda" o `/ayuda` se
  responden de forma **determinista** desde `src/brain/capabilities.py` (lista generada
  a partir del registro de tools, **sin pasar por el LLM**) → completa y sin truncar
  (evita el tope de `num_predict`). Tampoco disparan el "nudge" de lectura. El comando
  `/ayuda` esta tambien en Telegram y en la CLI, y hay boton *Ayuda* en la web.
- **Nombre exacto del evento**: "¿cual es el nombre completo del ultimo evento?",
  "el primero", "el proximo", "cuando es..." se resuelven **deterministicamente**
  (sin LLM) con `confirm.pregunta_nombre_evento` + `agent._describir_evento_solicitado`.
  Usa el ultimo listado (`session.ultimos_eventos`, que ahora guarda el `titulo`), el
  periodo si se indica, o el pasado mas reciente; devuelve el **titulo literal** (el
  modelo lo parafraseaba, p. ej. "topicos" -> "temas").
- **Tool-calls escritas como texto**: algunos modelos devuelven
  `{"name": "...", "arguments": {...}}` en el contenido. `src/brain/tooltext.py` las
  detecta y `agent._run_loop` las **convierte en llamadas reales** (las lecturas se
  ejecutan; las escrituras siguen pidiendo confirmacion). Si al final queda texto con
  pinta de codigo, se sustituye por una peticion de aclaracion (nunca se muestra/habla).
- **Barge-in y anti-eco (avatar/voz)**: al detectar la wake word durante la
  reproduccion, el backend envia `stop_speaking` y el avatar corta el audio al instante
  (`avatar/main.js`). Se prioriza `echoCancellation` en el micro y
  `src/brain/voice_guard.py` ignora transcripciones que son un eco del ultimo audio
  (evita que el modelo se confunda y responda JSON). Escribir mientras habla tambien
  corta la reproduccion.
- **Consultas limpias**: se descartan bloques `<think>` (aunque `think=False`, qwen3 a
  veces los filtra) y, si tras una lectura el modelo devuelve solo razonamiento o algo
  vacio, se pide un resumen **sin herramientas** con los datos ya leidos. Ademas, una
  consulta pura (`que listas tengo`) ya **no propone escrituras** que el modelo inventa
  al leer (se ejecuta la lectura y se resume).
- **Notas/listas/eventos**: `consultar_notas` filtra por `periodo`/`dias`/`desde`/
  `hasta` y `orden` (recientes/antiguas); `gestionar_listas(accion='crear', items=[...])`
  crea la lista **con sus elementos en una sola llamada** y `consultar_listas('listar')`
  devuelve los items; `listar_eventos` acepta `orden` (proximos/antiguos). Ademas,
  eventos, recordatorios y tareas incluyen un campo calculado **`faltan`** ("cuanto
  falta") para no depender de la aritmetica del modelo.
- **Fechas explicitas y rangos**: `confirm.fecha_de_texto` ("28 de octubre", "28/10/2026",
  "2026-10-28"; ano siguiente si ya paso) y `confirm.rango_de_texto` ("de aqui a dos
  semanas", "en 3 dias", "proximas N semanas/meses", **"la ultima/primera semana de
  `<mes>`"** o "del mes" → bloques de 7 dias: ultima = fin−6..fin); `agent._ajustar_args`
  los fija como `desde`/`hasta` en las tools de listado (eventos, notas, tareas,
  recordatorios). `hasta` de solo fecha se interpreta como **fin del dia**
  (`parse_datetime(..., end_of_day=True)`), para no excluir los eventos de ese dia. Los
  resultados de las tools se **recortan a campos esenciales** (evita respuestas vacias
  del modelo con listas grandes).
- **Fechas relativas**: qwen3:8b calculaba mal los rangos (p. ej. "proximos 3 dias"
  desde el dia equivocado). Ahora se resuelven en codigo con `periodo`
  (`src/timeutil.resolver_periodo`) y se fuerzan en `agent._ajustar_args`; el modelo
  solo elige la etiqueta.
- **Formato de salida**: las respuestas se limpian de Markdown (`src/brain/textfmt.py`
  via `limpiar_respuesta`) para que no aparezcan asteriscos/negritas/backticks ni en
  los mensajes ni en la voz.
- **Dos schedulers (web + Telegram)**: `start-all.ps1` arranca el servidor web y el
  bot de Telegram en **procesos distintos**; **ambos** lanzan el scheduler. Para no
  duplicar avisos, los recordatorios y temporizadores usan **reclamo atomico**
  (`UPDATE ... WHERE estado=... ` condicional) y el aviso del avatar se reenvia por
  `POST /avatar/say` al proceso web (el unico con los WS del avatar). Bug previo: el
  proceso de Telegram ganaba la carrera, enviaba el Telegram pero **no** podia avisar
  al avatar.
- **Secretos**: `.env`, `data/*.db` y `data/voices/` estan en `.gitignore`.
- **Google Calendar**: requiere `requirements-google.txt`, autorizar una vez
  (`start.ps1 -Mode auth`) y `google_calendar.enabled: true`. Credenciales/token en
  `data/google_credentials.json` y `data/google_token.json` (**gitignored**).
  Offline-first: sin red/token el CRUD local sigue funcionando y el push queda
  pendiente (`pending_push`). El pull es incremental (`syncToken`; si caduca con
  HTTP 410 se hace resync completo). Solo sincroniza mientras la app esta abierta.
- **Avatar**: los assets (`avatar/vendor`, `avatar/public/models`, `node_modules`)
  no se versionan; usar `avatar/setup_assets.ps1`. El lip-sync usa el perfil de
  ejemplo de wLipSync y el parametro se lee del grupo `LipSync` del modelo.
  **Haru** y **Wanko** son Cubism 3 (`moc3` v1) → compatibles con el Core 4.2.2.
  Wanko no tiene expresiones (las etiquetas de emocion solo afectan a Haru).
- **Modelo Mao (Cubism 5) = mejora futura (Opcion 2)**: `moc3` v5 no lo lee el
  Core 4.2.2 ni `pixi-live2d-display` 0.4. Requiere render Cubism 5 (Pixi 8, p. ej.
  `pixi-live2d5`) + Cubism Core 6.0.1; a cambio da lip-sync por vocales (A/I/U/E/O).

## Estado de datos

- `data/assistant.db`: contiene tareas/recordatorios/eventos del usuario.
- `data/voices/`: voces Piper descargadas (120 MB, regenerables).
- `data/calendario.ics`: export del calendario.
