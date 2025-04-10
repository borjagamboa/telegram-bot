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
MODELO, TEMA, PROPUESTA, SUGERENCIAS = range(4)

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
openai_model = 'gpt-3.5-turbo-instruct'

def clean_html(content):
    clean = re.compile("<.*?>")
    return re.sub(clean, "", content)

# Aquí agregamos una función para obtener las etiquetas con colores
def obtener_color_precio(modelo):
    precios = {
        "gpt-3.5-turbo": ("Muy barato", "green"),
        "gpt-3.5-turbo-instruct": ("Barato", "yellow"),
        "gpt-4": ("Caro", "orange"),
        "gpt-4-turbo": ("Muy caro", "red")
    }
    return precios.get(modelo, ("Desconocido", "gray"))
    
# Función para seleccionar modelo
def seleccionar_modelo(update, context):
    keyboard = [
        [InlineKeyboardButton(f"GPT-3.5 Turbo - {obtener_color_precio('gpt-3.5-turbo')[0]}", callback_data="modelo_gpt-3.5-turbo")],
        [InlineKeyboardButton(f"GPT-3.5 Instruct - {obtener_color_precio('gpt-3.5-turbo-instruct')[0]}", callback_data="modelo_gpt-3.5-turbo-instruct")],
        [InlineKeyboardButton(f"GPT-4 - {obtener_color_precio('gpt-4')[0]}", callback_data="modelo_gpt-4")],
        [InlineKeyboardButton(f"GPT-4 Turbo - {obtener_color_precio('gpt-4-turbo')[0]}", callback_data="modelo_gpt-4-turbo")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Selecciona el modelo de OpenAI que quieres usar:", reply_markup=reply_markup)
    return MODELO

def generate_content(tema, tone="informativo", model="gpt-3.5-turbo"):
    try:
        if model == "gpt-3.5-turbo-instruct":
            # Usamos el endpoint completions para el modelo instruct
            response = openai.Completion.create(
                model=model,
                prompt=f"Genera un título atractivo y un artículo de blog sobre: {tema}. Usa algún emoji. Devuélvelo en formato JSON con los tags 'title' y 'content'. El artículo debe incluir al menos un emoji relevante. Máximo 1000 palabras. No añadas comentarios.",
                max_tokens=700,
                n=1,
                stop=None,
                temperature=0.7
            )
            response_content = response.choices[0].text.strip()
        else:
            # Usamos el modelo chat (gpt-3.5-turbo por defecto)
            response = openai.ChatCompletion.create(
                model=model,
                messages=[ 
                    {"role": "system", "content": "Eres un asistente experto en generación de contenido y en neurorrehabilitación. Genera un título atractivo y un contenido para un blog en formato JSON."},
                    {"role": "user", "content": f"Genera un título atractivo y un artículo de blog sobre: {tema}. Devuélvelo en json usando los tags title y content. El artículo debe incluir al menos un emoji relevante. Máximo 1000 palabras. No añadas comentarios"}
                ]
            )
            response_content = response['choices'][0]['message']['content'].strip()

        try:
            post_data = json.loads(response_content)
            title = post_data.get("title", "Título no encontrado")
            content = post_data.get("content", "Contenido no encontrado")
        except json.JSONDecodeError:
            logger.error(f"Error al decodificar la respuesta JSON: {response_content}")
            title = "Error generando título"
            content = "Error generando contenido."

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
    update.message.reply_text("👋 ¡Hola! ¿Qué modelo quieres que utilice?")
    return MODELO

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

def handle_model_selection(update, context):
    query = update.callback_query
    query.answer()
    model = query.data.replace("modelo_", "")
    context.user_data["modelo"] = model
    query.edit_message_text(f"✅ Modelo seleccionado: {model}\n\nAhora, dime el tema para el post.")
    return TEMA

def handle_message(update, context):
    user_id = update.effective_user.id
    tema = update.message.text.strip()
    model = context.user_data.get("modelo", "gpt-3.5-turbo")
    loading_message = update.message.reply_text("⏳ Generando.")
    stop_flag = animated_loading(loading_message, base_text="Generando")
    title, content = generate_content(tema, model)
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
    model = context.user_data.get("modelo", "gpt-3.5-turbo")
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
        title, content = generate_content(post['tema'], model)
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
    model = context.user_data.get("modelo", "gpt-3.5-turbo")
    sugerencias = update.message.text.strip()
    tema_original = user_posts[user_id]['tema']
    contenido_actual = user_posts[user_id]['content']
    
    prompt = (
        f"Este es el contenido anterior de un artículo de blog:\n\n{contenido_actual}\n\n"
        f"Estas son sugerencias del usuario para mejorarlo:\n{sugerencias}\n\n"
        "Realiza una versión mejorada pero no modifiques más de lo necesario. Devuélvelo en json usando los tags title y content. No añadas comentarios a tu respuesta. Máximo 1000 palabras."
    )

    msg = update.message.reply_text("🛠️ Aplicando sugerencias...")
    stop_flag = animated_loading(msg, base_text="Generando")

    try:
        if model == "gpt-3.5-turbo-instruct":
            # Usamos el endpoint completions para el modelo instruct
            response = openai.Completion.create(
                model=openai_model,
                prompt=prompt,
                max_tokens=700,
                n=1,
                stop=None,
                temperature=0.7)
            response_content = response.choices[0].text.strip()
        else:
            # Usamos el modelo chat (gpt-3.5-turbo por defecto)
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[ 
                    {"role": "system", "content": "Eres un asistente experto en generación de contenido y en neurorrehabilitación. Genera un título atractivo y un contenido para un blog en formato JSON."},
                    {"role": "user", "content": promp}
                ])
            response_content = response['choices'][0]['message']['content'].strip()

        try:
            post_data = json.loads(response_content)
            title = post_data.get("title", "Título no encontrado")
            content = post_data.get("content", contenido_actual)
        except json.JSONDecodeError:
            logger.error(f"Error al decodificar la respuesta JSON: {response_content}")
            title = "Error generando título"
            content = "Error generando contenido."
        nuevo_content = clean_html(content)
        if not content:
            content = "No se pudo generar contenido. Intenta más tarde."
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
        logger.error(f"Error en sugerencias: {e}. Respuesta: ")
        update.message.reply_text("⚠️ Ocurrió un error al procesar tus sugerencias. Inténtalo de nuevo.")
        return PROPUESTA

# Dispatcher y webhook
dispatcher = Dispatcher(bot, None, workers=0)

conv_handler = ConversationHandler(
    entry_points=[MessageHandler(Filters.command, start)],
    states={
        MODELO: [CallbackQueryHandler(handle_model_selection)],
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
