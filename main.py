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

# Configuración de logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
user_posts = {}

# Estados para ConversationHandler
TEMA, PROPUESTA, SUGERENCIAS = range(3)

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

# Función para obtener las etiquetas con colores según el modelo
def obtener_color_precio(modelo):
    precios = {
        "gpt_3_turbo": ("Muy barato", "green"),
        "gpt_3_5_instruct": ("Barato", "yellow"),
        "gpt_4": ("Caro", "orange"),
        "gpt_4_turbo": ("Muy caro", "red")
    }
    return precios.get(modelo, ("Desconocido", "gray"))

# Función para seleccionar modelo
def seleccionar_modelo(update, context):
    keyboard = [
        [InlineKeyboardButton(f"GPT-3 Turbo - {obtener_color_precio('gpt_3_turbo')[0]}", callback_data="gpt_3_turbo")],
        [InlineKeyboardButton(f"GPT-3.5 Instruct - {obtener_color_precio('gpt_3_5_instruct')[0]}", callback_data="gpt_3_5_instruct")],
        [InlineKeyboardButton(f"GPT-4 - {obtener_color_precio('gpt_4')[0]}", callback_data="gpt_4")],
        [InlineKeyboardButton(f"GPT-4 Turbo - {obtener_color_precio('gpt_4_turbo')[0]}", callback_data="gpt_4_turbo")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Selecciona el modelo de OpenAI que quieres usar:", reply_markup=reply_markup)
    return TEMA

# Función para manejar la elección del modelo
def button_callback(update, context):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    data = query.data

    # Guardar el modelo seleccionado
    if user_id not in user_posts:
        user_posts[user_id] = {}
    user_posts[user_id]['modelo'] = data

    # Continuar con la conversación, pidiendo el tema para generar el contenido
    query.edit_message_text("¡Perfecto! Ahora, ¿sobre qué tema quieres generar un post?")
    return TEMA

def clean_html(content):
    clean = re.compile("<.*?>")
    return re.sub(clean, "", content)

def generate_content(tema, modelo, tone="informativo"):
    try:
        model_mapping = {
            "gpt_3_turbo": "gpt-3.5-turbo",  # GPT-3 Turbo
            "gpt_3_5_instruct": "text-davinci-003",  # GPT-3.5 Instruct
            "gpt_4": "gpt-4",  # GPT-4
            "gpt_4_turbo": "gpt-4-turbo"  # GPT-4 Turbo
        }

        model = model_mapping.get(modelo, "gpt-3.5-turbo")  # Default to gpt-3.5-turbo if no model is matched

        response = openai.Completion.create(
            model=model,
            prompt=f"Genera un título atractivo y un artículo de blog sobre: {tema}. Devuélvelo en json usando los tags title y content. Máximo 700 palabras. No añadas comentarios",
            max_tokens=2000
        )
        response_content = response['choices'][0]['text'].strip()

        post_data = json.loads(response_content)
        title = post_data.get("title", "Título no encontrado")
        content = post_data.get("content", "Contenido no encontrado")
        content = clean_html(content)

        if not content:
            content = "No se pudo generar contenido. Intenta más tarde."
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
    update.message.reply_text("¡Hola! ¿Sobre qué tema quieres generar un post?")
    return TEMA

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

def handle_message(update, context):
    user_id = update.effective_user.id
    tema = update.message.text.strip()

    loading_message = update.message.reply_text("⏳ Generando.")
    stop_flag = animated_loading(loading_message, base_text="Generando")

    modelo = user_posts.get(user_id, {}).get('modelo', 'gpt_3_turbo')  # Default to gpt_3_turbo if no model selected
    title, content = generate_content(tema, modelo)
    user_posts[user_id] = {"title": title, "content": content, "tema": tema, "modelo": modelo}

    stop_flag.set()

    update.message.reply_text(
        f"📝 <b>Título:</b> {title}\n\n{content}",
        parse_mode=telegram.ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Rehacer propuesta", callback_data="rehacer"),
            InlineKeyboardButton("✏️ Sugerir cambios", callback_data="cambios"),
            InlineKeyboardButton("🆕 Cambiar tema", callback_data="cambiar"),
            InlineKeyboardButton("✅ Publicar", callback_data="publicar")
        ]])
    )
    return PROPUESTA

def button_callback(update, context):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    data = query.data

    if user_id not in user_posts:
        query.edit_message_text("No hay ningún post en progreso.")
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

        title, content = generate_content(post['tema'], post['modelo'])
        user_posts[user_id] = {"title": title, "content": content, "tema": post['tema'], "modelo": post['modelo']}
        stop_flag.set()

        bot.send_message(
            chat_id=user_id,
            text=f"🔁 <b>Título:</b> {title}\n\n{content}",
            parse_mode=telegram.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Rehacer propuesta", callback_data="rehacer"),
                InlineKeyboardButton("✏️ Sugerir cambios", callback_data="cambios"),
                InlineKeyboardButton("🆕 Cambiar tema", callback_data="cambiar"),
                InlineKeyboardButton("✅ Publicar", callback_data="publicar")
            ]])
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
        "Realiza una versión mejorada teniendo en cuenta las sugerencias. Devuelve únicamente un JSON con 'title' y 'content'."
    )

    msg = update.message.reply_text("🛠️ Aplicando sugerencias...")
    stop_flag = animated_loading(msg, base_text="Generando")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente experto en contenido de blog. Me tienes que devolver solamente en JSON con 'title' y 'content'."},
                {"role": "user", "content": prompt}
            ]
        )
        content = response['choices'][0]['message']['content'].strip()

        try:
            post_data = json.loads(content)
            title = post_data.get("title", "Título")
            content = clean_html(post_data.get("content", "Contenido"))
        except json.JSONDecodeError:
            stop_flag.set()
            logger.error(f"Respuesta no es JSON válida: {content}")
            update.message.reply_text("⚠️ La respuesta del modelo no es válida. Intenta nuevamente.")
            return PROPUESTA

        user_posts[user_id] = {"title": title, "content": content, "tema": tema_original}
        stop_flag.set()

        update.message.reply_text(
            f"📝 <b>Título:</b> {title}\n\n{content}",
            parse_mode=telegram.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Rehacer propuesta", callback_data="rehacer"),
                InlineKeyboardButton("✏️ Sugerir cambios", callback_data="cambios"),
                InlineKeyboardButton("🆕 Cambiar tema", callback_data="cambiar"),
                InlineKeyboardButton("✅ Publicar", callback_data="publicar")
            ]])
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
    return 'Bot activo con botones!'

@app.route('/set_webhook')
def set_webhook():
    url = request.url_root.replace('http://', 'https://')
    webhook_url = url + 'webhook'
    success = bot.set_webhook(webhook_url)
    return f'Webhook {"configurado" if success else "fallido"}: {webhook_url}'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))


