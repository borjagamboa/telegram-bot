import json
import logging
import os
from flask import Flask, request
import telegram
from telegram.ext import Dispatcher, MessageHandler, Filters, CallbackContext
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from google.cloud import secretmanager
import base64
import openai
import re

# Configuración de logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
user_posts = {}

def access_secret(secret_id):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{os.environ.get('PROJECT_ID')}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def get_config():
    try:
        telegram_token = access_secret('TELEGRAM_TOKEN')
        wp_url = access_secret('WORDPRESS_URL')
        wp_user = access_secret('WORDPRESS_USER')
        wp_password = access_secret('WORDPRESS_PASSWORD')
        openai_api_key = access_secret('OPENAI_API_KEY')
    except Exception as e:
        logger.warning(f"Error accessing Secret Manager: {e}. Using environment variables.")
        telegram_token = os.environ.get('TELEGRAM_TOKEN')
        wp_url = os.environ.get('WORDPRESS_URL')
        wp_user = os.environ.get('WORDPRESS_USER')
        wp_password = os.environ.get('WORDPRESS_PASSWORD')
        openai_api_key = os.environ.get('OPENAI_API_KEY')
    return telegram_token, wp_url, wp_user, wp_password, openai_api_key

telegram_token, wp_url, wp_user, wp_password, openai_api_key = get_config()
bot = telegram.Bot(token=telegram_token)
openai.api_key = openai_api_key

# Limpiar contenido HTML para evitar problemas con Telegram
def clean_html(content):
    clean = re.compile("<.*?>")
    return re.sub(clean, "", content)

def generate_content(tema, tone="informativo"):
    try:
        # Usar gpt-3.5-turbo para generar título y contenido en formato JSON
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Usamos gpt-3.5-turbo
            messages=[
                {"role": "system", "content": "Eres un asistente experto en generación de contenido. Genera un título atractivo y un contenido para un blog en formato JSON."},
                {"role": "user", "content": f"Genera un título atractivo y un artículo de blog sobre: {tema}"}
            ]
        )
        
        # Obtener la respuesta de OpenAI y extraer el JSON
        response_content = response['choices'][0]['message']['content'].strip()
        
        # Intentar cargar la respuesta como JSON
        try:
            post_data = json.loads(response_content)
            title = post_data.get("title", "Título no encontrado")
            content = post_data.get("content", "Contenido no encontrado")
        except json.JSONDecodeError:
            logger.error("Error al decodificar la respuesta JSON.")
            title = "Error generando título"
            content = "Error generando contenido."
        
        # Limpiar el contenido de cualquier HTML no permitido
        content = clean_html(content)
        
        if not content:
            content = "No se pudo generar contenido. Intenta más tarde."
        
        return title, content
    
    except Exception as e:
        logger.error(f"Error generando contenido: {e}")
        return f"Post sobre {tema}", "Error generando contenido. Intenta más tarde."

def publish_to_wordpress(title, content, status='draft'):
    api_url = f"{wp_url}/wp-json/wp/v2/posts"
    credentials = f"{wp_user}:{wp_password}"
    token = base64.b64encode(credentials.encode())
    headers = {
        'Authorization': f'Basic {token.decode("utf-8")}',
        'Content-Type': 'application/json'
    }
    post_data = {'title': title, 'content': content, 'status': status}
    response = requests.post(api_url, headers=headers, json=post_data)
    if response.status_code == 201:
        return True, response.json()
    return False, response.text

# Comienzo con botón
def start(update, context):
    update.message.reply_text(
        "¡Hola! ¿Sobre qué tema quieres generar un post?",
        reply_markup=telegram.ForceReply(selective=True)
    )

# Captura del tema desde texto libre (después de botón Start)
def handle_message(update, context):
    user_id = update.effective_user.id
    tema = update.message.text.strip()
    update.message.reply_text(f"Generando contenido para: {tema}")
    title, content = generate_content(tema)
    user_posts[user_id] = {"title": title, "content": content, "tema": tema}
    update.message.reply_text(
        f"📝 <b>Título:</b> {title}\n\n{content}",
        parse_mode=telegram.ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([  # Eliminado "Ver contenido"
            [InlineKeyboardButton("Publicar", callback_data="publicar")],
            [InlineKeyboardButton("Guardar borrador", callback_data="guardar")],
            [InlineKeyboardButton("Cancelar", callback_data="cancelar")]
        ])
    )

def button_callback(update, context):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    data = query.data

    if user_id not in user_posts:
        query.edit_message_text("No hay ningún post en progreso.")
        return

    post = user_posts[user_id]

    if data == "publicar":
        query.edit_message_text("Publicando en WordPress...")
        success, response = publish_to_wordpress(post['title'], post['content'], 'publish')
        if success:
            del user_posts[user_id]
            query.edit_message_text(f"✅ ¡Publicado!\n🔗 {response.get('link')}")
        else:
            query.edit_message_text(f"❌ Error: {response}")

    elif data == "guardar":
        query.edit_message_text("Guardando como borrador...")
        success, response = publish_to_wordpress(post['title'], post['content'], 'draft')
        if success:
            del user_posts[user_id]
            query.edit_message_text(f"📝 Borrador guardado. ID: {response.get('id')}")
        else:
            query.edit_message_text(f"❌ Error: {response}")

    elif data == "cancelar":
        del user_posts[user_id]
        query.edit_message_text("❌ Post cancelado. Puedes comenzar uno nuevo enviando otro tema.")

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        update = telegram.Update.de_json(request.get_json(force=True), bot)
        dispatcher = Dispatcher(bot, None, workers=0)
        dispatcher.add_handler(MessageHandler(Filters.reply, handle_message))
        dispatcher.add_handler(MessageHandler(Filters.command, start))  # Solo comando /start
        dispatcher.add_handler(telegram.ext.CallbackQueryHandler(button_callback))
        dispatcher.process_update(update)
    return 'ok'

@app.route('/')
def index():
    return 'Bot activo con botones!'

@app.route('/set_webhook')
def set_webhook():
    url = request.url_root.replace('http://', 'https://')
    webhook_url = url + 'webhook'
    success = bot.set_webhook(webhook_url)
    return f'Webhook {"configurado" if success else "fallido"}: {webhook_url}'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

