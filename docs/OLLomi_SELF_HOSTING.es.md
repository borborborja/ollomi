# Ollomi: instalación y operación

Ollomi es un fork local de Omi. El servicio activo es `selfhost.main:app`; el backend comercial original no entra en la imagen Docker. La aplicación Android puede grabar con el micrófono del teléfono, capturar una llamada cuando Android lo permita, descubrir y conectar un dispositivo Omi/Friend compatible o importar MP3, M4A, WAV, OGG y FLAC. Incluye autenticación local y servidor configurable. Véanse [investigación](OLLomi_RESEARCH.es.md) y [validación y límites](OLLomi_VALIDATION.md).

## Instalación preparada en este equipo

Workspace: `/opt/projects/ollomi/ollomi.code-workspace`. El backend preparado escucha en `http://127.0.0.1:18080`, porque el puerto 8080 ya estaba ocupado. La cuenta `admin@ollomi.local` y su contraseña aleatoria están en `artifacts/initial-admin.txt` (permisos 600, fuera de Git). No vuelva a inicializar ni a crear esa cuenta. La APK está en `artifacts/ollomi-dev.apk` y su suma de verificación en `artifacts/SHA256SUMS`. La copia privada inicial de datos y claves está en `artifacts/backup-initial/`; conserve esos archivos fuera de repositorios públicos.

Esta instalación ya tiene Whisper `tiny`, Ollama `qwen3:0.6b`, `embeddinggemma` y la voz Piper `es_ES-davefx-medium`. Los perfiles predeterminados se han ajustado a esos modelos. La cuenta y perfiles usados para las pruebas están deshabilitados; sus audios son sintéticos. Las instrucciones siguientes sirven también para instalar desde cero en otra máquina.

## Requisitos

Docker Engine con Compose v2, Linux, almacenamiento persistente y un navegador o Android. Para desarrollar Android: Flutter 3.44.5, Java 21, SDK Android 36 y NDK 29.0.14206865. Las imágenes y los pesos se descargan durante la instalación; el funcionamiento posterior puede permanecer sin salida a Internet.

Reserve al menos 25 GB libres para compilar las imágenes y la app, más los modelos y audios. Para uso en CPU, 16 GB de RAM es un punto de partida razonable; los recursos necesarios dependen del modelo y de las grabaciones simultáneas. No compile Android mientras ejecuta inferencia en una máquina ajustada de memoria. El modelo de 0,6 B utilizado en la prueba verifica el recorrido técnico, pero su calidad no equivale a la de modelos mayores.

## Primera instalación con imágenes publicadas

La vía más rápida descarga las imágenes públicas de GitHub Container Registry y no compila el backend:

```bash
git clone https://github.com/borborborja/ollomi.git
cd ollomi
read -rsp 'Contraseña inicial: ' INITIAL_ADMIN_PASSWORD; echo
export INITIAL_ADMIN_PASSWORD
python3 scripts/selfhost_init.py --bind 0.0.0.0 \
  --admin-email admin@example.com \
  --admin-password-env INITIAL_ADMIN_PASSWORD
unset INITIAL_ADMIN_PASSWORD
```

El inicializador crea `.env` con permisos 600, escribe la cadena `COMPOSE_FILE`, usa por defecto las imágenes GHCR de `borborborja` y elige el primer puerto libre entre 8080, 8090 y los siguientes. `--bind 0.0.0.0` permite acceder desde el teléfono. Para usar únicamente proveedores de la LAN o Internet, use `--external-ai`; esta opción incluye `deploy/compose.connected.yaml`, fija `OLLOMI_LOCAL_ONLY=false` y no activa los perfiles `local-whisper` ni `local-ollama`.

```bash
docker compose pull
docker compose run --rm model-downloader --stt small
docker compose -f compose.yaml -f deploy/compose.ghcr.yaml \
  -f deploy/compose.connected.yaml --profile local-ollama up -d ollama
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama pull embeddinggemma
docker compose up -d
```

El arranque final vuelve a aplicar la cadena guardada en `.env` y retira de Ollama la red temporal de descarga. Si inicializó con `--external-ai`, omita la descarga de Whisper y los tres comandos de Ollama. Configure en `.env` al menos un perfil externo para STT, chat y embeddings antes de arrancar; no se crea, descarga ni ejecuta ningún contenedor de IA local.

Compose lee `COMPOSE_FILE` y `COMPOSE_PROFILES` desde `.env`; ya no hay que repetir `-f` ni exportar `OLLOMI_IMAGE_OWNER` en cada comando. Compruebe los valores elegidos con:

```bash
grep -E '^(COMPOSE_FILE|COMPOSE_PROFILES|OLLOMI_PORT)=' .env
docker compose config --quiet
```

El administrador se crea durante el primer arranque. El seed es idempotente: si el correo ya existe no cambia su contraseña, rol ni otros datos. Después de iniciar sesión correctamente, elimine `OLLOMI_ADMIN_PASSWORD` de `.env` y retire la variable del contenedor:

```bash
docker compose up -d --force-recreate migrate api worker scheduler
curl "http://127.0.0.1:$(sed -n 's/^OLLOMI_PORT=//p' .env)/health"
docker compose ps
```

La respuesta de salud debe ser `{"status":"ok"}`. `migrate` termina con código 0; los demás servicios permanecen activos. El backend y el worker usan la misma imagen `ollomi-backend`; `ollomi-speech` contiene el servidor compatible con la API de transcripción de OpenAI. PostgreSQL, Redis, Typesense y Ollama usan sus imágenes oficiales fijadas en `compose.yaml`.

### Compose autónomo con solo APIs externas

El directorio [`deploy/examples/external-api`](../deploy/examples/external-api/README.md) contiene un `compose.yaml` copiable que referencia directamente `ghcr.io/borborborja/ollomi-backend`. Su `env.example` enumera los ajustes de la instancia y todas las propiedades de los perfiles numerados, con ejemplos de OpenAI, OpenRouter, un endpoint compatible y Ollama en otra máquina. Esta variante no contiene servicios `stt`, `model-downloader` u `ollama`, por lo que no necesita pesos de Whisper ni el directorio `selfhost-data/models`.

```bash
mkdir ollomi && cd ollomi
curl -LO https://raw.githubusercontent.com/borborborja/ollomi/main/deploy/examples/external-api/compose.yaml
curl -Lo .env https://raw.githubusercontent.com/borborborja/ollomi/main/deploy/examples/external-api/env.example
chmod 600 .env
# Edite .env y sustituya todos los valores CHANGE_ME.
docker compose config --quiet
docker compose pull
docker compose up -d
```

La imagen queda fijada por `OLLOMI_IMAGE_TAG`; se recomienda una etiqueta de release como `v0.3.1`. `latest` sigue cada publicación de `main`. El Compose conserva localmente PostgreSQL/pgvector, Redis, Typesense y los audios: solo salen del servidor las peticiones de inferencia configuradas.

También puede crear o restablecer cuentas sin terminal interactivo. La contraseña se lee de una variable transmitida al contenedor o de una sola línea de entrada estándar; nunca la pase como argumento `--password`, porque quedaría visible en `ps`:

```bash
read -rsp 'Contraseña: ' OLLOMI_ADMIN_PASSWORD; echo
export OLLOMI_ADMIN_PASSWORD
docker compose exec -T -e OLLOMI_ADMIN_PASSWORD api \
  python -m selfhost.cli create-admin --email otra@example.com \
  --password-env OLLOMI_ADMIN_PASSWORD
unset OLLOMI_ADMIN_PASSWORD
```

## Primera instalación compilando desde el código

```bash
git clone https://github.com/borborborja/ollomi.git
cd ollomi
python3 scripts/selfhost_init.py --source-build
docker compose build
docker compose up -d postgres redis typesense migrate
```

Los Dockerfiles que usa GitHub Actions también se pueden ejecutar directamente:

```bash
docker build -f deploy/Dockerfile -t ollomi-backend:local .
docker build -f services/speech/Dockerfile -t ollomi-speech:local services/speech
```

`deploy/Dockerfile` compila el backend autoalojado. `services/speech/Dockerfile` compila el servidor Whisper; no hace falta construir esta segunda imagen si todo el STT se delega a una API externa. El workflow `.github/workflows/ollomi-release.yml` publica ambas imágenes para `linux/amd64` con etiquetas de rama, release y SHA; `latest` se actualiza desde `main`.

El inicializador crea `.env` con permisos 600 y claves independientes. No lo sobrescribe. Conserve `OLLOMI_SECRET_KEY`: cifra las credenciales de IA y firma las sesiones. Cambiarla invalida sesiones e impide descifrar las credenciales antiguas.

Instale Whisper con el servicio de descarga de una sola ejecución. Este usa el mismo volumen y usuario que el despliegue y solo se inicia al invocarlo:

```bash
docker compose run --rm model-downloader --stt small
```

Los valores admitidos son `tiny`, `base`, `small`, `medium`, `large-v2` y `large-v3`. El contenedor STT funciona después sin red y monta los pesos como solo lectura.

Para un modelo personalizado de faster-whisper/CTranslate2, copie su directorio completo bajo `selfhost-data/models/`. En el perfil STT, el modelo es el nombre de ese directorio o una ruta bajo `/models`; nunca una ruta arbitraria del host.

Descargue los modelos Ollama con la red conectada temporalmente:

```bash
docker compose -f compose.yaml -f deploy/compose.connected.yaml \
  --profile local-ollama up -d ollama
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama pull embeddinggemma
docker compose up -d
```

Whisper y Ollama están bajo los perfiles `local-whisper` y `local-ollama`. El inicializador normal escribe `COMPOSE_PROFILES=local-whisper,local-ollama`. `--without-local-ollama` mantiene solo Whisper; `--external-ai` omite ambos y evita crear perfiles que apunten a esos contenedores. Puede activar Ollama más tarde añadiéndolo a `COMPOSE_PROFILES` y fijando `OLLOMI_SEED_LOCAL_OLLAMA=true`. Para activar Whisper local, añada `local-whisper` y configure `OLLOMI_STT1_PROVIDER=whisper` y `OLLOMI_STT1_MODEL` con el modelo descargado.

La configuración inicial fija por entorno Whisper `small`, chat `qwen3:4b` y `embeddinggemma`. En hardware pequeño puede instalar `tiny` y `qwen3:0.6b` y cambiar `OLLOMI_STT1_MODEL` y `OLLOMI_CHAT1_MODEL` en `.env`. Con Ollama 0.11.10 y Qwen3, añada `OLLOMI_CHAT1_OPTIONS={"prompt_suffix":"/no_think","max_tokens":2048}` si quiere evitar pensamiento extendido. La compatibilidad de opciones depende de la versión del servidor; compruebe el estado desde Android.

## Acceso desde Android

El inicializador intenta 8080 y después 8090 si el primero está ocupado; el valor definitivo está en `OLLOMI_PORT`. Cambie `OLLOMI_BIND` por la dirección LAN del servidor para acceder desde un teléfono. Vuelva a crear el proxy con `docker compose up -d proxy`. En el emulador Android, `10.0.2.2` apunta al host.

Instale la APK y escriba en la pantalla de entrada la URL del backend, correo y contraseña locales. Desde Ajustes → servidor puede ver el modelo activo y la salud de cada fallback STT/chat/embeddings, administrar usuarios, importar audio y exportar datos. Cuando los modelos están definidos en `.env`, la app no permite editarlos ni seleccionarlos. Para cambiar de servidor, cierre sesión y entre con la nueva URL. La sesión, las importaciones pendientes y los metadatos WAL se vinculan al servidor y a la cuenta.

Cada cambio en `main` crea una APK firmada en [Actions → Publish Ollomi](https://github.com/borborborja/ollomi/actions/workflows/ollomi-release.yml). Abra la ejecución más reciente, baje hasta **Artifacts** y descargue `ollomi-android-<commit>`; dentro están `ollomi.apk` y `SHA256SUMS`. Una etiqueta `v*` publica los mismos archivos en [Releases](https://github.com/borborborja/ollomi/releases). La firma se conserva entre compilaciones, por lo que una APK publicada puede actualizar otra APK publicada sin desinstalarla. El paso desde una APK de desarrollo firmada con otra clave puede requerir una única desinstalación.

Una pulsación larga sobre `+` permite elegir la fuente: micrófono del teléfono, llamada, dispositivo compatible conectado o importar audio. La captura de llamadas depende de las restricciones del fabricante y la versión de Android. La opción del dispositivo permite buscar y asociar un Omi/Friend compatible por Bluetooth; después usa esa conexión.

La APK de desarrollo se construye así:

```bash
cd app
flutter pub get
flutter build apk --debug --flavor dev --target-platform android-arm64,android-x64
```

Para distribuir una versión definitiva, configure una clave de firma propia en Gradle y compile el sabor `prod` en modo release. La APK de desarrollo entregada no es una publicación en Google Play.

El selector acepta MP3, WAV, M4A, OGG y FLAC. También acepta «Compartir» audio desde otras apps Android. La copia pendiente del teléfono se elimina solo cuando el servidor confirma la admisión duradera. Puede cancelar/reintentar trabajos; un fallo de IA conserva el original. Un reintento explícito utiliza los perfiles seleccionados en ese momento, para poder corregir URL, credenciales o modelo. La subida está limitada a 1 GiB y 12 horas por grabación de forma predeterminada.

## IA local y servidores compatibles

El método recomendado es definir cadenas ordenadas en `.env`. Para cada propósito use un número creciente; el backend prueba el siguiente perfil si el anterior falla:

```dotenv
OLLOMI_CHAT1_PROVIDER=ollama
OLLOMI_CHAT1_MODEL=qwen3:4b
OLLOMI_CHAT2_PROVIDER=ollama-cloud
OLLOMI_CHAT2_MODEL=gemma4:31b
OLLOMI_CHAT2_API_KEY=...

OLLOMI_STT1_PROVIDER=whisper
OLLOMI_STT1_MODEL=small
OLLOMI_STT2_PROVIDER=openai
OLLOMI_STT2_MODEL=whisper-1
OLLOMI_STT2_API_KEY=...

OLLOMI_EMBEDDING1_PROVIDER=ollama
OLLOMI_EMBEDDING1_MODEL=embeddinggemma
OLLOMI_EMBEDDING1_DIMENSIONS=768
OLLOMI_EMBEDDING2_PROVIDER=openai
OLLOMI_EMBEDDING2_MODEL=text-embedding-3-small
OLLOMI_EMBEDDING2_API_KEY=...
OLLOMI_EMBEDDING2_DIMENSIONS=768
```

Cada entrada acepta `PROVIDER`, `MODEL`, `URL`, `API_KEY`, `NAME`, `EXTERNAL`, `OPTIONS` (objeto JSON) y `DIMENSIONS`. `openai`, `openrouter`, `ollama-cloud`, `ollama` y `whisper` conocen su URL predeterminada; `custom` requiere `URL`. OpenAI, OpenRouter y Ollama Cloud se marcan como externos automáticamente. Una cadena con varios modelos de embeddings exige el mismo `DIMENSIONS` explícito para evitar mezclar vectores incompatibles. Los perfiles se guardan cifrados, son de solo lectura en la app y nunca devuelven la clave al teléfono. Sin variables numeradas para un propósito, se conserva el modo anterior: los administradores pueden crear perfiles en Android y cada usuario puede elegir uno.

El seed de perfiles no impide arrancar por un fallo DNS transitorio: conserva la URL y registra un aviso. Antes de cada llamada real, el backend vuelve a resolver el nombre y aplica toda la política de red; un host todavía no resoluble o una dirección no permitida falla en ese momento y puede activar el siguiente fallback.

`OPTIONS` se envía como parámetros adicionales. Por ejemplo, para un transcriptor que no admita `verbose_json`, use `OLLOMI_STT2_OPTIONS={"response_format":"json"}`. Las respuestas sin segmentos se guardan como un único segmento con la duración total del audio.

Ejemplos de endpoints compatibles:

| Propósito | URL base | Modelo |
|---|---|---|
| Whisper del Compose | `http://stt:8000/v1` | `small` o directorio instalado |
| Ollama del Compose | `http://ollama:11434/v1` | nombre instalado con `ollama pull` |
| Servidor compatible en LAN | `http://servidor-lan:8000/v1` | nombre que exponga ese servidor |
| OpenAI | `https://api.openai.com/v1` | modelo compatible con el propósito |
| OpenRouter | `https://openrouter.ai/api/v1` | identificador del catálogo |
| Ollama Cloud | `https://ollama.com/v1` | nombre cloud, por ejemplo `gemma4:31b` |

STT usa `POST /audio/transcriptions`, chat `/chat/completions` y embeddings `/embeddings`. Ollama local y Ollama Cloud sirven chat; Ollama local también sirve embeddings. Ollama no implementa actualmente el endpoint de transcripción de audio, por lo que STT debe apuntar a Whisper u otro proveedor compatible. No se supone que una única URL ofrezca las tres operaciones.

`compose.yaml` aísla API, workers, bases y modelos en una red `internal`. El override `deploy/compose.connected.yaml` permite llegar a servidores de la LAN o de Internet desde API/worker. Para un proveedor público hay que activar además `OLLOMI_LOCAL_ONLY=false` y marcar el perfil como externo; se exige HTTPS. No se siguen redirecciones ni se heredan proxies de entorno en las llamadas de IA. El administrador del host debe limitar la salida por firewall si quiere permitir solo determinados destinos LAN.

Caddy reenvía al alias privado `ollomi-api`, exclusivo de la red de este proyecto. No usa el nombre genérico `api`, que puede resolver a contenedores de otros stacks si un proxy se conecta a varias redes Docker compartidas. Mantenga el proxy en la red privada de Ollomi; no hace falta `container_name` ni depender del nombre generado del contenedor.

Al cambiar el perfil de embeddings se crea una generación de índice nueva y se programa la reindexación. La búsqueda puede estar incompleta mientras esta termina. PostgreSQL conserva los datos originales; Typesense y los embeddings son índices derivados.

## Voz, hablantes y GPU

Piper es opcional. Copie un modelo `.onnx` y su `.onnx.json` a `selfhost-data/models/piper/`. El nombre predeterminado es `es_ES-davefx-medium`; respete la licencia del modelo. El servicio expone las voces en `/v1/voices` y sintetiza respuestas con `/v2/tts/synthesize`. La preferencia de voz se guarda con `PATCH /v1/users/me` y `{"voice":"nombre-del-modelo"}`.

La diarización Community-1 requiere pesos descargados por el operador tras aceptar sus condiciones. Coloque una copia local completa en `selfhost-data/models/community-1/` y reconstruya con `DIARIZATION=true`. Sin esos pesos el servicio sigue transcribiendo y deja el hablante sin identificar. Los identificadores de hablante son locales a cada fragmento; no se afirma reconocimiento biométrico persistente entre conversaciones.

Para CUDA, con NVIDIA Container Toolkit instalado:

```bash
docker compose -f compose.yaml -f deploy/compose.cuda.yaml up -d --build
```

La ruta CUDA está preparada, pero la validación realizada fue en CPU.

## Integraciones y firmware locales

La pestaña de integraciones permite al administrador configurar WebDAV, CalDAV, webhooks y MCP en direcciones privadas. WebDAV exporta JSON; CalDAV publica tareas VTODO en una colección ya creada. Son exportaciones explícitas, no una sincronización bidireccional de agenda. Los webhooks pueden repetirse si se reintenta tras un error de red: el receptor debe tratar los duplicados. MCP admite Streamable HTTP, descubrimiento de herramientas y ejecución explícita con argumentos JSON; no ejecuta herramientas automáticamente desde el chat.

El firmware se provisiona en `/data/firmware/` del volumen de audio. `manifest.json` relaciona modelo de dispositivo con `latest` y `stable`; cada entrada contiene `filename`, `sha256`, `version`, `changelog` y los campos OTA de Omi. Solo se sirven binarios instalados localmente; el manifiesto se valida contra SHA-256. No se ha flasheado ningún dispositivo durante la verificación. Los mapas abren una aplicación instalada mediante coordenadas; no se incluye un servidor de teselas ni consultas obligatorias a Google Maps.

## Datos, retención y notificaciones

Los datos se almacenan en volúmenes Docker: PostgreSQL, Redis, Typesense, audio y modelos Ollama. Los modelos de voz están en `selfhost-data/models`. Por defecto los audios se conservan hasta borrarlos. `OLLOMI_AUDIO_RETENTION_DAYS=N` elimina periódicamente el audio de conversaciones terminadas mayores de N días; cero desactiva la caducidad. La transcripción permanece. Si el usuario desactiva guardar grabaciones, el audio se elimina después de procesarlo correctamente.

Las notificaciones son locales y se alimentan de un cursor de eventos autenticado. Llegan al consultar el servidor mientras la app está activa. No hay Firebase ni garantía de entrega push con la app terminada o restringida por Android.

## Copias de seguridad y recuperación

```bash
scripts/selfhost_backup.sh /ruta/privada/backup-ollomi
```

El script detiene temporalmente los escritores, guarda un `pg_dump` consistente, los originales y `.env`, y vuelve a arrancar los servicios. Añada por separado los modelos y el firmware aprovisionado; los modelos pueden reinstalarse, pero conserve sus revisiones y licencias. El archivo de claves debe guardarse con el mismo cuidado que la base de datos.

Restaure primero en una instalación **nueva**, con volúmenes vacíos, y mantenga la instalación anterior hasta verificarla:

```bash
cp /ruta/backup/instance.env .env
chmod 600 .env
docker compose up -d postgres redis typesense
docker compose exec -T postgres pg_restore -U ollomi -d ollomi < /ruta/backup/database.dump
docker compose run --rm --no-deps -T --user 0 --entrypoint tar api -C /data -xzf - < /ruta/backup/audio.tar.gz
docker compose run --rm --no-deps --user 0 --entrypoint chown api -R 10001:10001 /data
docker compose up -d
```

Reinstale los modelos antes de procesar. Use Actualizar en Ajustes → servidor para programar la reindexación (`POST /v1/users/me/reindex`). No borre los volúmenes como procedimiento de actualización. Las actualizaciones compiladas desde código usan `git pull --ff-only && docker compose build && docker compose up -d`. Si instaló desde GHCR, use:

Una instalación creada antes de que el inicializador gestionara la cadena de Compose necesita esta migración única en `.env`:

```dotenv
COMPOSE_FILE=compose.yaml:deploy/compose.ghcr.yaml
COMPOSE_PROFILES=local-whisper,local-ollama
```

Si usa IA externa o de la LAN, añada `:deploy/compose.connected.yaml` al primer valor. Deje solo `local-whisper` para STT local sin Ollama. Omita `COMPOSE_PROFILES` cuando STT, chat y embeddings sean externos. Después las actualizaciones quedan reducidas a:

```bash
git pull --ff-only
docker compose pull
docker compose up -d
```

El servicio `migrate` aplica las migraciones antes de arrancar API y workers. No ejecute `docker compose down -v`: `-v` elimina los volúmenes con los datos.

## Diagnóstico

```bash
docker compose ps
docker compose logs --tail=200 api worker stt proxy
curl "http://127.0.0.1:$(sed -n 's/^OLLOMI_PORT=//p' .env)/health"
```

Si Android muestra `ERR_CONNECTION_REFUSED`, compruebe que `proxy` está activo, que `.env` contiene `OLLOMI_BIND=0.0.0.0`, que el firewall permite el puerto y que teléfono y servidor comparten red. Una respuesta `{"detail":"Not Found"}` en `/` confirma que el API responde, pero la ruta de comprobación correcta es `/health`; Ollomi no incluye una interfaz web de usuario.

Para restablecer una contraseña de forma interactiva use `docker compose exec api python -m selfhost.cli reset-password --email usuario@local`. Para automatizarlo, añada `--password-env NOMBRE` o `--password-stdin`. El cambio revoca las sesiones anteriores de ese usuario.

## TLS

El proxy incluido sirve HTTP para localhost/LAN. Para exposición fuera de una red de confianza, sitúe Caddy detrás de su terminador TLS o cambie el Caddyfile con su dominio y certificados. No exponga PostgreSQL, Redis, Typesense ni Ollama. La instalación predeterminada solo publica el puerto del proxy.
