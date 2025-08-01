import time
import logging
import json
import math
from pathlib import Path
import html
from datetime import datetime
import os

# Importar librerías necesarias
import qbittorrentapi
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest
import urllib.parse
from qbittorrentapi.exceptions import APIConnectionError, NotFound404Error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot

# --- CONFIGURACIÓN ---
# Rellena con tus datos
QBIT_HOST = "192.168.0.160"  # o la IP de tu servidor qBittorrent
QBIT_PORT = 6363
QBIT_USER = None      # tu usuario de la Web UI
QBIT_PASS = None # tu contraseña de la Web UI

TELEGRAM_TOKEN = "xxxxxxx" # Token de tu bot obtenido de @BotFather
TELEGRAM_CHAT_ID = "6xxxxxxxx"         # Tu ID de chat personal

PRIVATE_TRACKER_DOMAINS = [
    "xxxxxxx.li",
    "xxxxxxxx.org",
    "xxxxxxxx.club",
    "xxxxxxx.li",
    "xxxxxxxx.cx",
    "xxxxxxx.com",
    "tracker.xxxxxxxx.org"
]

# --- VARIABLES GLOBALES Y UTILIDADES ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

STATE_FILE = Path("torrent_messages.json")
torrent_messages = {}
control_panel_state = {}
connection_state = {'connected': True, 'error_message_id': None}
pending_torrents = {}

UPDATES_PER_CYCLE = 8
update_cursor = 0
COMPLETED_TORRENT_CLEANUP_DELAY = 3600


def load_state():
    global torrent_messages
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            torrent_messages = json.load(f)
    logger.info(f"Estado cargado: {len(torrent_messages)} torrents monitorizados.")

def save_state():
    with open(STATE_FILE, 'w') as f:
        json.dump(torrent_messages, f, indent=4)

# NUEVA FUNCIÓN para evitar errores de formato en Telegram
def escape_markdown(text: str) -> str:
    """Escapa caracteres especiales de Markdown V1."""
    escape_chars = '_*`['
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

def format_bytes(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.log(abs(size_bytes), 1024))
    p = 1024 ** i
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def format_eta(eta_seconds):
    if eta_seconds > 8640000:
        return "∞"
    m, s = divmod(eta_seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d > 0: return f"{d}d {h}h"
    if h > 0: return f"{h}h {m}m"
    return f"{m}m {s}s"

def create_progress_bar(progress):
    progress_float = float(progress)
    filled_blocks = int(round(progress_float * 15))
    empty_blocks = 15 - filled_blocks
    return "🟦" * filled_blocks + "⬜️" * empty_blocks

def get_message_details(torrent):
    """Genera el texto y los botones para un mensaje de torrent. (Versión HTML)"""
    # Define el emoji principal según el estado del torrent
    status_emoji_map = {
        "downloading": "📥", "pausedDL": "⏸️", "stoppedDL": "⏸️", "stalledDL": "స్త", "forcedDL": "🔥",
        "uploading": "✅", "pausedUP": "✅", "completed": "✅",
        "checkingDL": "🔄", "checkingUP": "🔄", "error": "❌"
    }
    status_emoji = status_emoji_map.get(torrent.state, "❓")

    if 'checking' in torrent.state:
        progress_bar = create_progress_bar(torrent.progress)
        percentage = f"{torrent.progress * 100:.2f}%"
        text = (
            f"<b>{html.escape(torrent.name)}</b>\n"
            f"<code>{progress_bar}</code>\n\n"
            f"{status_emoji} <b>Verificando archivos:</b> {percentage}\n"
            f"💾 <b>Tamaño total:</b> {format_bytes(torrent.total_size)}"
        )
        if torrent.category:
            text += f"\n📂 <b>Categoría:</b> {html.escape(torrent.category)}"
        
        # Para este estado, solo ofrecemos el botón de eliminar.
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Eliminar 💥", callback_data=f"delete_prompt:{torrent.hash}")]
        ])
        return text, buttons

    # ----- MENSAJE PARA DESCARGAS NO COMPLETADAS -----
    elif torrent.progress < 1:
        progress_bar = create_progress_bar(torrent.progress)
        percentage = f"{torrent.progress * 100:.2f}%"
        
        # --- LÍNEA CORREGIDA ---
        downloaded_size = format_bytes(torrent.downloaded) # Usamos .downloaded en lugar de .size
        
        total_size = format_bytes(torrent.total_size)
        eta = format_eta(torrent.eta)

        text = (
            f"<b>{html.escape(torrent.name)}</b>\n"
            f"<code>{progress_bar}</code>\n\n"
            f"{status_emoji} <b>Progreso:</b> {percentage}\n"
            f"💾 <b>Tamaño:</b> {downloaded_size} / {total_size}\n\n"
            f"⬇️ <b>Vel. Bajada:</b> {format_bytes(torrent.dlspeed)}/s\n"
            f"⬆️ <b>Vel. Subida:</b> {format_bytes(torrent.upspeed)}/s\n\n"
            f"🌱 <b>Semillas:</b> {torrent.num_seeds} | 👥 <b>Pares:</b> {torrent.num_leechs}\n"
            f"⏳ <b>Tiempo restante:</b> {eta}\n"
            f"⚖️ <b>Ratio:</b> {torrent.ratio:.2f}"
        )

        text += f"\n⚙️ <b>Estado API:</b> <code>{torrent.state}</code>"
        
        # Añadimos la información del tracker si está disponible
        if torrent.tracker:
            # Parseamos la URL para obtener solo el dominio (netloc)
            tracker_domain = urllib.parse.urlparse(torrent.tracker).netloc
            # Mostramos el dominio si lo encontramos, si no, la URL completa como respaldo
            display_tracker = tracker_domain if tracker_domain else torrent.tracker
            text += f"\n🛰️ <b>Tracker:</b> {html.escape(display_tracker)}"

        # --- BLOQUE AÑADIDO ---
        # Añadimos la fecha en que se agregó el torrent, si está disponible
        if torrent.added_on:
            added_date = datetime.fromtimestamp(torrent.added_on).strftime("%d/%m/%Y %H:%M")
            text += f"\n🗓️ <b>Añadido:</b> {added_date}"

        if torrent.category:
            text += f"\n📂 <b>Categoría:</b> {html.escape(torrent.category)}"

        if torrent.state == 'queuedDL':
            buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Forzar ▶️🔥", callback_data=f"force_start:{torrent.hash}"),
                    InlineKeyboardButton("Categoría 📂", callback_data=f"show_cat:{torrent.hash}")
                ],
                [InlineKeyboardButton("Eliminar 💥", callback_data=f"delete_prompt:{torrent.hash}")]
            ])
        # Para todos los demás estados (descargando, pausado, etc.), muestra Pausar/Reanudar
        else:
            pause_resume_button = InlineKeyboardButton(
                "Pausar ⏸️" if "downloading" in torrent.state or "forced" in torrent.state or "stalled" in torrent.state else "Reanudar ▶️",
                callback_data=f"toggle:{torrent.hash}"
            )
            buttons = InlineKeyboardMarkup([
                [
                    pause_resume_button,
                    InlineKeyboardButton("Categoría 📂", callback_data=f"show_cat:{torrent.hash}")
                ],
                [InlineKeyboardButton("Eliminar 💥", callback_data=f"delete_prompt:{torrent.hash}")]
            ])
        
        return text, buttons

    # Bloque para torrents completados (sin cambios)
    else:
        text = (
            f"✅ <b>{html.escape(torrent.name)}</b>\n\n"
            f"Descarga completada con éxito.\n\n"
            f"💾 <b>Tamaño total:</b> {format_bytes(torrent.total_size)}\n"
            f"⚖️ <b>Ratio final:</b> {torrent.ratio:.2f}"
        )
        if torrent.category:
            text += f"\n📂 <b>Categoría:</b> {html.escape(torrent.category)}"
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Borrar 🗑️", callback_data=f"cleanup_msg:{torrent.hash}"),
                InlineKeyboardButton("Eliminar 💥", callback_data=f"delete_prompt:{torrent.hash}")
            ],
            [InlineKeyboardButton("Categoría 📂", callback_data=f"show_cat:{torrent.hash}")]
        ])
            
        return text, buttons


async def generate_control_panel(qbt_client: qbittorrentapi.Client):
    """Genera el texto y los botones para el panel de control general (versión refinada)."""
    main_data = qbt_client.sync_maindata()
    torrents = qbt_client.torrents_info()

    states = {'downloading': 0, 'seeding': 0, 'paused': 0, 'error': 0, 'stalled': 0}
    for t in torrents:
        if 'paused' in t.state or 'stopped' in t.state:
            states['paused'] += 1
        elif t.state == 'stalledDL':
            states['stalled'] += 1
        elif 'downloading' in t.state:
            states['downloading'] += 1
        elif t.state in ['uploading', 'stalledUP', 'forcedUP']:
            states['seeding'] += 1
        elif t.state == 'error':
            states['error'] += 1

    server_state = main_data.server_state
    free_space = format_bytes(server_state.free_space_on_disk)
    session_upload = format_bytes(server_state.up_info_data)
    total_upload = format_bytes(server_state.alltime_ul)
    connection_status = server_state.connection_status.capitalize()
    alt_speed_status = "Activados" if server_state.use_alt_speed_limits else "Desactivados"

    # --- Diseño Refinado ---
    text = (
        f"<b>PANEL DE CONTROL QBITTORRENT</b> (v{qbt_client.app.version})\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"<b>Torrents:</b> 📥 {states['downloading']} | స్త {states['stalled']} | ✅ {states['seeding']} | ⏸️ {states['paused']} | ❌ {states['error']}\n\n"
        
        f"⬇️ <b>Vel. Bajada:</b> {format_bytes(server_state.dl_info_speed)}/s\n"
        f"⬆️ <b>Vel. Subida:</b> {format_bytes(server_state.up_info_speed)}/s\n\n"
        
        f"🌐 {connection_status} | 💽 Libre: {free_space}\n"
        f"📈 Subido: {session_upload} (sesión) | {total_upload} (total)\n"
        f"🐢 Límites Alt: {alt_speed_status}\n\n"
        
        f"<code>Última actualización: {datetime.now().strftime('%H:%M:%S')}</code>"
    )
    
    # --- Botones con la nueva opción "Forzar Todos" ---
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Pausar Todos ⏸️", callback_data="ctrl:pause_all"),
            InlineKeyboardButton("Reanudar Todos ▶️", callback_data="ctrl:resume_all")
        ],
        [
            InlineKeyboardButton("Forzar Todos ▶️🔥", callback_data="ctrl:force_all")
        ],
        [
            InlineKeyboardButton("Refrescar 🔄", callback_data="ctrl:refresh"),
            InlineKeyboardButton("Cerrar ❌", callback_data="ctrl:close")
        ]
    ])

    return text, buttons

async def update_torrents(context: ContextTypes.DEFAULT_TYPE):
    """
    Tarea principal que se ejecuta periódicamente.
    Gestiona la actualización de mensajes de torrents y el estado de la conexión.
    """
    global update_cursor # <-- AÑADIR ESTA LÍNEA

    qbt_client = context.job.data['qbt_client']
    bot = context.bot

    try:
        # --- Lógica de gestión de conexión (sin cambios) ---
        qbt_client.app.version
        if not connection_state['connected']:
            logger.info("Conexión con qBittorrent restaurada.")
            if connection_state['error_message_id']:
                try:
                    await bot.delete_message(chat_id=TELEGRAM_CHAT_ID, message_id=connection_state['error_message_id'])
                except Exception as e:
                    logger.warning(f"No se pudo borrar el mensaje de error de conexión: {e}")
            connection_state['connected'] = True
            connection_state['error_message_id'] = None
            connection_state.pop('first_failure_time', None)

        # --- Lógica para obtener todos los torrents (sin cambios) ---
        downloading_torrents = qbt_client.torrents_info(filter='downloading')
        managed_hashes = list(torrent_messages.keys())

        if managed_hashes:
            managed_torrents = qbt_client.torrents_info(torrent_hashes=managed_hashes)
        else:
            managed_torrents = []

        all_torrents_map = {t.hash: t for t in downloading_torrents}
        all_torrents_map.update({t.hash: t for t in managed_torrents})
        all_relevant_torrents = list(all_torrents_map.values())
        current_hashes = {t.hash for t in all_relevant_torrents}

        # --- INICIO: LÓGICA DE DISTRIBUCIÓN DE CARGA ---

        if update_cursor >= len(all_relevant_torrents):
            update_cursor = 0

        torrents_to_check = all_relevant_torrents[update_cursor : update_cursor + UPDATES_PER_CYCLE]

        for torrent in torrents_to_check:
            text, buttons = get_message_details(torrent)

            if torrent.hash not in torrent_messages:
                try:
                    message = await bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode='HTML', reply_markup=buttons
                    )
                    torrent_messages[torrent.hash] = {'message_id': message.message_id, 'text': text, 'status': 'default'}
                    logger.info(f"Nuevo torrent '{torrent.name}'. Mensaje enviado: {message.message_id}")
                except Exception as e:
                    logger.error(f"Error enviando mensaje para nuevo torrent: {e}")
            else:
                message_id = torrent_messages[torrent.hash].get('message_id')
                last_text = torrent_messages[torrent.hash].get('text')
                is_busy = torrent_messages[torrent.hash].get('status', 'default') != 'default'

                if message_id and text != last_text and not is_busy:
                    try:
                        await bot.edit_message_text(
                            chat_id=TELEGRAM_CHAT_ID, message_id=message_id, text=text, parse_mode='HTML', reply_markup=buttons
                        )
                        if torrent.progress == 1 and torrent_messages[torrent.hash].get('status') != 'completed':
                            torrent_messages[torrent.hash]['status'] = 'completed'
                            # Guardamos la hora actual para el borrado automático
                            torrent_messages[torrent.hash]['completion_time'] = time.time()
                            logger.info(f"Torrent '{torrent.name}' completado. Se borrará automáticamente en 1h.")
                    except BadRequest as e:
                        if "message is not modified" not in e.message.lower():
                            logger.error(f"Error al editar mensaje {message_id}: {e}")
                    except Exception as e:
                        logger.error(f"Error inesperado al editar mensaje {message_id}: {e}")

        update_cursor += len(torrents_to_check)
        if update_cursor >= len(all_relevant_torrents):
            update_cursor = 0

        hashes_to_autoclean = []
        for torrent_hash, data in torrent_messages.items():
            # Comprobamos si el torrent está 'completado' y tiene una hora de finalización
            if data.get('status') == 'completed' and 'completion_time' in data:
                # Si han pasado más segundos que los definidos en la constante, lo añadimos a la lista de limpieza
                if time.time() - data['completion_time'] > COMPLETED_TORRENT_CLEANUP_DELAY:
                    hashes_to_autoclean.append(torrent_hash)

        for torrent_hash in hashes_to_autoclean:
            message_id = torrent_messages[torrent_hash].get('message_id')
            logger.info(f"Limpiando automáticamente el mensaje del torrent completado {torrent_hash}.")
            try:
                await bot.delete_message(chat_id=TELEGRAM_CHAT_ID, message_id=message_id)
            except Exception as e:
                # Si el mensaje ya fue borrado manualmente, no hacemos nada
                logger.warning(f"No se pudo autolimpiar el mensaje {message_id} (posiblemente ya borrado): {e}")
            finally:
                # Nos aseguramos de eliminarlo del seguimiento, incluso si falla el borrado del mensaje
                if torrent_hash in torrent_messages:
                    del torrent_messages[torrent_hash]

        hashes_to_remove = [h for h in torrent_messages if h not in current_hashes]
        for torrent_hash in hashes_to_remove:
            if torrent_hash in torrent_messages:
                message_id = torrent_messages[torrent_hash].get('message_id')
                logger.info(f"Torrent {torrent_hash} no encontrado. Eliminando mensaje.")
                try:
                    await bot.delete_message(chat_id=TELEGRAM_CHAT_ID, message_id=message_id)
                except Exception as e:
                    logger.warning(f"No se pudo eliminar el mensaje {message_id}: {e}")
                del torrent_messages[torrent_hash]

        # --- Lógica del panel de control (sin cambios) ---
        if control_panel_state:
            timeout_seconds = 300
            elapsed = time.time() - control_panel_state.get('created_at', 0)

            if elapsed > timeout_seconds:
                logger.info("El panel de control ha expirado. Borrando mensaje.")
                try:
                    await bot.delete_message(
                        chat_id=control_panel_state['chat_id'],
                        message_id=control_panel_state['message_id']
                    )
                except Exception:
                    pass
                finally:
                    control_panel_state.clear()
            else:
                try:
                    text, buttons = await generate_control_panel(qbt_client)
                    await bot.edit_message_text(
                        text=text,
                        chat_id=control_panel_state['chat_id'],
                        message_id=control_panel_state['message_id'],
                        reply_markup=buttons,
                        parse_mode='HTML'
                    )
                except BadRequest as e:
                    if "message is not modified" not in e.message:
                        logger.warning("Panel borrado manualmente, limpiando estado.")
                        control_panel_state.clear()
                except Exception as e:
                    logger.error(f"No se pudo refrescar el panel: {e}")
                    control_panel_state.clear()

        save_state()

    except APIConnectionError:
        if connection_state['connected']:
            logger.error("Se ha perdido la conexión con qBittorrent.")
            connection_state['connected'] = False
            connection_state['first_failure_time'] = time.time()

            try:
                error_message = await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=f"🔴 <b>Conexión perdida con qBittorrent</b>\n\nHora del fallo: {datetime.now().strftime('%H:%M:%S')}",
                    parse_mode='HTML'
                )
                connection_state['error_message_id'] = error_message.message_id
            except Exception as send_e:
                logger.error(f"No se pudo enviar el mensaje de notificación de error: {send_e}")

        elif connection_state['error_message_id']:
            elapsed_seconds = int(time.time() - connection_state.get('first_failure_time', time.time()))

            text = (
                f"🔴 <b>Conexión perdida con qBittorrent</b>\n\n"
                f"Tiempo desconectado: <b>~{elapsed_seconds} segundos</b>\n\n"
                f"El bot sigue intentando reconectar..."
            )
            try:
                await bot.edit_message_text(
                    text=text,
                    chat_id=TELEGRAM_CHAT_ID,
                    message_id=connection_state['error_message_id'],
                    parse_mode='HTML'
                )
            except BadRequest as e:
                if 'message is not modified' not in e.message:
                    logger.warning("No se pudo editar mensaje de error (¿borrado manualmente?).")
                    connection_state['error_message_id'] = None
            except Exception as edit_e:
                logger.error(f"Error desconocido al editar el mensaje de estado: {edit_e}")

async def control_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del panel de control general."""
    query = update.callback_query
    await query.answer() # Responde al callback para que el botón deje de cargar

    action = query.data.split(":")[1]
    
    if action == 'close':
        await query.message.delete()
        control_panel_state.clear()
        return
    
    # Si la acción no es 'refresh' o 'close', necesitamos el cliente qBit
    if action != 'refresh':
        qbt_client = context.job_queue.jobs()[0].data['qbt_client']

        if action == 'pause_all':
            qbt_client.torrents_pause(hashes='all')
        elif action == 'resume_all':
            qbt_client.torrents_resume(hashes='all')
        # --- NUEVA LÓGICA ---
        elif action == 'force_all':
            # La API llama a esta función "force_start"
            qbt_client.torrents_set_force_start(hashes='all', value=True)
    
    # Refresca el panel para mostrar los cambios
    # Se necesita el cliente qBit aquí de todas formas para generar el nuevo panel
    qbt_client = context.job_queue.jobs()[0].data['qbt_client']
    text, buttons = await generate_control_panel(qbt_client)
    try:
        await query.edit_message_text(text=text, reply_markup=buttons, parse_mode='HTML')
    except BadRequest as e:
        if "message is not modified" not in e.message:
            logger.error(f"Error al refrescar panel de control: {e}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Router principal para todos los botones, con gestión de estados para evitar cierres de menú."""
    query = update.callback_query
    if query.data.startswith("add_torrent:"):
        await query.answer()
        parts = query.data.split(":", 2)
        action_type = parts[1] # 'file', 'magnet' o 'cancel'

        pending_info = context.user_data.pop('pending_torrent', None)
        if not pending_info:
            await query.edit_message_text("Esta acción ya fue completada o ha expirado.")
            return

        # Borrar el mensaje de selección de categoría y el mensaje original del usuario.
        await context.bot.delete_message(chat_id=query.message.chat_id, message_id=pending_info['prompt_msg_id'])
        await context.bot.delete_message(chat_id=query.message.chat_id, message_id=pending_info['original_msg_id'])
        
        if action_type == 'cancel':
            # Si era un archivo, hay que borrar el archivo temporal
            if pending_info['type'] == 'file':
                os.remove(pending_info['data'])
            logger.info("La adición del torrent fue cancelada por el usuario.")
            return

        # Si no se canceló, se procede a añadir a qBittorrent
        category = ""
        if len(parts) > 2 and parts[2] != "NO_CATEGORY":
            category = urllib.parse.unquote_plus(parts[2])

        try:
            qbt_client = context.job_queue.jobs()[0].data['qbt_client']
            if pending_info['type'] == 'file':
                with open(pending_info['data'], 'rb') as f:
                    qbt_client.torrents_add(torrent_files=f, category=category)
                os.remove(pending_info['data']) # Borrar el archivo temporal después de añadirlo
                logger.info(f"Archivo torrent añadido a qBittorrent con categoría '{category or 'ninguna'}'")

            elif pending_info['type'] == 'magnet':
                qbt_client.torrents_add(urls=pending_info['data'], category=category)
                logger.info(f"Enlace magnet añadido a qBittorrent con categoría '{category or 'ninguna'}'")
            
            # La tarea periódica 'update_torrents' se encargará de crear el nuevo mensaje de estado automáticamente.
        except Exception as e:
            logger.error(f"Fallo al añadir torrent a qBittorrent: {e}")
            await query.message.reply_text("❌ No se pudo añadir la descarga a qBittorrent.")
        

    elif query.data == "trackers:close":
        await query.answer()
        await query.message.delete()
        return
    # Manejo del panel de control (sin cambios aquí)
    elif query.data.startswith("ctrl:"):
        try:
            await control_panel_callback(update, context)
        except qbittorrentapi.exceptions.APIConnectionError:
            logger.warning("No se pudo conectar con qBittorrent al usar el panel de control.")
            await query.answer("⚠️ qBittorrent no responde. Inténtalo de nuevo más tarde.", show_alert=True)
        except Exception as e:
            logger.error(f"Error inesperado en el callback del panel de control: {e}")
            await query.answer("Ocurrió un error inesperado.", show_alert=True)
        return

    await query.answer()
    
    data_parts = query.data.split(":", 2)
    action = data_parts[0]
    torrent_hash = data_parts[1]
    
    qbt_client = context.job_queue.jobs()[0].data['qbt_client']
    
    try:
        # --- LÓGICA DE GESTIÓN DE ESTADOS ---
        
        if action == "show_cat":
            # MARCAMOS EL MENSAJE COMO "EDITANDO CATEGORÍA" PARA BLOQUEARLO
            if torrent_hash in torrent_messages:
                torrent_messages[torrent_hash]['status'] = 'editing_category'
                save_state()

            categories_dict = qbt_client.torrents_categories()
            category_names = list(categories_dict.keys())
            
            cat_buttons = []
            for i, name in enumerate(category_names):
                cat_buttons.append([InlineKeyboardButton(name, callback_data=f"set_cat:{torrent_hash}:{i}")])
            
            cat_buttons.append([InlineKeyboardButton("Sin Categoría", callback_data=f"set_cat:{torrent_hash}:-1")])
            cat_buttons.append([InlineKeyboardButton("« Volver", callback_data=f"show_main:{torrent_hash}")])
            
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(cat_buttons))

        elif action in ["set_cat", "show_main"]:
             # AL SALIR DE UN SUBMENÚ, DESBLOQUEAMOS EL MENSAJE PONIENDO SU ESTADO EN 'DEFAULT'
            if torrent_hash in torrent_messages:
                torrent_messages[torrent_hash]['status'] = 'default' # CORREGIDO: Usamos 'default' en lugar de 'completed'
                save_state()

            if action == "set_cat":
                category_index_str = data_parts[2] if len(data_parts) > 2 else "-1"
                category_index = int(category_index_str)
                
                category_name = ""
                if category_index >= 0:
                    categories_dict = qbt_client.torrents_categories()
                    category_names = list(categories_dict.keys())
                    if category_index < len(category_names):
                        category_name = category_names[category_index]
                
                qbt_client.torrents_set_category(torrent_hashes=torrent_hash, category=category_name)
            
            # Para ambas acciones (set_cat y show_main), refrescamos el mensaje a su estado principal
            torrent = qbt_client.torrents_info(torrent_hashes=torrent_hash)[0]
            text, buttons = get_message_details(torrent)
            await query.edit_message_text(text=text, reply_markup=buttons, parse_mode='HTML')

        # --- AÑADIDO: GESTIÓN DE ESTADO PARA EL BORRADO ---
        elif action == "delete_prompt":
            # MARCAMOS EL MENSAJE COMO "CONFIRMANDO BORRADO" PARA BLOQUEARLO
            if torrent_hash in torrent_messages:
                torrent_messages[torrent_hash]['status'] = 'confirming_delete'
                save_state()
            
            torrent = qbt_client.torrents_info(torrent_hashes=torrent_hash)[0]
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("SÍ, BORRAR ARCHIVOS 💥", callback_data=f"delete_files:{torrent_hash}")],
                [InlineKeyboardButton("NO, CANCELAR ❌", callback_data=f"show_main:{torrent_hash}")] # Reutilizamos show_main para cancelar
            ])
            await query.edit_message_text(
                text=f"❓ ¿Seguro que quieres eliminar este torrent Y SUS ARCHIVOS del disco?\n\n<b>{html.escape(torrent.name)}</b>",
                reply_markup=buttons,
                parse_mode='HTML'
            )

        elif action == "force_start":
            await query.answer("Forzando inicio...")
            qbt_client.torrents_set_force_start(torrent_hashes=torrent_hash, value=True)
            # Refrescamos el mensaje inmediatamente para que el usuario vea el cambio de estado y botones
            torrent = qbt_client.torrents_info(torrent_hashes=torrent_hash)[0]
            text, buttons = get_message_details(torrent)
            await query.edit_message_text(text=text, reply_markup=buttons, parse_mode='HTML')


        # --- OTRAS ACCIONES (SIN CAMBIOS EN SU LÓGICA INTERNA) ---
        elif action == "toggle":
            torrents = qbt_client.torrents_info(torrent_hashes=torrent_hash)
            if not torrents:
                await query.edit_message_text(text="Este torrent ya no existe.")
                return
            torrent = torrents[0]
            # --- LÍNEA CORREGIDA ---
            if "downloading" in torrent.state or "forced" in torrent.state or "stalled" in torrent.state:
                qbt_client.torrents_pause(torrent_hashes=torrent_hash)
            else:
                qbt_client.torrents_resume(torrent_hashes=torrent_hash)

        elif action == "cleanup_msg":
            await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
            if torrent_hash in torrent_messages:
                del torrent_messages[torrent_hash]
                save_state()

        elif action == "delete_files":
            try:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
            finally:
                qbt_client.torrents_delete(delete_files=True, torrent_hashes=torrent_hash)
                if torrent_hash in torrent_messages:
                    del torrent_messages[torrent_hash]
                    save_state()

    except qbittorrentapi.exceptions.APIConnectionError:
        logger.warning("No se pudo conectar con qBittorrent al pulsar un botón.")
        await query.answer("⚠️ qBittorrent no responde. Por favor, espera a que se restablezca la conexión.", show_alert=True)
        # Al fallar la conexión, también es buena idea desbloquear el mensaje por si acaso
        if torrent_hash in torrent_messages:
            torrent_messages[torrent_hash]['status'] = 'default'
            save_state()

    except qbittorrentapi.exceptions.NotFound404Error:
        await query.edit_message_text(text="Este torrent ya fue eliminado de qBittorrent.")
        if torrent_hash in torrent_messages:
            del torrent_messages[torrent_hash]
            save_state()
            
    except Exception as e:
        logger.error(f"Error en el callback para el torrent {torrent_hash}: {e}", exc_info=True)
        try:
            error_type = type(e).__name__
            await query.edit_message_text(text=f"⚠️ Ocurrió un error inesperado: {error_type}")
        except Exception:
            pass

async def handle_torrent_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Se activa al recibir un archivo .torrent."""
    if not update.message.document.file_name.endswith('.torrent'):
        return

    qbt_client = context.job_queue.jobs()[0].data['qbt_client']
    
    try:
        # Descargar el archivo .torrent temporalmente
        file = await context.bot.get_file(update.message.document.file_id)
        # El Path nos da la ruta completa donde se descarga
        temp_file_path = await file.download_to_drive()
        
        # Obtener categorías de qBittorrent
        categories = qbt_client.torrents_categories()
        buttons = []
        for name in categories.keys():
            # Codificamos el nombre de la categoría para evitar problemas en el callback_data
            encoded_name = urllib.parse.quote_plus(name)
            buttons.append([InlineKeyboardButton(name, callback_data=f"add_torrent:file:{encoded_name}")])
        
        buttons.append([InlineKeyboardButton("Sin Categoría", callback_data="add_torrent:file:NO_CATEGORY")])
        buttons.append([InlineKeyboardButton("Cancelar ❌", callback_data="add_torrent:cancel")])
        
        # Guardar la información del archivo pendiente y el ID del mensaje original para borrarlo después
        context.user_data['pending_torrent'] = {'type': 'file', 'data': str(temp_file_path), 'original_msg_id': update.message.message_id}
        
        # Enviar el menú de categorías y guardar su ID para borrarlo también
        prompt_message = await update.message.reply_text("Selecciona una categoría para añadir la descarga:", reply_markup=InlineKeyboardMarkup(buttons))
        context.user_data['pending_torrent']['prompt_msg_id'] = prompt_message.message_id

    except Exception as e:
        logger.error(f"Error al manejar archivo torrent: {e}")
        await update.message.reply_text("⚠️ Hubo un error procesando el archivo .torrent.")


async def handle_magnet_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Se activa al recibir un enlace magnet."""
    text = update.message.text
    if not text.startswith('magnet:'):
        return

    qbt_client = context.job_queue.jobs()[0].data['qbt_client']

    try:
        # Obtener categorías de qBittorrent
        categories = qbt_client.torrents_categories()
        buttons = []
        for name in categories.keys():
            encoded_name = urllib.parse.quote_plus(name)
            buttons.append([InlineKeyboardButton(name, callback_data=f"add_torrent:magnet:{encoded_name}")])

        buttons.append([InlineKeyboardButton("Sin Categoría", callback_data="add_torrent:magnet:NO_CATEGORY")])
        buttons.append([InlineKeyboardButton("Cancelar ❌", callback_data="add_torrent:cancel")])
        
        # Guardar la información del magnet pendiente y los IDs para el borrado
        context.user_data['pending_torrent'] = {'type': 'magnet', 'data': text, 'original_msg_id': update.message.message_id}

        prompt_message = await update.message.reply_text("Selecciona una categoría para añadir la descarga:", reply_markup=InlineKeyboardMarkup(buttons))
        context.user_data['pending_torrent']['prompt_msg_id'] = prompt_message.message_id

    except Exception as e:
        logger.error(f"Error al manejar enlace magnet: {e}")
        await update.message.reply_text("⚠️ Hubo un error procesando el enlace magnet.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy tu bot de monitorización de qBittorrent. Las actualizaciones comenzarán en breve.")

async def trackers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Envía un resumen del estado de los trackers privados definidos en la lista.
    """
    # --- NUEVO: Borramos el comando del usuario para mantener el chat limpio ---
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"No se pudo borrar el comando /trackers: {e}")

    msg = await context.bot.send_message(
        chat_id=update.message.chat_id,
        text="🔄 Procesando estadísticas de trackers, por favor espera..."
    )
    
    try:
        qbt_client = context.job_queue.jobs()[0].data['qbt_client']
        
        # ... (toda la lógica para construir tracker_stats se mantiene igual) ...
        tracker_stats = {}
        all_torrents = qbt_client.torrents_info()

        for torrent in all_torrents:
            found_private_domains = set()
            statuses_by_domain = {}

            for tracker in torrent.trackers:
                try:
                    domain = urllib.parse.urlparse(tracker['url']).netloc
                    if domain in PRIVATE_TRACKER_DOMAINS:
                        found_private_domains.add(domain)
                        statuses_by_domain[domain] = tracker['status']
                except Exception:
                    continue

            for domain in found_private_domains:
                if domain not in tracker_stats:
                    tracker_stats[domain] = {
                        'count': 0, 'seeding_count': 0,
                        'uploaded': 0, 'downloaded': 0,
                        'status_codes': []
                    }
                
                stats = tracker_stats[domain]
                stats['count'] += 1
                stats['uploaded'] += torrent.uploaded
                stats['downloaded'] += torrent.downloaded
                
                if domain in statuses_by_domain:
                    stats['status_codes'].append(statuses_by_domain[domain])

                if torrent.progress == 1:
                    stats['seeding_count'] += 1
        
        # ... (la lógica de formateo del mensaje también se mantiene igual) ...
        final_message_text = "📊 <b>Resumen de Trackers Privados</b>"
        if not tracker_stats:
            final_message_text += "\n\nNo se encontraron torrents activos para los trackers definidos."
        else:
            items = []
            for domain, stats in sorted(tracker_stats.items()):
                statuses = stats['status_codes']
                status_icon = '🔴'
                if statuses:
                    if all(s == 2 for s in statuses): status_icon = '🟢'
                    elif any(s == 2 for s in statuses): status_icon = '🟡'
                
                ratio = stats['uploaded'] / stats['downloaded'] if stats['downloaded'] > 0 else float('inf')
                ratio_str = f"{ratio:.2f}" if ratio != float('inf') else "∞"
                up_str = format_bytes(stats['uploaded'])
                down_str = format_bytes(stats['downloaded'])
                
                seeding_str = f" (🌱{stats['seeding_count']})" if stats['seeding_count'] > 0 else ""
                count_str = f"{stats['count']} torrents{seeding_str}"

                line = (
                    f"{status_icon} <b>{html.escape(domain)}:</b> <code>{count_str}</code>\n"
                    f"  - 📤 <code>{up_str}</code> | 📥 <code>{down_str}</code>\n"
                    f"  - ⚖️ <b>Ratio:</b> <code>{ratio_str}</code>"
                )
                items.append(line)
            
            final_message_text += "\n\n" + "\n".join(items)

        # --- NUEVO: Creamos el markup con el botón de cerrar ---
        close_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("Cerrar Panel ❌", callback_data="trackers:close")]
        ])

        await msg.edit_text(
            final_message_text,
            parse_mode='HTML',
            reply_markup=close_button  # <-- Añadimos el botón al mensaje
        )

    except Exception as e:
        logger.error(f"Error al generar el resumen de trackers: {e}", exc_info=True)
        await msg.edit_text("❌ Ocurrió un error al obtener los datos de los trackers.")

async def control_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía el panel de control, lo guarda en el estado y borra el comando."""
    qbt_client = context.job_queue.jobs()[0].data['qbt_client']
    
    # Si ya existe un panel, lo borramos antes de crear el nuevo
    if control_panel_state:
        try:
            await context.bot.delete_message(
                chat_id=control_panel_state['chat_id'],
                message_id=control_panel_state['message_id']
            )
        except Exception:
            pass # El mensaje podría no existir ya
    
    # Borramos el comando /control del usuario
    await context.bot.delete_message(
        chat_id=update.message.chat_id,
        message_id=update.message.message_id
    )
    
    # Creamos el nuevo panel
    text, buttons = await generate_control_panel(qbt_client)
    panel_message = await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=text,
        reply_markup=buttons,
        parse_mode='HTML'
    )
    
    # Guardamos el estado del nuevo panel
    control_panel_state['message_id'] = panel_message.message_id
    control_panel_state['chat_id'] = panel_message.chat_id
    control_panel_state['created_at'] = time.time()

def main():
    qbt_client = qbittorrentapi.Client(host=QBIT_HOST, port=QBIT_PORT, username=QBIT_USER, password=QBIT_PASS)
    
    # --- BUCLE DE CONEXIÓN INICIAL ---
    while True:
        try:
            qbt_client.auth_log_in()
            logger.info(f"Conexión con qBittorrent exitosa. Versión: {qbt_client.app.version}")
            break # Si la conexión es exitosa, salimos del bucle

        except qbittorrentapi.exceptions.LoginFailed as e:
            logger.error(f"Fallo al iniciar sesión en qBittorrent: {e}. El script se cerrará.")
            # Un fallo de login es un error de configuración, por lo que aquí sí es correcto salir.
            return 
            
        except Exception as e:
            # Si es cualquier otro error (ej. qBittorrent no disponible), esperamos y reintentamos.
            logger.error(f"No se pudo conectar a qBittorrent. Reintentando en 15 segundos... Error: {e}")
            time.sleep(15) # Pausa para no sobrecargar el sistema

    # --- El resto del script continúa con normalidad una vez conectado ---
    load_state()

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("control", control_panel_command))
    
    application.add_handler(CommandHandler("start", start))

    application.add_handler(CommandHandler("trackers", trackers_command))

    application.add_handler(MessageHandler(filters.Document.ALL, handle_torrent_file))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_magnet_link))

    application.add_handler(CallbackQueryHandler(button_callback))
    
    job_queue = application.job_queue
    job_queue.run_repeating(update_torrents, interval=7, first=1, data={'qbt_client': qbt_client})
    
    logger.info("El bot se ha iniciado y está monitorizando...")
    application.run_polling()

if __name__ == '__main__':
    main()
