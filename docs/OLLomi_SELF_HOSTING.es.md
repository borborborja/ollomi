# Ollomi: instalación y operación

Ollomi es un fork local de Omi. El servicio activo es `selfhost.main:app`; el backend comercial original no entra en la imagen Docker. La aplicación Android puede grabar con el micrófono del teléfono, capturar una llamada cuando Android lo permita, descubrir y conectar un dispositivo Omi/Friend compatible o importar MP3, M4A, WAV, OGG y FLAC. Incluye autenticación local y servidor configurable. Véanse [investigación](OLLomi_RESEARCH.es.md) y [validación y límites](OLLomi_VALIDATION.md).

## Estado de este checkout

Este checkout no contiene una instalación objetivo, una APK ni credenciales de
administrador. Las rutas, contraseñas, artefactos y modelos de una instalación
anterior no son instrucciones válidas para un despliegue nuevo. Consulte
[`OLLomi_VALIDATION.md`](OLLomi_VALIDATION.md) para conocer la evidencia actual
y las puertas obligatorias antes de producción.

## Requisitos

Docker Engine con Compose v2, Linux, almacenamiento persistente y un navegador o Android. Para desarrollar Android: Flutter 3.44.5, Java 21, SDK Android 36 y NDK 29.0.14206865. Las imágenes y los pesos se descargan durante la instalación; el funcionamiento posterior puede permanecer sin salida a Internet.

Reserve al menos 25 GB libres para compilar las imágenes y la app, más los modelos y audios. Para uso en CPU, 16 GB de RAM es un punto de partida razonable; los recursos necesarios dependen del modelo y de las grabaciones simultáneas. No compile Android mientras ejecuta inferencia en una máquina ajustada de memoria. El modelo de 0,6 B utilizado en la prueba verifica el recorrido técnico, pero su calidad no equivale a la de modelos mayores.

## Primera instalación directa: modelos en LAN o proveedores externos

Esta es la vía corta para un servidor CPU que no aloja modelos. Copie la
plantilla de la raíz, edite todos los marcadores `CHANGE_ME` y las IP de
ejemplo, y mantenga el archivo solo legible para su propietario:

```bash
git clone https://github.com/YOUR_GITHUB_OWNER/ollomi.git
cd ollomi
cp .env.example .env
chmod 600 .env
${EDITOR:-vi} .env
docker compose config --quiet
docker compose build
docker compose up -d
```

La plantilla activa el override de conectividad, pero no inicia `stt`,
`model-downloader` ni `ollama`: todo STT, procesamiento y embeddings se
define mediante perfiles numerados de `.env`. Debe dejar un perfil válido para
cada propósito. Las entradas LAN usan `EXTERNAL=false` y pueden usar HTTP; un
proveedor público debe tener `EXTERNAL=true` y HTTPS.

El primer arranque crea `OLLOMI_ADMIN_EMAIL` con
`OLLOMI_ADMIN_PASSWORD`. Después del primer inicio de sesión correcto, quite
la contraseña de `.env` y recree los servicios que la reciben:

```bash
docker compose up -d --force-recreate migrate api worker scheduler
```

La plantilla mantiene MCP desactivado. Para MCP con OAuth, primero configure
el dominio HTTPS y el perfil TLS de la sección siguiente; no active OAuth en
una URL HTTP de LAN ni acepte redirecciones HTTP en el cliente.

## Primera instalación compilando desde código

Hasta que el fork publique una release revisada, la vía segura construye esta
revisión concreta del backend:

```bash
git clone https://github.com/YOUR_GITHUB_OWNER/ollomi.git
cd ollomi
read -rsp 'Contraseña inicial: ' INITIAL_ADMIN_PASSWORD; echo
export INITIAL_ADMIN_PASSWORD
python3 scripts/selfhost_init.py --source-build --bind 0.0.0.0 \
  --admin-email admin@example.com \
  --admin-password-env INITIAL_ADMIN_PASSWORD
unset INITIAL_ADMIN_PASSWORD
docker compose build
```

El inicializador crea `.env` con permisos 600, escribe la cadena `COMPOSE_FILE` para construir desde fuente y elige el primer puerto libre entre 8080, 8090 y los siguientes. `--bind 0.0.0.0` permite acceder desde el teléfono. Para usar únicamente proveedores de la LAN o Internet, use `--external-ai`; esta opción incluye `deploy/compose.connected.yaml`, fija `OLLOMI_LOCAL_ONLY=false` y no activa los perfiles `local-whisper` ni `local-ollama`.

Para acceder desde Internet o activar el MCP con OAuth, use un dominio público que ya resuelva hacia el servidor y abra los puertos 80 y 443 antes del primer inicio. Añada `--tls-domain` al inicializador; el perfil `public-tls` inicia un Caddy incluido en el Compose, obtiene y renueva el certificado, conserva sus claves en un volumen y reenvía también el WebSocket de captura. Mantenga el proxy HTTP de mantenimiento ligado a `127.0.0.1`; no añada `--bind 0.0.0.0` en esta modalidad.

```bash
python3 scripts/selfhost_init.py --source-build \
  --tls-domain ollomi.example.com \
  --admin-email admin@example.com \
  --admin-password-env INITIAL_ADMIN_PASSWORD
```

El inicializador fija `OLLOMI_PUBLIC_URL` y `OLLOMI_MCP_PUBLIC_URL` a ese dominio HTTPS, pero conserva `OLLOMI_MCP_ENABLED=false`: actívelo solo cuando haya comprobado que el certificado y el acceso de Android funcionan.

```bash
docker compose run --rm model-downloader --stt small
docker compose -f compose.yaml -f deploy/compose.connected.yaml \
  --profile local-ollama up -d ollama
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama pull embeddinggemma
docker compose up -d
```

El arranque final vuelve a aplicar la cadena guardada en `.env` y retira de Ollama la red temporal de descarga. Si inicializó con `--external-ai`, omita la descarga de Whisper y los tres comandos de Ollama. Configure en `.env` al menos un perfil externo para STT, chat y embeddings antes de arrancar; no se crea, descarga ni ejecuta ningún contenedor de IA local.

Compose lee `COMPOSE_FILE` y `COMPOSE_PROFILES` desde `.env`; no hace falta repetir los overrides habituales en cada comando. Compruebe los valores elegidos con:

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

El directorio [`deploy/examples/external-api`](../deploy/examples/external-api/README.md) contiene un `compose.yaml` copiable que descarga una imagen revisada del mismo fork de Ollomi. Su `env.example` pide el owner y la etiqueta de release, además de los ajustes de instancia y los perfiles numerados, con ejemplos de OpenAI, OpenRouter, un endpoint compatible y Ollama en otra máquina. Esta variante no contiene servicios `stt`, `model-downloader` u `ollama`, por lo que no necesita pesos de Whisper ni el directorio `selfhost-data/models`. Antes de publicar la primera imagen del fork, use la instalación compilada desde código.

```bash
mkdir ollomi && cd ollomi
curl -LO https://raw.githubusercontent.com/YOUR_GITHUB_OWNER/ollomi/main/deploy/examples/external-api/compose.yaml
curl -Lo .env https://raw.githubusercontent.com/YOUR_GITHUB_OWNER/ollomi/main/deploy/examples/external-api/env.example
chmod 600 .env
# Edite .env y sustituya todos los valores CHANGE_ME.
docker compose config --quiet
docker compose pull
docker compose up -d
```

La imagen queda fijada por `OLLOMI_IMAGE_OWNER` y `OLLOMI_IMAGE_TAG`; use una etiqueta de release del mismo fork que haya pasado las puertas de validación. No use `latest` como sustituto de una release revisada. El Compose conserva localmente PostgreSQL/pgvector, Redis, Typesense y los audios: solo salen del servidor las peticiones de inferencia configuradas.

El mismo Compose externo incorpora el perfil opcional `public-tls`: con un DNS público, puertos 80/443 abiertos y las variables `OLLOMI_TLS_DOMAIN`, `OLLOMI_TLS_BIND`, `OLLOMI_HTTP_PORT`, `OLLOMI_HTTPS_PORT`, `OLLOMI_PUBLIC_URL=https://…` y `COMPOSE_PROFILES=public-tls`, Caddy obtiene el certificado y sirve tanto API como WebSocket. Esta es también la ruta autocontenida para activar MCP OAuth; mantenga `OLLOMI_BIND=127.0.0.1` y use el dominio HTTPS como `OLLOMI_MCP_PUBLIC_URL`.

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
git clone https://github.com/YOUR_GITHUB_OWNER/ollomi.git
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

`deploy/Dockerfile` compila el backend autoalojado. `services/speech/Dockerfile` compila el servidor Whisper; no hace falta construir esta segunda imagen si todo el STT se delega a una API externa. El workflow `.github/workflows/ollomi-release.yml` publica ambas imágenes para `linux/amd64` solo desde `push` a `main` o etiquetas `v*`, con etiquetas de rama, release y SHA; `latest` se actualiza desde `main`. Pull requests y ejecuciones manuales construyen pero no autentican ni publican imágenes.

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

La configuración inicial fija por entorno Whisper `small`, chat `qwen3:4b` y `embeddinggemma`. En hardware pequeño puede instalar `tiny` y `qwen3:0.6b` y cambiar `OLLOMI_STT1_MODEL` y `OLLOMI_CHAT1_MODEL` en `.env`. Con Ollama 0.11.10 y Qwen3, añada `OLLOMI_CHAT1_OPTIONS={"prompt_suffix":"/no_think","max_tokens":2048}` si quiere evitar pensamiento extendido. La compatibilidad de opciones depende de la versión del servidor; compruebe el estado desde Android. El primer perfil configurado para cada tarea es el primario y los demás son fallback. `OLLOMI_ALLOW_USER_MODEL_SELECTION=false` (valor inicial) impide cambiarlo también por API; active el valor solo si los usuarios deben elegir entre los perfiles ya definidos por el administrador.

## Acceso desde Android

El inicializador intenta 8080 y después 8090 si el primero está ocupado; el valor definitivo está en `OLLOMI_PORT`. Cambie `OLLOMI_BIND` por la dirección LAN del servidor para acceder desde un teléfono. Vuelva a crear el proxy con `docker compose up -d proxy`. En el emulador Android, `10.0.2.2` apunta al host.

Instale la APK y escriba en la pantalla de entrada la URL del backend, correo y contraseña locales. Desde Ajustes → servidor puede probar una nueva conexión, ver el modelo activo y la salud de cada fallback STT/chat/embeddings, administrar usuarios, importar audio y exportar datos. Cuando los modelos están definidos en `.env`, la app no permite crear ni editar ese catálogo. Por defecto muestra el primario y los fallbacks sin permitir cambiarlos; solo con `OLLOMI_ALLOW_USER_MODEL_SELECTION=true` cada usuario puede escoger como primario una de las opciones habilitadas, conservando las restantes como fallback. La captura en tiempo real siempre abre el WebSocket del servidor seleccionado: configuraciones STT antiguas guardadas en el teléfono, claves directas de proveedores y el modo on-device no pueden eludir el catálogo ni los fallbacks del backend. Para cambiar de servidor, cierre sesión y entre con la nueva URL. La sesión, las importaciones pendientes y los metadatos WAL se vinculan al servidor y a la cuenta.

Cuando el workflow `Publish Ollomi` del fork haya pasado las puertas de validación, su ejecución deja `ollomi-android-debug-<commit>` en **Artifacts** para pruebas físicas; es una APK de depuración, no distribuible. Una etiqueta `v*` que haya pasado las mismas puertas crea `ollomi-android-<commit>` con `ollomi.apk` y `SHA256SUMS`, y los adjunta a la Release. La firma se conserva entre APK publicadas, por lo que las actualizaciones posteriores se instalan sobre la anterior. El paso desde una APK de desarrollo firmada con otra clave puede requerir una única desinstalación.

Una pulsación larga sobre `+` permite elegir la fuente: micrófono del teléfono, llamada, dispositivo compatible conectado o importar audio. La captura de llamadas depende de las restricciones del fabricante y la versión de Android. La opción del dispositivo permite buscar y asociar un Omi/Friend compatible por Bluetooth; después usa esa conexión.

La APK de desarrollo se construye así:

```bash
cd app
flutter pub get
flutter build apk --debug --flavor dev --target-platform android-arm64,android-x64
```

Para distribuir una versión definitiva, configure una clave de firma propia en Gradle y compile el sabor `prod` en modo release. La APK de desarrollo entregada no es una publicación en Google Play.

El selector acepta MP3, WAV, M4A, OGG y FLAC. También acepta «Compartir» audio desde otras apps Android. La copia pendiente del teléfono se elimina solo cuando el servidor confirma la admisión duradera. Puede cancelar/reintentar trabajos; un fallo de IA conserva el original. Un reintento explícito utiliza los perfiles seleccionados en ese momento, para poder corregir URL, credenciales o modelo. La subida está limitada a 1 GiB y 12 horas por grabación de forma predeterminada. La captura normal y la muestra para reconocer la voz del propietario se envían únicamente al WebSocket autenticado de Ollomi: la app no usa claves directas, servicios Omi ni STT en el teléfono como ruta de reserva.

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

Cada entrada acepta `PROVIDER`, `MODEL`, `URL`, `API_KEY`, `NAME`, `EXTERNAL`, `OPTIONS` (objeto JSON) y `DIMENSIONS`. `openai`, `openrouter`, `ollama-cloud`, `ollama`, `whisper`, `gemini`, `assemblyai`, `deepgram`, `voyage` y `cohere` conocen su URL predeterminada; `custom` requiere `URL`. OpenAI, OpenRouter, Ollama Cloud y los proveedores SaaS se marcan como externos automáticamente. Una cadena con varios modelos de embeddings exige el mismo `DIMENSIONS` explícito para evitar mezclar vectores incompatibles. Los perfiles se guardan cifrados y nunca devuelven la clave al teléfono. El administrador controla el catálogo de producción mediante `.env`; si habilita `OLLOMI_ALLOW_USER_MODEL_SELECTION=true`, cada usuario puede elegir uno de esos modelos permitidos y los demás quedan ordenados como fallback. Sin variables numeradas para un propósito, los administradores pueden crear perfiles en Android, pero esa modalidad no sustituye un catálogo auditable por `.env`.

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

STT OpenAI/Whisper usa `POST /audio/transcriptions`, chat `/chat/completions` y embeddings OpenAI/Ollama `/embeddings`. Gemini usa su Files API y `gemini-3.5-transcribe` para transcripción por lotes; Deepgram, AssemblyAI, Voyage y Cohere usan sus APIs nativas. Gemini, Deepgram y AssemblyAI pueden entregar etiquetas de diarización cuando el modelo y la cuenta del proveedor las admiten, pero esas etiquetas no reconocen biométricamente al propietario entre grabaciones. Ollama local y Ollama Cloud sirven chat; Ollama local también sirve embeddings. Ollama no implementa actualmente el endpoint de transcripción de audio, por lo que STT debe apuntar a Whisper u otro proveedor compatible.

`compose.yaml` aísla API, workers, bases y modelos en una red `internal`. El override `deploy/compose.connected.yaml` permite llegar a servidores de la LAN o de Internet desde API/worker. Para un proveedor público hay que activar además `OLLOMI_LOCAL_ONLY=false` y marcar el perfil como externo; se exige HTTPS. No se siguen redirecciones ni se heredan proxies de entorno en las llamadas de IA. El administrador del host debe limitar la salida por firewall si quiere permitir solo determinados destinos LAN.

Caddy reenvía al alias privado `ollomi-api`, exclusivo de la red de este proyecto. No usa el nombre genérico `api`, que puede resolver a contenedores de otros stacks si un proxy se conecta a varias redes Docker compartidas. Mantenga el proxy en la red privada de Ollomi; no hace falta `container_name` ni depender del nombre generado del contenedor.

Al cambiar el perfil de embeddings se crea una generación de índice nueva y se programa la reindexación. La búsqueda puede estar incompleta mientras esta termina. PostgreSQL conserva los datos originales; Typesense y los embeddings son índices derivados.

## Voz y hablantes

Piper es opcional. Copie un modelo `.onnx` y su `.onnx.json` a `selfhost-data/models/piper/`. El nombre predeterminado es `es_ES-davefx-medium`; respete la licencia del modelo. El servicio expone las voces en `/v1/voices` y sintetiza respuestas con `/v2/tts/synthesize`. La preferencia de voz se guarda con `PATCH /v1/users/me` y `{"voice":"nombre-del-modelo"}`.

Para distinguir interlocutores y reconocer la voz del propietario desde la primera versión, Ollomi combina diarización del proveedor STT con un servicio de *voiceprint* separado y opcional. Está pensado para el segundo servidor x86-64 sin GPU: siga [`deploy/examples/voiceprint/README.md`](../deploy/examples/voiceprint/README.md), que ofrece Compose desde código y otro que descarga la imagen versionada del mismo fork, proteja su puerto por red privada o TLS y configure en el backend:

```dotenv
OLLOMI_VOICEPRINT_URL=https://voiceprint.example.internal
OLLOMI_VOICEPRINT_API_KEY=la_misma_clave_del_servicio
OLLOMI_VOICEPRINT_THRESHOLD=0.72
```

La app pide una muestra de voz solo cuando el servicio está disponible. El backend prefiere siempre las etiquetas nativas de Gemini, Deepgram o AssemblyAI. Si el STT es solo texto —por ejemplo, un endpoint OpenAI/Whisper estándar—, manda el clip WAV normalizado al endpoint privado `/v1/diarize` del servicio ECAPA: ventanas de voz con energía se agrupan en turnos `spk_N` y el texto se reparte por sus intervalos. Es una alternativa CPU para distinguir interlocutores, no una atribución forense ni una sustitución de diarización nativa de alta calidad.

Después, el backend envía una muestra WAV breve de cada turno al endpoint de embeddings para comparar la voz enrolada. Guarda únicamente el vector de enrolamiento cifrado en la base de datos y borra la muestra recibida; no conserva el audio de enrolamiento ni da una URL de reproducción. La imagen lleva una revisión ECAPA fijada, verifica en el build las sumas SHA-256 de los tres checkpoints cargados y funciona con Hugging Face en modo offline: no descarga pesos ni necesita credenciales de Hugging Face al arrancar. Las etiquetas del fallback son locales a cada clip y «tú» solo se marca tras la comparación con el perfil enrolado. La caída del servicio nunca descarta una transcripción: deja las etiquetas de interlocutor sin marcar como «tú». Una modificación sustancial del modelo o del umbral exige volver a enrolar la voz y calibrar el umbral con grabaciones consentidas.

Para CUDA, con NVIDIA Container Toolkit instalado:

```bash
docker compose -f compose.yaml -f deploy/compose.cuda.yaml up -d --build
```

La ruta CUDA está preparada, pero la validación realizada fue en CPU.

## MCP, OAuth e integraciones locales

El backend puede exponer un servidor MCP Streamable HTTP de solo lectura. No necesita un proveedor OAuth externo ni secretos de cliente: activa el servidor con una URL pública HTTPS estable y el propio backend publica el descubrimiento OAuth 2.1, registro dinámico de clientes, Authorization Code con PKCE S256, refresh y revocación.

```dotenv
OLLOMI_MCP_ENABLED=true
OLLOMI_MCP_PUBLIC_URL=https://ollomi.example.com
OLLOMI_MCP_ACCESS_MINUTES=15
OLLOMI_MCP_REFRESH_DAYS=30
```

El endpoint MCP es `https://ollomi.example.com/mcp`. Un cliente moderno descubre `/.well-known/oauth-protected-resource/mcp` y `/.well-known/oauth-authorization-server`, registra su redirect URI y abre el inicio de sesión local de Ollomi. Para clientes que todavía no soportan OAuth, el usuario puede crear una clave personal desde Ajustes de desarrollador de Android y usarla como `Authorization: Bearer …`; la clave completa aparece una sola vez y puede revocarse. Las herramientas incluidas solo listan o leen las conversaciones, recuerdos y tareas de la cuenta autenticada; nunca entregan audio ni permiten escribir o borrar datos. Cambiar la contraseña, desactivar la cuenta o revocar una credencial corta el acceso MCP de inmediato.

El valor de `OLLOMI_MCP_PUBLIC_URL` se anuncia como `mcp_url`. Puede ser distinto de la URL LAN que usa Android: es esta URL HTTPS pública la que se debe pegar en el cliente MCP.

La pestaña de integraciones permite al administrador configurar WebDAV, CalDAV, webhooks y llamadas salientes a MCP en direcciones privadas. WebDAV exporta JSON; CalDAV publica tareas VTODO en una colección ya creada. Son exportaciones explícitas, no una sincronización bidireccional de agenda. Los webhooks pueden repetirse si se reintenta tras un error de red: el receptor debe tratar los duplicados. MCP saliente admite Streamable HTTP, descubrimiento de herramientas y ejecución explícita con argumentos JSON; no ejecuta herramientas automáticamente desde el chat.

El firmware se provisiona en `/data/firmware/` del volumen de audio. `manifest.json` relaciona modelo de dispositivo con `latest` y `stable`; cada entrada contiene `filename`, `sha256`, `version`, `changelog` y los campos OTA de Omi. Solo se sirven binarios instalados localmente; el manifiesto se valida contra SHA-256. No se ha flasheado ningún dispositivo durante la verificación. Los mapas abren una aplicación instalada mediante coordenadas; no se incluye un servidor de teselas ni consultas obligatorias a Google Maps.

## Datos, retención y notificaciones

Los datos se almacenan en volúmenes Docker: PostgreSQL, Redis, Typesense, audio y modelos Ollama. Los modelos de voz están en `selfhost-data/models`. Por defecto los audios se conservan hasta borrarlos. `OLLOMI_AUDIO_RETENTION_DAYS=N` elimina periódicamente el audio de conversaciones terminadas mayores de N días; cero desactiva la caducidad. La transcripción permanece. Si el usuario desactiva guardar grabaciones, el audio se elimina después de procesarlo correctamente.

Las notificaciones son locales y se alimentan de un cursor de eventos autenticado. Llegan al consultar el servidor mientras la app está activa. No hay Firebase ni garantía de entrega push con la app terminada o restringida por Android.

## Copias de seguridad y recuperación

```bash
scripts/selfhost_backup.sh /ruta/privada/backup-ollomi
```

El script detiene temporalmente los escritores, guarda un `pg_dump` consistente, los originales y `.env`, y vuelve a arrancar los servicios. Añada por separado los modelos y el firmware aprovisionado; los modelos pueden reinstalarse, pero conserve sus revisiones y licencias. El archivo de claves debe guardarse con el mismo cuidado que la base de datos.

Para recuperar, mantenga la instalación anterior hasta verificar la nueva y
ejecute el restaurador desde el checkout que contiene los scripts:

```bash
scripts/selfhost_restore.sh /ruta/privada/backup-ollomi --confirm-restore
```

El restaurador exige que el `OLLOMI_SECRET_KEY` de la instalación sea
exactamente el de `instance.env` de la copia: es lo que permite recuperar las
credenciales de proveedores cifradas. En una instalación nueva, copie primero
esa línea de forma segura a su `.env` (o copie `instance.env` completo y adapte
puerto y proveedores). Antes de detener escritores verifica `SHA256SUMS` y las
rutas del archivo de audio; después reemplaza PostgreSQL y los audios, borra
solamente los índices derivados de Typesense/pgvector y deja una reindexación
en cola para cada usuario activo. Reinstale o compruebe los modelos antes de
dejar procesar trabajos. El script se niega a actuar sin
`--confirm-restore`.

No borre los volúmenes como procedimiento de actualización. Las actualizaciones compiladas desde código usan `git pull --ff-only && docker compose build && docker compose up -d`. Si instaló desde GHCR, use:

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
