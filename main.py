import os
import json
import logging
from flask import Flask, request
import telegram
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from google.cloud import secretmanager
import base64
import openai  # Para generar contenido con GPT

# Configuración de logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar la aplicación Flask
app = Flask(__name__)

# Función para obtener secretos desde Secret Manager
def access_secret(secret_id):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{os.environ.get('PROJECT_ID')}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# Obtener tokens y configuración desde Secret Manager (en producción)
def get_config():
    try:
        telegram_token = access_secret('TELEGRAM_TOKEN')
        wp_url = access_secret('WORDPRESS_URL')
        wp_user = access_secret('WORDPRESS_USER')
        wp_password = access_secret('WORDPRESS_PASSWORD')
        openai_api_key = access_secret('OPENAI_API_KEY')
    except Exception as e:
        # Fallback para desarrollo local
        logger.warning(f"Error accessing Secret Manager: {e}. Using environment variables.")
        telegram_token = os.environ.get('TELEGRAM_TOKEN')
        wp_url = os.environ.get('WORDPRESS_URL')
        wp_user = os.environ.get('WORDPRESS_USER')
        wp_password = os.environ.get('WORDPRESS_PASSWORD')
        openai_api_key = os.environ.get('OPENAI_API_KEY')
    
    return telegram_token, wp_url, wp_user, wp_password, openai_api_key

# Inicializar el bot de Telegram y OpenAI
telegram_token, wp_url, wp_user, wp_password, openai_api_key = get_config()
bot = telegram.Bot(token=telegram_token)
openai.api_key = openai_api_key

# Diccionario para almacenar posts en progreso
user_posts = {}

# Función para generar contenido con AI
def generate_content(tema, tone="informativo"):
    """
    Genera contenido para un post de blog basado en un tema
    :param tema: Tema para el post
    :param tone: Tono del contenido (informativo, casual, profesional, etc.)
    :return: Título y contenido generados
    """
    try:
        # Prompt para generar el título
        title_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"Eres un experto en crear títulos atractivos para blogs. Crea un título atractivo para un post sobre '{tema}'. El título debe ser conciso y atrayente."},
                {"role": "user", "content": f"Crea un título atractivo para un artículo de blog sobre {tema}"}
            ],
            max_tokens=50
        )
        
        title = title_response.choices[0].message.content.strip().replace('"', '')
        
        # Prompt para generar el contenido
        content_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"Eres un blogger profesional que escribe contenido {tone}. Crea un post de blog completo sobre '{tema}' con un tono {tone}. Incluye una introducción, desarrollo y conclusión. Usa formato HTML para estructurar el contenido."},
                {"role": "user", "content": f"Escribe un artículo de blog completo sobre {tema} con título: '{title}'"}
            ],
            max_tokens=1000
        )
        
        content = content_response.choices[0].message.content.strip()
        
        # Asegurarnos de que el contenido esté en formato HTML
        if not content.startswith("<"):
            content = "<p>" + content.replace('\n\n', '</p><p>').replace('\n', '<br>') + "</p>"
        
        return title, content
    
    except Exception as e:
        logger.error(f"Error generando contenido: {e}")
        return f"Post sobre {tema}", f"<p>No se pudo generar contenido automáticamente. Por favor, intenta de nuevo más tarde.</p>"

# Función para publicar en WordPress
def publish_to_wordpress(title, content, status='draft'):
    """
    Publica un post en WordPress a través de la API REST
    :param title: Título del post
    :param content: Contenido del post
    :param status: Estado del post ('draft', 'publish', etc.)
    :return: Response de la API
    """
    api_url = f"{wp_url}/wp-json/wp/v2/posts"
    
    # Credenciales para la API de WordPress
    credentials = f"{wp_user}:{wp_password}"
    token = base64.b64encode(credentials.encode())
    headers = {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json'
    }
    
    # Datos del post
    post_data = {
        'title': title,
        'content': content,
        'status': status
    }
    
    # Enviar petición a la API de WordPress
    response = requests.post(api_url, headers=headers, json=post_data)
    
    if response.status_code == 201:  # 201 = Created
        return True, response.json()
    else:
        return False, response.text

# Comandos del bot
def start(update, context):
    """Envía un mensaje cuando se emite el comando /start."""
    update.message.reply_text('¡Hola! Soy un bot que te ayudará a crear y publicar posts en tu blog de WordPress. '
                             'Usa /help para ver los comandos disponibles.')

def help_command(update, context):
    """Envía un mensaje cuando se emite el comando /help."""
    update.message.reply_text('Estos son los comandos disponibles:\n'
                             '/tema [tu tema] - Genera un post sobre el tema especificado\n'
                             '/revisar - Muestra el post en progreso\n'
                             '/modificar [instrucciones] - Modifica el post actual\n'
                             '/publicar - Publica el post en WordPress\n'
                             '/guardar - Guarda el post como borrador\n'
                             '/cancelar - Cancela el post actual')

def tema_command(update, context):
    """Inicia el proceso de generación de post con un tema"""
    user_id = update.effective_user.id
    text = update.message.text[6:].strip()  # Eliminar '/tema '
    
    if not text:
        update.message.reply_text('Por favor, proporciona un tema para el post. Ejemplo: /tema inteligencia artificial')
        return
    
    update.message.reply_text(f'Generando post sobre: {text}. Esto puede tomar un momento...')
    
    # Generar contenido con IA
    title, content = generate_content(text)
    
    # Guardar el post en progreso
    user_posts[user_id] = {
        'title': title,
        'content': content,
        'tema': text
    }
    
    # Mostrar resultado al usuario
    update.message.reply_text(
        f"He generado este post para ti:\n\n"
        f"📝 <b>Título:</b> {title}\n\n"
        f"<i>Para ver el contenido completo usa /revisar</i>\n\n"
        f"¿Qué quieres hacer ahora?",
        parse_mode=telegram.ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Ver post completo", callback_data="revisar")],
            [InlineKeyboardButton("Modificar", callback_data="modificar"), 
             InlineKeyboardButton("Publicar", callback_data="publicar")],
            [InlineKeyboardButton("Guardar borrador", callback_data="guardar"),
             InlineKeyboardButton("Cancelar", callback_data="cancelar")]
        ])
    )

def revisar_command(update, context):
    """Muestra el post en progreso"""
    user_id = update.effective_user.id
    
    if user_id not in user_posts:
        update.message.reply_text('No hay ningún post en progreso. Usa /tema [tu tema] para empezar.')
        return
    
    post = user_posts[user_id]
    
    # Extraer una vista previa del contenido (primeros 300 caracteres)
    content_preview = post['content'][:300] + '...' if len(post['content']) > 300 else post['content']
    # Eliminar etiquetas HTML para la vista previa
    content_preview = content_preview.replace('<p>', '').replace('</p>', '\n\n').replace('<br>', '\n')
    
    update.message.reply_text(
        f"📝 <b>Título:</b> {post['title']}\n\n"
        f"<b>Vista previa:</b>\n{content_preview}\n\n"
        f"¿Qué quieres hacer ahora?",
        parse_mode=telegram.ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Modificar", callback_data="modificar"), 
             InlineKeyboardButton("Publicar", callback_data="publicar")],
            [InlineKeyboardButton("Guardar borrador", callback_data="guardar"),
             InlineKeyboardButton("Cancelar", callback_data="cancelar")]
        ])
    )

def modificar_command(update, context):
    """Modifica el post actual"""
    user_id = update.effective_user.id
    
    if user_id not in user_posts:
        update.message.reply_text('No hay ningún post en progreso. Usa /tema [tu tema] para empezar.')
        return
    
    text = update.message.text[10:].strip()  # Eliminar '/modificar '
    
    if not text:
        update.message.reply_text('Por favor, proporciona instrucciones para modificar el post. Ejemplo: /modificar Agregar más detalles sobre el tema')
        return
    
    post = user_posts[user_id]
    update.message.reply_text(f'Modificando post según tus instrucciones: "{text}". Esto puede tomar un momento...')
    
    try:
        # Usar IA para modificar el contenido
        modification_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Eres un editor profesional de blog."},
                {"role": "user", "content": f"Este es un post de blog:\n\nTítulo: {post['title']}\n\nContenido: {post['content']}\n\nModifica el post según estas instrucciones: {text}. Mantén el formato HTML."}
            ],
            max_tokens=1500
        )
        
        modified_content = modification_response.choices[0].message.content.strip()
        
        # Intentar extraer título y contenido del resultado
        if "Título:" in modified_content and "Contenido:" in modified_content:
            parts = modified_content.split("Título:", 1)[1].split("Contenido:", 1)
            new_title = parts[0].strip()
            new_content = parts[1].strip()
        else:
            # Si no podemos separar, asumimos que solo modificó el contenido
            new_title = post['title']
            new_content = modified_content
        
        # Asegurarnos de que el contenido esté en formato HTML
        if not new_content.startswith("<"):
            new_content = f"<p>{new_content.replace('\n\n', '</p><p>').replace('\n', '<br>')}</p>"
        
        # Actualizar el post
        user_posts[user_id]['title'] = new_title
        user_posts[user_id]['content'] = new_content
        
        # Mostrar resultado al usuario
        update.message.reply_text(
            f"He modificado el post según tus instrucciones:\n\n"
            f"📝 <b>Título:</b> {new_title}\n\n"
            f"<i>Para ver el contenido completo usa /revisar</i>\n\n"
            f"¿Qué quieres hacer ahora?",
            parse_mode=telegram.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Ver post completo", callback_data="revisar")],
                [InlineKeyboardButton("Seguir modificando", callback_data="modificar"), 
                 InlineKeyboardButton("Publicar", callback_data="publicar")],
                [InlineKeyboardButton("Guardar borrador", callback_data="guardar"),
                 InlineKeyboardButton("Cancelar", callback_data="cancelar")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error modificando post: {e}")
        update.message.reply_text(f"No se pudo modificar el post. Error: {str(e)}")

def publicar_command(update, context):
    """Publica el post en WordPress"""
    user_id = update.effective_user.id
    
    if user_id not in user_posts:
        update.message.reply_text('No hay ningún post en progreso. Usa /tema [tu tema] para empezar.')
        return
    
    post = user_posts[user_id]
    update.message.reply_text('Publicando post en WordPress...')
    
    # Publicar en WordPress
    success, response = publish_to_wordpress(post['title'], post['content'], 'publish')
    
    if success:
        post_id = response.get('id')
        post_link = response.get('link')
        update.message.reply_text(
            f'¡Post publicado con éxito!\n'
            f'ID: {post_id}\n'
            f'Link: {post_link}'
        )
        # Limpiar el post en progreso
        del user_posts[user_id]
    else:
        update.message.reply_text(f'Error al publicar: {response}')

def guardar_command(update, context):
    """Guarda el post como borrador en WordPress"""
    user_id = update.effective_user.id
    
    if user_id not in user_posts:
        update.message.reply_text('No hay ningún post en progreso. Usa /tema [tu tema] para empezar.')
        return
    
    post = user_posts[user_id]
    update.message.reply_text('Guardando post como borrador en WordPress...')
    
    # Guardar como borrador en WordPress
    success, response = publish_to_wordpress(post['title'], post['content'], 'draft')
    
    if success:
        post_id = response.get('id')
        update.message.reply_text(
            f'¡Borrador guardado con éxito!\n'
            f'ID: {post_id}'
        )
        # Limpiar el post en progreso
        del user_posts[user_id]
    else:
        update.message.reply_text(f'Error al guardar borrador: {response}')

def cancelar_command(update, context):
    """Cancela el post actual"""
    user_id = update.effective_user.id
    
    if user_id not in user_posts:
        update.message.reply_text('No hay ningún post en progreso.')
        return
    
    del user_posts[user_id]
    update.message.reply_text('Post cancelado. Puedes empezar uno nuevo con /tema [tu tema]')

# Manejo de botones inline
def button_callback(update, context):
    """Maneja las respuestas de los botones inline"""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "revisar":
        if user_id not in user_posts:
            query.edit_message_text('No hay ningún post en progreso. Usa /tema [tu tema] para empezar.')
            return
        
        post = user_posts[user_id]
        content_preview = post['content'][:300] + '...' if len(post['content']) > 300 else post['content']
        content_preview = content_preview.replace('<p>', '').replace('</p>', '\n\n').replace('<br>', '\n')
        
        query.edit_message_text(
            f"📝 <b>Título:</b> {post['title']}\n\n"
            f"<b>Vista previa:</b>\n{content_preview}\n\n"
            f"¿Qué quieres hacer ahora?",
            parse_mode=telegram.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Modificar", callback_data="modificar_prompt"), 
                 InlineKeyboardButton("Publicar", callback_data="publicar")],
                [InlineKeyboardButton("Guardar borrador", callback_data="guardar"),
                 InlineKeyboardButton("Cancelar", callback_data="cancelar")]
            ])
        )
    
    elif data == "modificar" or data == "modificar_prompt":
        query.edit_message_text(
            "Por favor, envía un mensaje con el comando /modificar seguido de tus instrucciones.\n\n"
            "Ejemplo: /modificar Agregar más detalles sobre el impacto ambiental"
        )
    
    elif data == "publicar":
        if user_id not in user_posts:
            query.edit_message_text('No hay ningún post en progreso.')
            return
        
        post = user_posts[user_id]
        query.edit_message_text('Publicando post en WordPress...')
        
        # Publicar en WordPress
        success, response = publish_to_wordpress(post['title'], post['content'], 'publish')
        
        if success:
            post_id = response.get('id')
            post_link = response.get('link')
            query.edit_message_text(
                f'¡Post publicado con éxito!\n'
                f'ID: {post_id}\n'
                f'Link: {post_link}'
            )
            # Limpiar el post en progreso
            del user_posts[user_id]
        else:
            query.edit_message_text(f'Error al publicar: {response}')
    
    elif data == "guardar":
        if user_id not in user_posts:
            query.edit_message_text('No hay ningún post en progreso.')
            return
        
        post = user_posts[user_id]
        query.edit_message_text('Guardando post como borrador en WordPress...')
        
        # Guardar como borrador en WordPress
        success, response = publish_to_wordpress(post['title'], post['content'], 'draft')
        
        if success:
            post_id = response.get('id')
            query.edit_message_text(
                f'¡Borrador guardado con éxito!\n'
                f'ID: {post_id}'
            )
            # Limpiar el post en progreso
            del user_posts[user_id]
        else:
            query.edit_message_text(f'Error al guardar borrador: {response}')
    
    elif data == "cancelar":
        if user_id not in user_posts:
            query.edit_message_text('No hay ningún post en progreso.')
            return
        
        del user_posts[user_id]
        query.edit_message_text('Post cancelado. Puedes empezar uno nuevo con /tema [tu tema]')

def echo(update, context):
    """Responde al mensaje del usuario."""
    update.message.reply_text('Comando no reconocido. Usa /help para ver los comandos disponibles.')

# Webhook para recibir actualizaciones
@app.route('/webhook', methods=['POST'])
def webhook():
    """Maneja las actualizaciones del webhook de Telegram"""
    if request.method == "POST":
        # Recuperar la actualización de Telegram
        update = telegram.Update.de_json(request.get_json(force=True), bot)
        
        # Configurar el dispatcher
        dispatcher = Dispatcher(bot, None, workers=0)
        
        # Registrar handlers
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(CommandHandler("tema", tema_command))
        dispatcher.add_handler(CommandHandler("revisar", revisar_command))
        dispatcher.add_handler(CommandHandler("modificar", modificar_command))
        dispatcher.add_handler(CommandHandler("publicar", publicar_command))
        dispatcher.add_handler(CommandHandler("guardar", guardar_command))
        dispatcher.add_handler(CommandHandler("cancelar", cancelar_command))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
        dispatcher.add_handler(telegram.ext.CallbackQueryHandler(button_callback))
        
        # Procesar la actualización
        dispatcher.process_update(update)
        
    return 'ok'

@app.route('/')
def index():
    """Página de inicio para verificar que la aplicación está funcionando"""
    return 'Bot generador de posts para WordPress activo!'

# Configurar el webhook
@app.route('/set_webhook')
def set_webhook():
    """Configura el webhook para el bot de Telegram"""
    url = request.url_root.replace('http://', 'https://')
    webhook_url = url + 'webhook'
    success = bot.set_webhook(webhook_url)
    
    if success:
        return f'Webhook configurado correctamente en: {webhook_url}'
    else:
        return 'Error al configurar el webhook'

# Iniciar el servidor
if __name__ == '__main__':
    # Para desarrollo local
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
