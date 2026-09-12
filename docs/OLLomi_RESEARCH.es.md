# Omi → Ollomi: investigación y decisiones de implementación

Fecha de revisión: 12 de septiembre de 2026. Destinatario: operador de una grabadora personal con IA que quiere controlar el servidor, los modelos y la conservación de sus datos. Este documento acompaña al código; distingue los hechos observados en las fuentes, las decisiones de Ollomi y las capacidades que todavía requieren validación adicional.

## Conclusión

Es viable conservar la app y el protocolo de grabación de Omi y sustituir el plano de servicios por una instalación propia. Sin embargo, incluir el backend original en Docker no elimina sus dependencias de servicios alojados. La separación importante es entre el protocolo que necesita el teléfono y las implementaciones concretas de autenticación, almacenamiento, inferencia e indexación. Ollomi implementa ese protocolo central sobre servicios locales y mantiene el código original fuera de la imagen desplegada.

El resultado de esta revisión es una primera implementación funcional y comprobable: acceso local multiusuario, perfiles de IA administrados, importación de audio, transcripción local, resumen, recuerdos/tareas, recuperación de información y chat. No debe confundirse con una certificación de equivalencia de todas las funciones comerciales de Omi. La app upstream contiene una superficie considerablemente mayor —pagos, marketplace, llamadas y proveedores específicos, entre otras— y parte de ella necesita retirarse o sustituirse por funciones que tengan sentido en una instalación privada.

## Qué proyectos se utilizaron

El origen es [BasedHardware/omi](https://github.com/BasedHardware/omi), fijado en el commit [`e02339f4c720eb726fb4b798991b306c817630c5`](https://github.com/BasedHardware/omi/tree/e02339f4c720eb726fb4b798991b306c817630c5). El repositorio combina app Flutter, componentes nativos de Android, firmware y backend Python. La licencia del código raíz es MIT; se conserva su aviso. La revisión local se hizo sobre este commit, no sobre una supuesta versión permanentemente actual de la rama principal.

La referencia interpretada a partir de «Olyami» fue [SpencerSmithSite/ollami](https://github.com/SpencerSmithSite/ollami), revisada en [`76637a5be92371737dc0bf8d13a3a8f2adaa6b1c`](https://github.com/SpencerSmithSite/ollami/tree/76637a5be92371737dc0bf8d13a3a8f2adaa6b1c). Sirvió como referencia de dirección: adaptar Omi al uso con infraestructura y modelos controlados por el usuario. No se da por hecho que un fork de ese tipo haya eliminado todas las dependencias remotas. Ollomi se deriva directamente de Omi y lleva su propia implementación de servicios locales; no consiste en renombrar Ollami.

El nombre «Olyama» se interpreta como **Ollama**, el servidor de modelos. Conviene separar estos nombres: Omi es el producto upstream, Ollami es el fork de referencia, Ollama sirve modelos y Ollomi es este workspace.

## Qué significa “sin dependencias externas”

Para esta implementación significa que el recorrido normal puede completarse sin Firebase, cuentas de terceros, almacenamiento comercial, una API de transcripción de pago o un proveedor público de chat. No significa que desaparezcan las bibliotecas de software libre. Tampoco significa que los pesos de los modelos aparezcan en el equipo sin una instalación inicial: hay que descargarlos o copiarlos desde otro medio.

Se han separado dos fases. Durante aprovisionamiento se construyen imágenes y se obtienen los modelos elegidos. Durante ejecución, API, workers, PostgreSQL, Redis, Typesense, Whisper y Ollama están en una red Docker interna. El proxy publica la entrada HTTP. El acceso saliente se habilita expresamente mediante un override cuando el operador quiere utilizar otra máquina de su LAN o una API pública.

Esta separación es verificable. Una URL local por defecto no demuestra aislamiento: un programa puede contactar con servicios de telemetría o descargar pesos automáticamente. Por eso la implementación desactiva descargas en la carga de Whisper, retira los SDK Firebase/Intercom/PostHog del cliente Android y evita una comprobación de conectividad contra servicios públicos. La prueba funcional se efectuó con pesos ya instalados y contenedores en la red privada.

La opción de una URL compatible con OpenAI no contradice el objetivo. La compatibilidad describe un protocolo. Puede referirse a un servidor en la misma máquina, a otra máquina privada o, si el administrador lo autoriza, a un servicio público. Se registran por separado URL, propósito, modelo, credencial y permiso para proveedor externo.

## Arquitectura resultante

| Responsabilidad | Implementación de Ollomi | Motivo |
|---|---|---|
| Identidad | Usuarios y sesiones en PostgreSQL, Argon2, JWT de acceso y refresh rotatorio | No requiere un proveedor de identidad remoto |
| Datos de aplicación | PostgreSQL, registros delimitados por propietario | Unifica conversaciones, tareas, recuerdos, carpetas y preferencias |
| Audios | Volumen local con archivos por usuario e identificador | Permite retención, recuperación y copias de seguridad ordinarias |
| Trabajo duradero | Tabla de trabajos PostgreSQL; Celery/Redis para ejecución | El reinicio de Redis no debe borrar la admisión del audio |
| Búsqueda semántica | pgvector con generación de embeddings | Evita mezclar vectores de modelos incompatibles |
| Búsqueda de texto | Typesense local | Permite consultas de texto sin convertirlo en fuente primaria de datos |
| Transcripción | Servicio faster-whisper o endpoint STT compatible | Se puede elegir modelo y ubicación del procesamiento |
| Resumen y chat | Ollama o endpoint Chat Completions compatible | El administrador controla modelo y credencial |
| Voz de respuesta | Piper opcional | Síntesis local sin un proveedor comercial de voces |
| Android | App Flutter original modificada y código nativo conservado | Mantiene la inversión en captura y dispositivos Omi |

Estas son decisiones de diseño de Ollomi, no una afirmación de que sean componentes intercambiables en cualquier versión de Omi. Se implementaron contratos concretos y se validó el recorrido principal. Los índices son derivados; la recuperación se apoya en la base de datos y los originales.

## Audio: Whisper no es toda la función

[faster-whisper](https://github.com/SYSTRAN/faster-whisper) implementa Whisper sobre CTranslate2 y permite elegir dispositivo y tipo de cómputo. Ollomi usa CPU/int8 por defecto y carga únicamente un directorio instalado. El modelo configurado puede ser un nombre de directorio o una ruta bajo el volumen de modelos. La variante CUDA tiene su propia imagen y configuración de reserva de GPU.

Transcribir es producir texto. Diarizar es asignar turnos a hablantes dentro de una grabación. Identificar a una persona conocida entre grabaciones es una tercera tarea. No es correcto presentar la salida de Whisper como si resolviera automáticamente las tres.

La opción de diarización es [pyannote Community-1](https://huggingface.co/pyannote/speaker-diarization-community-1). Su distribución requiere aceptar condiciones para obtener los pesos; admite una copia local para ejecución posterior. Ollomi integra la diarización opcional, pero no obtuvo esos pesos en nombre del usuario. Por tanto, la prueba realizada no valida diarización ni reconocimiento biométrico. Las etiquetas de fragmentos distintos permanecen separadas para evitar atribuir erróneamente dos voces a una persona.

Los MP3 se reciben como originales y se convierten a fragmentos de audio PCM para el procesamiento. La conversión tiene límites de tamaño y duración y restringe los protocolos/formatos de FFmpeg. Las entradas WAL de Omi tienen un formato distinto: contienen fotogramas precedidos por su longitud. No se deben enviar esos bytes directamente a un transcriptor de archivos. Ollomi valida la estructura, decodifica PCM/Opus y normaliza antes de transcribir; una trama incompleta se rechaza sin confirmar que el teléfono pueda borrar su original.

Las reconexiones introducen otro riesgo: si cada fragmento se trata como una conversación nueva, se pierde continuidad; si todos reemplazan el mismo campo, se pierde texto. La implementación incorpora identificadores por archivo, offsets de tiempo y sustitución idempotente de una parte. Los trabajos de audio/resumen de una conversación se serializan. La prueba de regresión comprueba que un reintento no duplique ni borre partes anteriores.

## Interoperabilidad de modelos

La [documentación de compatibilidad de Ollama](https://docs.ollama.com/api/openai-compatibility) describe la superficie compatible con OpenAI. No se infiere de ella que Ollama sea el transcriptor de audio de Omi. En Ollomi, STT, chat y embeddings tienen perfiles distintos y comprobaciones distintas. Que un servidor responda a `/models` tampoco demuestra que pueda transcribir, producir embeddings o resumir JSON: se prueba la operación correspondiente.

La implementación solicita JSON para extraer título, resumen, tareas y recuerdos. Esa salida se valida antes de escribir los resultados. El modelo puede producir una respuesta inválida, agotar contexto o no responder; en ese caso el trabajo pasa a estado de error recuperable y el audio sigue disponible. Las transcripciones largas se reducen por partes antes del resumen final, con un límite explícito de rondas.

Durante la validación apareció una diferencia concreta entre versiones: Ollama 0.11.10 rechazó `reasoning_effort: none`. La revisión de su [adaptador OpenAI en esa versión](https://github.com/ollama/ollama/blob/v0.11.10/openai/openai.go) permitió acotar el problema. La prueba con Qwen3 utilizó un sufijo `/no_think` y límite de tokens por perfil. Esa es una configuración específica del modelo y versión, no una transformación universal de la API.

La calidad del resumen sigue dependiendo del modelo. Haber comprobado un MP3 breve con Qwen3 0,6 B demuestra que las piezas se comunican y que el resultado llega al usuario; no demuestra precisión clínica, jurídica o de reuniones complejas. Para elegir un modelo de uso diario conviene probar grabaciones representativas, idiomas, ruido y compromisos implícitos. Ese conjunto de evaluación debe ser privado y tener permiso de las personas grabadas.

## Identidad y límites entre usuarios

Cambiar el backend desde el teléfono afecta a más que una URL. La sesión anterior no puede viajar al servidor nuevo; una respuesta de refresh tardía no debe reemplazar la nueva sesión. Las cachés, audios pendientes y metadatos de sincronización necesitan el mismo límite entre propietarios.

Ollomi valida la identidad de instancia al entrar y almacena los tokens en almacenamiento seguro de Android. La URL, instancia y usuario forman la identidad de la caché local. La rotación del refresh usa una protección frente a respuestas tardías. Los registros y búsquedas se filtran por usuario en el backend. Las pruebas incluyen acceso cruzado a conversaciones/archivos y revocación de una URL de reproducción después de revocar la sesión.

La reproducción utiliza tickets temporales porque el reproductor original consume una URL sin añadir el encabezado de autenticación de la API. El ticket se vincula a usuario, archivo y sesión; conocer un identificador de archivo ajeno no basta para reproducirlo. Las claves de IA se cifran en el servidor y sus respuestas de administración solo indican si existe una clave.

Los administradores siguen siendo administradores de una instalación propia: controlan servidores y credenciales. Las exportaciones a conectores configurados pueden trasladar datos a esos servicios. Por eso el cliente presenta el destino y exige una acción explícita de exportación. No se ha conectado ningún servicio personal del usuario durante la implementación.

## Integraciones y autonomía

La sustitución de un marketplace comercial no exige reproducir su infraestructura de pagos o descubrimiento público. Ollomi ofrece conectores configurados por el operador. WebDAV guarda un archivo JSON por usuario; CalDAV exporta tareas VTODO; un webhook recibe la exportación elegida. Esto aporta intercambio local, pero no se presenta como reconciliación bidireccional de calendarios.

MCP se implementó como cliente de [Streamable HTTP del protocolo 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports): inicialización, sesión cuando el servidor la proporciona, descubrimiento de herramientas, llamada explícita y terminación de sesión. La interfaz muestra los argumentos JSON. No se conecta un ejecutor libre al texto de una transcripción ni se permite que un resumen dispare por sí solo acciones en otros sistemas.

El firmware se sirve desde un manifiesto local con hashes, conservando el protocolo OTA del cliente. Debe ser aprovisionado por el operador para el modelo y hardware adecuados. La implementación no sustituye la necesidad de comprobar compatibilidad antes de flashear. No se realizó ningún flasheo en esta revisión.

Los mapas utilizan coordenadas y una aplicación instalada. No se ha implementado un servidor de teselas propio en esta entrega. Del mismo modo, las notificaciones son locales y dependen de que Android permita a la app consultar el servidor; no existe una promesa de push remoto con el proceso terminado.

## Operación y recuperación

El archivo original se confirma al teléfono después de escribirlo y admitir el trabajo en PostgreSQL. Redis no es el registro de admisión. Un worker adquiere un arrendamiento con un token; cancelación o recuperación invalidan ese token para impedir que una ejecución antigua confirme resultados después.

El audio puede conservarse indefinidamente, borrarse manualmente o caducar según la política configurada. Borrar una conversación invalida sus trabajos, elimina registros asociados y programa el borrado de archivos e índices. Los registros de conversación y búsqueda comprueban pertenencia incluso cuando un índice derivado todavía no ha recibido una eliminación.

La copia de seguridad necesita base de datos, originales y claves de instancia. Sin la clave que cifra credenciales, una restauración de la base no reconstruye por sí sola la capacidad de contactar con los modelos configurados. Typesense y embeddings se pueden regenerar, aunque eso requiere que los modelos estén disponibles. Los pesos y el firmware deben conservarse o poder reinstalarse con una revisión conocida.

La instalación se entrega con un procedimiento de copia consistente y restauración en volúmenes nuevos. La primera restauración debe verificarse antes de retirar la instancia anterior. No se utiliza `docker compose down -v` como mecanismo de actualización.

## Evidencia y límites de la conclusión

La evidencia ejecutada incluye compilación Android, pruebas de contratos de autenticación y datos, y un recorrido real de MP3 → Whisper → resumen Ollama → PostgreSQL/pgvector/Typesense → reproducción → chat. El detalle final y los resultados de las pruebas adicionales se registran en [OLLomi_VALIDATION.md](OLLomi_VALIDATION.md).

Quedan fuera de lo demostrado por una prueba de software en este host: autonomía de batería de un dispositivo Omi, calidad Bluetooth bajo interferencias, diarización con pesos gated, identificación persistente de personas, rendimiento CUDA y notificaciones con Android terminando el proceso. Las decisiones de implementación permiten avanzar en esas áreas, pero no convierten esas pruebas ausentes en resultados positivos.

El criterio de aceptación útil para la siguiente revisión es concreto: instalar en una máquina limpia, entrar desde un Android físico, grabar y recuperar una sesión con pérdida de conexión, importar un MP3 propio, comprobar usuarios aislados, restaurar una copia y repetir la consulta sin acceso público. Esta entrega deja el código, los procedimientos y la primera evidencia reproducible para hacerlo.
