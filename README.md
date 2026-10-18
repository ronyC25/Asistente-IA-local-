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

> **Importante:** usa siempre el Python del entorno virtual (`.\.venv\Scripts\python.exe`).
> Si ejecutas `python` a secas, puede que falten dependencias
> (`ModuleNotFoundError: No module named 'ollama'`). Hay atajos que ya usan el venv:
> `.\start-web.ps1`, `.\start-telegram.ps1` o `.\start.ps1 -Mode web|telegram|voice|cli`.

```powershell
# Atajos (recomendado, usan el .venv automaticamente)
.\start-all.ps1          # TODO: Ollama + web + Telegram + avatar (overlay)
.\start-web.ps1          # servidor web
.\start-telegram.ps1     # bot de Telegram bidireccional

# Equivalente explicito
.\.venv\Scripts\python.exe -m src.main --web

# Chat por texto (CLI)
.\.venv\Scripts\python.exe -m src.main

# Servidor web con interfaz de chat  ->  http://127.0.0.1:8000/
.\.venv\Scripts\python.exe -m src.main --web

# Modo voz (di "hey jarvis")
.\.venv\Scripts\python.exe -m src.main --voice
.\.venv\Scripts\python.exe -m src.main --voice --debug     # diagnostico del wake word
.\.venv\Scripts\python.exe -m src.main --list-audio        # listar microfonos
.\.venv\Scripts\python.exe -m src.main --voice --device 2  # elegir microfono

# Bot de Telegram bidireccional (escribes al bot y responde)
.\.venv\Scripts\python.exe -m src.main --telegram
```

### Avatar Live2D (Fase 7)

> El avatar (overlay/navegador) **necesita el servidor web (`--web`) corriendo**, porque
> es quien sirve `/avatar/`, el WebSocket `/ws` y `/tts`. El modo `--telegram` **no**
> sirve el avatar. La forma facil es `.\start-all.ps1` (levanta todo).

Requiere los assets (una vez) y Electron instalados:
```powershell
# 1) Descargar librerias + modelos (Haru y Wanko)
powershell -ExecutionPolicy Bypass -File avatar\setup_assets.ps1

# 2) Instalar Electron
cd avatar; npm install; cd ..

# 3) Levantar el backend y abrir el avatar
.\.venv\Scripts\python.exe -m src.main --web     # en una terminal
cd avatar; npm start                             # overlay de escritorio
```

- En el navegador: `http://127.0.0.1:8000/avatar/`
- En Electron: ventana transparente siempre visible; el personaje responde por voz
  (micrófono del navegador + wake word "hey jarvis") y mueve los labios con lo que habla.
- **Avatares**: selector en la barra (**Haru**, **Wanko**); el elegido se recuerda.
  Configurables en `config/settings.yaml` (`avatar.models`, `avatar.model`, `avatar.height`).
- **Mover / tamano**: arrastra el avatar por el handle **⠿** de la barra de estado
  (la posición se recuerda en `data/avatar_pos.json`); menú contextual (clic derecho):
  *Centrar*, *Esquina inferior derecha*, *Restablecer posición*. El tamaño se ajusta con
  `avatar.height` (alto en px, por defecto 350).

Escribe (o di) cosas como:

- "Anade una tarea: comprar leche, prioridad alta"
- "Que tareas pendientes tengo?"
- "Que agenda tengo los proximos 3 dias?"      # rangos: hoy, manana, fin de semana, esta semana...
- "Que hay el fin de semana?"
- "Que eventos hay la ultima semana de octubre?"  # tambien: "la primera semana de <mes>"
- "Cuanto falta para el proximo evento?"        # el tiempo restante se calcula en codigo
- "Cual es la nota mas antigua?"                # y "las notas de esta semana"
- "Crea una lista de la compra con leche y pan" # se guarda con sus elementos
- "Recuerdame llamar al banco manana a las 9"
- "Recuerdame tomar agua todos los dias a las 9"        # recordatorio recurrente
- "Agenda una reunion el martes a las 10 en la oficina"
- "Crea una nota: ideas para el proyecto"
- "Crea una lista de la compra y anade leche y pan"
- "Busca donde apunte lo del proyecto"             # buscar_todo: busca en todo a la vez
- "Que tareas estan etiquetadas como compras?"     # etiquetas (tareas, notas, eventos, recordatorios)
- "Crea una subtarea de la tarea 3: revisar el borrador"  # subtareas anidadas
- "Mandame la lista de recordatorios por Telegram"
- "Lee mis ultimos 3 correos"
- "Sincroniza mi calendario con Google"          # requiere Google Calendar configurado

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
3. Para **recibir** mensajes, arranca el bot y deja la terminal abierta:
   ```powershell
   .\start-telegram.ps1
   ```
   Solo responde al chat de `TELEGRAM_CHAT_ID`. El comando `/ping` responde `pong`
   para comprobar que esta vivo. Aviso: **un solo** consumidor de `getUpdates` a la vez
   (no usar `src.tools.messaging` mientras el bot corre). Log en `data/telegram_bot.log`.

### Email (Gmail)
Rellena en `.env`: `EMAIL_ADDRESS`, `EMAIL_PASSWORD` (contrasena de aplicacion),
`IMAP_HOST=imap.gmail.com`, `SMTP_HOST=smtp.gmail.com`.

### Google Calendar (opcional, sincronizacion bidireccional)
Conecta tu calendario con Google via OAuth. Instala las dependencias extra:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-google.txt
```

1. En [Google Cloud Console](https://console.cloud.google.com):
   - Crea un proyecto y habilita **Google Calendar API**.
   - Configura la *pantalla de consentimiento OAuth* (tipo **Externo**) y anadete
     a ti mismo como **usuario de prueba**.
   - Credenciales -> **ID de cliente OAuth** -> tipo **App de escritorio** -> descarga el JSON.
2. Guarda el JSON como `data/google_credentials.json`.
3. Autoriza una vez (abre el navegador):
   ```powershell
   .\start.ps1 -Mode auth
   ```
4. Activa la sincronizacion en `config/settings.yaml`:
   ```yaml
   google_calendar:
     enabled: true
   ```

Uso: al crear/editar/cancelar un evento se sube a Google al momento (si hay
conexion); di o escribe **"sincroniza mi calendario"** para traer los cambios de
Google y subir los pendientes. Los conflictos los gana el cambio mas reciente.
La zona horaria se detecta automaticamente (se puede fijar en `settings.yaml`).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Estado del proyecto

Ver [PROGRESS.md](PROGRESS.md) para el detalle de fases, pendientes y notas.
