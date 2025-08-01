📊 Qbit-Telegram Monitor: Tu Gestor de qBittorrent en Telegram 🚀
¡Bienvenido a Qbit-Telegram Monitor! Este es un bot de Telegram potente y fácil de usar, escrito en Python, que te permite monitorizar y gestionar tu servidor qBittorrent desde la comodidad de tu chat de Telegram. Olvídate de tener que acceder a la Web UI; con este bot, tendrás el control total y recibirás notificaciones en tiempo real directamente en tu móvil.

✨ Características Principales
El bot está diseñado para ser completo, robusto e intuitivo. Estas son algunas de las cosas que puede hacer:

📊 Monitorización en Tiempo Real y Detallada: Recibe mensajes individuales por cada descarga activa. Cada mensaje se actualiza automáticamente mostrando:

Barra de progreso visual.

Porcentaje, tamaño descargado y total.

Velocidades de subida y bajada.

ETA (tiempo estimado restante).

Semillas, pares, ratio y tracker.

Fecha en que se añadió el torrent.

🕹️ Panel de Control General: Usa el comando /control para invocar un panel que te da una visión global de tu servidor:

Estado de la conexión y versión de qBittorrent.

Recuento total de torrents por estado (descargando, pausado, completado, etc.).

Velocidades globales de subida y bajada.

Espacio libre en el disco.

Botones para Pausar, Reanudar y Forzar el inicio de TODOS los torrents a la vez.

🧲 Añadir Descargas Fácilmente:

Arrastra y suelta un archivo .torrent en el chat para iniciar una nueva descarga.

Pega un enlace magnet: directamente en el chat.

El bot te preguntará en qué categoría deseas guardar la descarga antes de añadirla.

📂 Gestión de Categorías:

Asigna o cambia la categoría de cualquier torrent (activo o completado) con un menú interactivo.

Añade nuevas descargas directamente a la categoría que elijas.

⏯️ Controles Interactivos por Torrent: Cada mensaje de torrent incluye botones para:

Pausar / Reanudar la descarga.

Forzar inicio si un torrent está en cola.

Cambiar la categoría.

Eliminar el torrent y sus datos.

💥 Eliminación Segura con Confirmación: Para evitar accidentes, al pulsar "Eliminar", el bot te pedirá confirmación antes de borrar permanentemente los archivos del disco.

📡 Resumen de Trackers Privados: Con el comando /trackers, obtén un informe detallado del rendimiento de tus trackers privados, mostrando:

Estado general del tracker (🟢, 🟡, 🔴).

Número de torrents activos y en seeding.

Total de datos subidos y bajados.

Ratio calculado para ese tracker específico.

✨ Notificaciones Inteligentes y Autolimpieza:

Cuando un torrent finaliza, el mensaje se actualiza a un estado de "Completado" ✅.

El mensaje de un torrent completado se elimina automáticamente después de una hora para mantener el chat limpio. También puedes borrarlo manualmente.

Si un torrent se elimina desde la Web UI, el bot lo detecta y borra el mensaje correspondiente en Telegram.

🔌 Conexión Robusta y Tolerante a Fallos:

El bot intenta reconectarse a qBittorrent si la conexión se pierde.

Recibirás una notificación en Telegram si el servidor qBittorrent se cae y otra cuando se restablezca la conexión.

📸 Demostración Visual
Así es como se ve el bot en acción:

Mensaje de un torrent en progreso:

Plaintext

📥 Mi.Torrent.Favorito.1080p.mkv
🟦🟦🟦🟦🟦🟦⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️

📥 Progreso: 42.15%
💾 Tamaño: 1.25 GB / 2.97 GB

⬇️ Vel. Bajada: 5.23 MB/s
⬆️ Vel. Subida: 450.2 KB/s

🌱 Semillas: 12 | 👥 Pares: 45
⏳ Tiempo restante: 8m 15s
⚖️ Ratio: 0.15
⚙️ Estado API: downloading
🛰️ Tracker: tracker.dominio.org
🗓️ Añadido: 01/08/2025 10:30
📂 Categoría: Peliculas

+------------------+-------------------+
|    Pausar ⏸️     |   Categoría 📂    |
+------------------+-------------------+
|      Eliminar 💥                     |
+------------------------------------+
Panel de Control General (/control):

Plaintext

PANEL DE CONTROL QBITTORRENT (v4.6.2)
⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯
Torrents: 📥 5 | స్త 1 | ✅ 52 | ⏸️ 3 | ❌ 0

⬇️ Vel. Bajada: 12.8 MB/s
⬆️ Vel. Subida: 4.5 MB/s

🌐 Online | 💽 Libre: 1.2 TB
📈 Subido: 10.3 GB (sesión) | 2.1 TB (total)
🐢 Límites Alt: Desactivados

Última actualización: 11:25:24
+-----------------+--------------------+
|  Pausar Todos ⏸️ | Reanudar Todos ▶️   |
+-----------------+--------------------+
|     Forzar Todos ▶️🔥                 |
+------------------------------------+
|   Refrescar 🔄   |      Cerrar ❌     |
+-----------------+--------------------+
⚙️ Cómo Funciona (Visión Técnica)
El script utiliza una combinación de librerías y lógica para lograr esta integración:

Núcleo: Se basa en python-telegram-bot para la interacción con la API de Telegram y qbittorrent-api para comunicarse con la Web UI de qBittorrent.

Bucle Principal (update_torrents): Una tarea asíncrona se ejecuta cada pocos segundos. En cada ciclo:

Se conecta a qBittorrent para obtener la lista de torrents activos.

Compara esta lista con los torrents que ya está monitorizando.

Envía un nuevo mensaje si detecta un torrent nuevo.

Edita el mensaje existente si detecta cambios en un torrent (progreso, velocidad, etc.). Esto evita el spam y mantiene la información siempre actualizada en un único lugar.

Elimina mensajes de torrents que ya no existen en el servidor.

Refresca el panel de control si está activo.

Gestión de Estado (torrent_messages.json): El bot guarda un archivo JSON para recordar qué mensaje de Telegram corresponde a qué torrent (usando el hash del torrent). Esto le permite sobrevivir a reinicios y seguir actualizando los mensajes correctos. También guarda estados temporales, como cuando estás en el menú de categorías, para evitar que la actualización automática interfiera.

Manejadores de Eventos: El script está atento a diferentes tipos de actualizaciones de Telegram:

Comandos (/start, /control, /trackers) que activan funciones específicas.

Archivos: Si recibe un documento que termina en .torrent, inicia el proceso para añadirlo.

Texto: Si recibe un mensaje de texto que empieza con magnet:, hace lo mismo.

Callbacks de Botones: Cada botón de los mensajes tiene un callback_data único (ej: toggle:HASH_DEL_TORRENT) que es procesado por button_callback para ejecutar la acción correspondiente (pausar, eliminar, etc.).

🚀 Instalación y Puesta en Marcha
Poner a funcionar tu bot es muy sencillo.

Prerrequisitos:

Python 3.8 o superior.

qBittorrent con la Web UI activada.

Instalar las librerías de Python:

Bash

pip install python-telegram-bot qbittorrent-api
Configurar el Bot:
Abre el archivo qbitmonitor.py y rellena las siguientes variables en la sección --- CONFIGURACIÓN ---:

QBIT_HOST: La dirección IP de tu servidor qBittorrent.

QBIT_PORT: El puerto de la Web UI de qBittorrent.

QBIT_USER: Tu usuario de la Web UI (si no tienes, déjalo como None).

QBIT_PASS: Tu contraseña de la Web UI (si no tienes, déjalo como None).

TELEGRAM_TOKEN: El token de tu bot, que obtienes hablando con @BotFather en Telegram.

TELEGRAM_CHAT_ID: Tu ID de chat personal de Telegram. Puedes obtenerlo hablando con bots como @userinfobot.

(Opcional) Configurar Trackers Privados:

Edita la lista PRIVATE_TRACKER_DOMAINS para incluir los dominios de los trackers de los que quieres un resumen con el comando /trackers.

Ejecutar el Bot:

Bash

python qbitmonitor.py
