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

def clean_html(content):
    clean = re.compile("<.*?>")
    return re.sub(clean, "", content)

def generate_content(tema, tone="informativo"):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[ 
                {"role": "system", "content": "Eres un asistente experto en generación de contenido y en neurorrehabilitación. Genera un título atractivo y un contenido para un blog en formato JSON."},
                {"role": "user", "content": f"Genera un título atractivo y un artículo de blog sobre: {tema}. Devuélvelo en json usando los tags title y content. Máximo 700 palabras. No añadas comentarios"}
            ]
        )
        response_content = response['choices'][0]['message']['content'].strip()
        try:
            post_data = json.loads(response_content)
            title = post_data.get("title", "Título no encontrado")
            content = post_data.get("content", "Contenido no encontrado")
        except json.JSONDecodeError:
            logger.error(f"Error al decodificar la respuesta JSON: {response}")
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
    logger.info(f"Enviando solicitud a WordPress: {api_url}")
    logger.info(f"Datos del post: {post}")
    logger.info(f"Respuesta de WordPress: {response.status_code}")
    logger.info(f"Contenido de la respuesta: {response.json()}")

    if response.status_code == 201:
        return True, response.json()
    else:
        return False, f"Error al publicar: {response.status_code} - {response.text}"

def start(update, context):
    update.message.reply_text("¡Hola! ¿Sobre qué tema quieres generar un post?")
    return TEMA

def handle_message(update, context):
    user_id = update.effective_user.id
    tema = update.message.text.strip()

    # Enviar el primer mensaje de que está generando el contenido
    loading_message = update.message.reply_text("⏳ Generando contenido...")

    # Animación de puntos, que se actualizará cada 0.5 segundos
    dots = 0
    while dots < 3:  # Hacerlo por 3 ciclos (aparecerán 3 puntos)
        loading_message.edit_text(f"⏳ Generando contenido...{'.' * (dots + 1)}")
        time.sleep(0.5)  # Pausa de 0.5 segundos
        dots += 1

    # Realizar el proceso de generación
    title, content = generate_content(tema)
    user_posts[user_id] = {"title": title, "content": content, "tema": tema}

    # Borrar el mensaje de "cargando..." y enviar el contenido generado
    loading_message.edit_text("⏳ Generando contenido... . . .")  # Aquí aparece la animación de puntos

    # Después de unos segundos, mostrar el contenido
    update.message.reply_text(
        f"📝 <b>Título:</b> {title}\n\n{content}",
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
        query.edit_message_text("No hay ningún post en progreso.")
        return ConversationHandler.END

    post = user_posts[user_id]

    if data == "publicar":
        query.edit_message_text("📤 Publicando en WordPress...")
        success, response = publish_to_wordpress(post['title'], post['content'], 'publish')
        if success:
            del user_posts[user_id]
            # Enviar mensaje confirmando que el post fue publicado
            bot.send_message(chat_id=user_id, text=f"✅ ¡Publicado!\n🔗 {response.get('link')}")
        else:
            send_message_in_chunks(bot, user_id, f"❌ Error al publicar: {response}")
        return ConversationHandler.END

    elif data == "rehacer":
        bot.send_message(chat_id=user_id, text="♻️ Rehaciendo propuesta, un momento...")
        title, content = generate_content(post['tema'])
        user_posts[user_id] = {"title": title, "content": content, "tema": post['tema']}
        bot.send_message(
            chat_id=user_id,
            text=f"🔁 <b>Título:</b> {title}\n\n{content}",
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
        "Realiza una versión mejorada teniendo en cuenta las sugerencias. Devuelve un JSON con 'title' y 'content'."
    )

    update.message.reply_text("🛠️ Procesando sugerencias...")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente experto en contenido de blog. Devuelve el resultado en JSON."},
                {"role": "user", "content": prompt}
            ]
        )
        content = response['choices'][0]['message']['content'].strip()

        # Validar que el contenido es JSON antes de parsear
        try:
            post_data = json.loads(content)
            title = post_data.get("title", "Título")
            content = clean_html(post_data.get("content", "Contenido"))
        except json.JSONDecodeError:
            logger.error(f"Respuesta no es JSON válida: {content}")
            update.message.reply_text("⚠️ La respuesta del modelo no es válida. Intenta nuevamente.")
            return PROPUESTA

        user_posts[user_id] = {"title": title, "content": content, "tema": tema_original}

        update.message.reply_text(
            f"📝 <b>Título:</b> {title}\n\n{content}",
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
        logger.error(f"Error en sugerencias: {e}")
        update.message.reply_text("⚠️ Ocurrió un error al procesar tus sugerencias. Inténtalo de nuevo.")
        return PROPUESTA


# Configurar dispatcher y handlers globales
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

