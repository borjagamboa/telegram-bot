import json
import logging
import os
from flask import Flask, request
import telegram
from telegram.ext import (
    Dispatcher, MessageHandler, Filters, CallbackContext,
    ConversationHandler, CallbackQueryHandler
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from google.cloud import secretmanager
import openai
import re
import time
import threading
import difflib

# Configuración de logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
user_posts = {}

# Estados para ConversationHandler
TEMA, PROPUESTA, SUGERENCIAS, SELECCION_MODELO = range(4)

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

# Modelo por defecto
openai_model = 'gpt-3.5-turbo'

def clean_html(content):
    clean = re.compile("<.*?>")
    return re.sub(clean, "", content)

def generate_content(tema, tone="informativo", model="gpt-3.5-turbo"):
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "Eres un asistente experto en generación de contenido de blog y en neurorrehabilitación. Devuelve solo un JSON con 'title' y 'content'."},
                {"role": "user", "content": f"Genera un título atractivo con un emoji al inicio y un artículo de blog sobre: {tema}. Pon algún emoji también en el texto. Devuélvelo en JSON usando los tags title y content. No añadas comentarios a tu respuesta. Máximo 1000 palabras."}
            ]
        )
        content = response['choices'][0]['message']['content'].strip()
        try:
            post_data = json.loads(content)
            title = post_data.get("title", "Título no encontrado")
            content = post_data.get("content", "Contenido no encontrado")
        except json.JSONDecodeError:
            logger.error(f"Error al decodificar JSON: {content}")
            title = "Error generando título"
            content = "Error generando contenido."

        content = clean_html(content)
        return title, content

    except Exception as e:
        logger.error(f"Error generando contenido: {e}")
        return f"Post sobre {tema}", "Error generando contenido. Intenta más tarde."

def publish_to_wordpress(title, content, status='publish'):
    api_url = f"{wp_url}/wp-json/wp/v2/posts"
    r = requests.post(f"{wp_url}/wp-json/jwt-auth/v1/token", data={
        'username': wp_user,
        'password': wp_password
    })
    token = r.json()['token']
    headers = {
        'Authorization': f'Bearer {token}'
    }
    post = {
        'title': title,
        'status': status,
        'content': content
    }
    response = requests.post(api_url, headers=headers, json=post)
    if response.status_code == 201:
        return True, response.json()
    else:
        return False, f"Error al publicar: {response.status_code} - {response.text}"

def start(update, context):
    update.message.reply_text(
        "👋 ¡Hola! ¿Sobre qué tema quieres generar un post?\n"
        "Primero, elige el modelo que prefieres usar:\n"
        "1. GPT-3.5\n2. GPT-3.5 Turbo\n3. GPT-4"
    )
    return SELECCION_MODELO

def animated_loading(message, base_text="Generando"):
    stop_flag = threading.Event()
    def animate():
        states = [f"⏳ {base_text}", f"⏳ {base_text}.", f"⏳ {base_text}..", f"⏳ {base_text}..."]
        i = 0
        while not stop_flag.is_set():
            try:
                message.edit_text(states[i % len(states)])
                time.sleep(0.6)
                i += 1
            except Exception:
                break
    thread = threading.Thread(target=animate)
    thread.start()
    return stop_flag

def diff_highlight(original, modified):
    differ = difflib.ndiff(original.split(), modified.split())
    result = []
    for word in differ:
        if word.startswith("+ "):
            result.append(f"<u>{word[2:]}</u>")
        elif word.startswith("  "):
            result.append(word[2:])
    return ' '.join(result)

def handle_message(update, context):
    user_id = update.effective_user.id
    tema = update.message.text.strip()
    loading_message = update.message.reply_text("⏳ Generando.")
    stop_flag = animated_loading(loading_message, base_text="Generando")
    title, content = generate_content(tema, model=context.user_data['selected_model'])
    user_posts[user_id] = {"title": title, "content": content, "tema": tema}
    stop_flag.set()

    update.message.reply_text(
        f"📝 <b>{title}</b>\n\n{content}",
        parse_mode=telegram.ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Rehacer propuesta", callback_data="rehacer")],
            [InlineKeyboardButton("✏️ Sugerir cambios", callback_data="cambios")],
            [InlineKeyboardButton("🆕 Cambiar tema", callback_data="cambiar")],
            [InlineKeyboardButton("✅ Publicar", callback_data="publicar")]
        ])
    )
    return PROPUESTA

def button_callback(update, context):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    data = query.data
    if user_id not in user_posts:
        query.edit_message_text("⚠️ No hay ningún post en progreso.")
        return ConversationHandler.END

    post = user_posts[user_id]

    if data == "publicar":
        msg = bot.send_message(chat_id=user_id, text="📤 Publicando...")
        stop_flag = animated_loading(msg, base_text="Publicando")
        success, response = publish_to_wordpress(post['title'], post['content'], 'publish')
        stop_flag.set()
        if success:
            del user_posts[user_id]
            bot.send_message(chat_id=user_id, text=f"✅ ¡Publicado!\n🔗 {response.get('link')}")
        else:
            bot.send_message(chat_id=user_id, text=f"❌ Error al publicar: {response}")
        return ConversationHandler.END

    elif data == "rehacer":
        msg = bot.send_message(chat_id=user_id, text="♻️ Rehaciendo propuesta...")
        stop_flag = animated_loading(msg, base_text="Generando")
        title, content = generate_content(post['tema'], model=context.user_data['selected_model'])
        user_posts[user_id] = {"title": title, "content": content, "tema": post['tema']}
        stop_flag.set()
        bot.send_message(
            chat_id=user_id,
            text=f"🔁 <b>{title}</b>\n\n{content}",
            parse_mode=telegram.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Rehacer propuesta", callback_data="rehacer")],
                [InlineKeyboardButton("✏️ Sugerir cambios", callback_data="cambios")],
                [InlineKeyboardButton("🆕 Cambiar tema", callback_data="cambiar")],
                [InlineKeyboardButton("✅ Publicar", callback_data="publicar")]
            ])
        )
        return PROPUESTA

    elif data == "cambiar":
        del user_posts[user_id]
        bot.send_message(chat_id=user_id, text="🆕 ¿Cuál es el nuevo tema?")
        return TEMA

    elif data == "cambios":
        bot.send_message(chat_id=user_id, text="✏️ Escribe tus sugerencias para mejorar la propuesta actual:")
        return SUGERENCIAS

def handle_sugerencias(update, context):
    user_id = update.effective_user.id
    sugerencias = update.message.text.strip()
    tema_original = user_posts[user_id]['tema']
    contenido_actual = user_posts[user_id]['content']
    prompt = (
        f"Este es el contenido anterior de un artículo de blog:\n\n{contenido_actual}\n\n"
        f"Estas son sugerencias del usuario para mejorarlo:\n{sugerencias}\n\n"
        "Realiza una versión mejorada pero no modifiques más de lo necesario. Devuelve solo un JSON con 'title' y 'content'. No añadas comentarios a tu respuesta. Máximo 1000 palabras."
    )

    msg = update.message.reply_text("🛠️ Aplicando sugerencias...")
    stop_flag = animated_loading(msg, base_text="Generando")

    try:
        response = openai.ChatCompletion.create(
            model=context.user_data['selected_model'],
            messages=[
                {"role": "system", "content": "Eres un asistente experto en redacción. Devuelve solo un JSON con 'title' y 'content'."},
                {"role": "user", "content": prompt}
            ]
        )
        result = response['choices'][0]['message']['content'].strip()
        post_data = json.loads(result)
        title = post_data.get("title", tema_original)
        nuevo_content = clean_html(post_data.get("content", contenido_actual))
        highlighted = diff_highlight(contenido_actual, nuevo_content)
        user_posts[user_id] = {"title": title, "content": nuevo_content, "tema": tema_original}
        stop_flag.set()

        update.message.reply_text(
            f"📝 <b>{title}</b>\n\n{highlighted}",
            parse_mode=telegram.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Rehacer propuesta", callback_data="rehacer")],
                [InlineKeyboardButton("✏️ Sugerir cambios", callback_data="cambios")],
                [InlineKeyboardButton("🆕 Cambiar tema", callback_data="cambiar")],
                [InlineKeyboardButton("✅ Publicar", callback_data="publicar")]
            ])
        )
        return PROPUESTA

    except Exception as e:
        stop_flag.set()
        logger.error(f"Error en sugerencias: {e}")
        update.message.reply_text("⚠️ Ocurrió un error al procesar tus sugerencias. Inténtalo de nuevo.")
        return PROPUESTA

# Dispatcher y webhook
dispatcher = Dispatcher(bot, None, workers=0)

conv_handler = ConversationHandler(
    entry_points=[MessageHandler(Filters.command, start)],
    states={
        SELECCION_MODELO: [MessageHandler(Filters.text & ~Filters.command, handle_model_selection)],
        TEMA: [MessageHandler(Filters.text & ~Filters.command, handle_message)],
        PROPUESTA: [CallbackQueryHandler(button_callback)],
        SUGERENCIAS: [MessageHandler(Filters.text & ~Filters.command, handle_sugerencias)],
    },
    fallbacks=[MessageHandler(Filters.command, start)]
)

dispatcher.add_handler(conv_handler)

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        update = telegram.Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
    return 'ok'

@app.route('/')
def index():
    return '🤖 Bot activo con botones y animaciones'

@app.route('/set_webhook')
def set_webhook():
    url = request.url_root.replace('http://', 'https://')
    webhook_url = url + 'webhook'
    success = bot.set_webhook(webhook_url)
    return f'Webhook {"configurado" if success else "fallido"}: {webhook_url}'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
