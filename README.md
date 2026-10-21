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
- "Cancela el evento de hoy que ya paso"          # resuelve el id correcto (no cancela otro)
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
- "Que puedes hacer?"                             # tambien /ayuda (o boton Ayuda en la web)
- "Inicia un pomodoro"                             # 25 min de trabajo + 5 de descanso
- "Pon un temporizador de 10 minutos para el horno"  # varios a la vez, con etiqueta
- "Cuanto queda del pomodoro?"                     # y "cancela el temporizador del horno"
- "Mandame la lista de recordatorios por Telegram"
- "Lee mis ultimos 3 correos"
- "Sincroniza mi calendario con Google"          # requiere Google Calendar configurado
- "Recuerda que me gusta el cafe"                  # hecho duradero (global, todos los canales)
- "/memoria"                                       # ver hechos + resumen de la conversacion
- "/olvida cafe"                                   # borrar un hecho (o "/olvida todo")
- "/reset"                                         # nueva conversacion (borra historial y resumen)

Las acciones que modifican datos piden confirmacion (`si` / `no`).

## Configuracion

- `config/settings.yaml`: modelo, parametros web y de voz.
- `.env` (no versionado): credenciales de Telegram y email.

La **semana** ("esta semana", "semana que viene", "semana pasada") empieza en **domingo**
por defecto; se cambia con `week_start: domingo|lunes` en `config/settings.yaml`.

El contexto del modelo (`num_ctx`) esta en **8192** para caber entero en una GPU de 8 GB
(el prompt base ocupa ~6.5k tokens). Si lo subes, comprueba con `ollama ps` que Ollama
sigue usando la GPU y no hace spill a CPU.

### Memoria
Las conversaciones se guardan en SQLite por canal (web, Telegram, CLI, voz y avatar) y
se recuperan al reiniciar; un `pending` guardado permite responder "si" despues de un
reinicio. Cuando la conversacion crece (~30 mensajes) se genera un resumen automatico.
Los hechos de `recuerda que ...` son globales y se comparten entre canales. Se gestionan
con `/memoria`, `/olvida ...` y `/reset`. Configurable en `settings.yaml` (`memory`).

### Router de herramientas
El agente envia por turno solo las tools del dominio detectado (tareas, eventos, email,
etc.) para bajar el prompt (~3k tokens en vez de ~6.5k) y dejar sitio al historial. Si no
hay dominio claro o el modelo no llama ninguna tool, reintenta con todas. Se desactiva
con `tools.mode: full` en `config/settings.yaml`.

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
   para comprobar que esta vivo y `/ayuda` muestra todo lo que sabe hacer. Aviso: **un solo** consumidor de `getUpdates` a la vez
   (no usar `src.tools.messaging` mientras el bot corre). Log en `data/telegram_bot.log`.

### Pomodoro / temporizadores
Di "inicia un pomodoro" (25 min de trabajo + 5 de descanso; descanso largo de 15 cada
4 ciclos), "pon un temporizador de 10 minutos para el horno" (puedes tener varios a
la vez, con nombre), "pausa el pomodoro" o "cancela el temporizador del horno". Se
ejecutan al instante (sin confirmacion). Al terminar, el aviso llega **casi al
momento** (<1 s) por **Telegram** y lo dice el **avatar** (si esta abierto): el
scheduler revisa cada 1 s y la voz se **pre-sintetiza** al crear el temporizador.

Tambien hay una **interfaz** para verlos en vivo y gestionarlos (iniciar, pausar,
reanudar, detener y ajustar tiempos de trabajo/descanso), con **anillo de progreso**
por temporizador:
- **Ventana aparte** en el overlay Electron (siempre encima, se puede ocultar): se abre
  con el boton **🕐** de la barra del avatar (siempre visible; cambia de color segun el
  estado: gris sin temporizadores, azul en trabajo, verde en descanso, ambar si esta
  pausado).
- **Panel** en la UI web (boton **⏱ Temporizador** en la cabecera).

Configurable en `config/settings.yaml`:
```yaml
scheduler:
  tick_s: 1            # cada cuantos segundos se revisan los vencimientos
pomodoro:
  trabajo_min: 25
  descanso_min: 5
  descanso_largo_min: 15
  ciclos: 4
  telegram: true
  avatar: true
  presintetizar: true  # pre-sintetizar la voz del aviso (aviso inmediato)
```

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
