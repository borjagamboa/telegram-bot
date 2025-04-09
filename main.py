# NOTA: Se han quitado los comandos /tema, /modificar, etc.
# Todo se maneja con botones ahora.

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

def generate_content(tema, tone="informativo"):
    try:
        title_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"Eres un experto en crear títulos atractivos para blogs."},
                {"role": "user", "content": f"Crea un título para un post sobre: {tema}"}
            ],
            max_tokens=50
        )
        title = title_response.choices[0].message.content.strip().replace('"', '')
        content_response = openai.ChatCompletion.create(
            model="gpt-3.5",
            messages=[
                {"role": "system", "content": f"Eres un blogger profesional."},
                {"role": "user", "content": f"Escribe un artículo de blog sobre {tema} titulado '{title}' en formato HTML y de máximo 700 palabras."}
            ],
            max_tokens=700
        )
        content = content_response.choices[0].message.content.strip()
        if not content.startswith("<"):
            content = "<p>" + content.replace('\n\n', '</p><p>').replace('\n', '<br>') + "</p>"
        return title, content
    except Exception as e:
        logger.error(f"Error generando contenido: {e}")
        return f"Post sobre {tema}", f"<p>Error generando contenido. Intenta más tarde.</p>"

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
        f"📝 <b>Título:</b> {title}\n\n<i>Post generado.</i>",
        parse_mode=telegram.ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Ver contenido", callback_data="ver")],
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

    if data == "ver":
        content = post['content']
        query.edit_message_text(
            f"<b>{post['title']}</b>\n\n{content}",
            parse_mode=telegram.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Publicar", callback_data="publicar")],
                [InlineKeyboardButton("Guardar borrador", callback_data="guardar")],
                [InlineKeyboardButton("Cancelar", callback_data="cancelar")]
            ])
        )

    elif data == "publicar":
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

