from flask import Flask, request, jsonify
import json
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackContext, CallbackQueryHandler, ConversationHandler
)

# importar OPENAI
import openai

# 🔑 Sustituye por tu token de Telegram y API Key de OpenAI
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

# Configurar OpenAI
openai.api_key = OPENAI_API_KEY

# Configurar Flask
app = Flask(__name__)

import logging

# Configurar el logging
log_file = '/tmp/app.log'  # Ruta de archivo en Google Cloud (usualmente en /tmp)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),  # Esto asegura que los logs también se muestren en consola
        logging.FileHandler(log_file)  # Guardar los logs en un archivo
    ]
)

logger = logging.getLogger(__name__)

# Log inicial para verificar si el logging está funcionando
logger.info("El logging esta activo.")

# Estados de la conversación
TEMA, CONFIRMAR_TEMA, GENERAR_POST = range(3)

# Crear instancia del bot
application = Application.builder().token(TOKEN).build()

logger.info("La aplicacion se ha iniciado.")

# 📌 Comando /start
async def start(update: Update, context: CallbackContext) -> None:
    logger.info(f" /start recibido de {update.message.from_user.first_name} ({update.message.from_user.id})")
    await update.message.reply_text("¡Hola! ¿Cómo puedo ayudarte?")

    keyboard = [
        [InlineKeyboardButton("Publicar post en blog", callback_data="publish_blog")],
        [InlineKeyboardButton("Nada, olvídalo", callback_data="nothing")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Selecciona una opción:", reply_markup=reply_markup)


# 📌 Manejo de botones
async def button(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "publish_blog":
        await query.edit_message_text(text="¡Genial! ¿Sobre qué tema te gustaría publicar en el blog?")
        return TEMA

    elif query.data == "nothing":
        await query.edit_message_text(text="Está bien, olvídalo.")
        return ConversationHandler.END


# 📌 Estado 1: Recibir el tema
async def tema(update: Update, context: CallbackContext) -> int:
    context.user_data["tema"] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Confirmar", callback_data="confirm")],
        [InlineKeyboardButton("Repetir", callback_data="repeat")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Has propuesto el tema: {context.user_data['tema']}. ¿Confirmar?",
                                    reply_markup=reply_markup)
    return CONFIRMAR_TEMA


# 📌 Estado 2: Confirmar o repetir el tema
async def confirmar_tema(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "confirm":
        await query.edit_message_text(f"¡Perfecto! Generando el post sobre '{context.user_data['tema']}'... ⏳")
        return await generar_post(update, context)

    elif query.data == "repeat":
        await query.edit_message_text(text="Por favor, proporciona nuevamente el tema del post:")
        return TEMA


# 📌 Estado 3: Generar post con OpenAI
async def generar_post(update: Update, context: CallbackContext) -> int:
    tema = context.user_data.get("tema", "un tema interesante")
    try:
        response = openai.ChatCompletion.create(  # Aquí debería ser openai.ChatCompletion
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": "Eres un asistente experto en redacción de blogs."},
                {"role": "user",
                 "content": f"Escribe un post sobre {tema}. Que tenga unas 600 palabras"}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        post_generado = response.choices[0].message['content']  # Corregido
        await update.effective_message.reply_text(f"✍️ Aquí tienes un post generado:\n\n{post_generado}")

    except Exception as e:
        await update.effective_message.reply_text("❌ Error generando el post. Inténtalo de nuevo.")
        logger.error(f"Error con OpenAI: {e}")

    return ConversationHandler.END


# 📌 Cancelar conversación
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("La conversación ha sido cancelada. Escribe /start para comenzar de nuevo.")
    return ConversationHandler.END


# Configuración del manejador de Telegram
def setup_telegram():
    logger.info("Configurando Telegram.")
    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), CallbackQueryHandler(button)],
        states={
            TEMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, tema)],
            CONFIRMAR_TEMA: [CallbackQueryHandler(confirmar_tema)],
            GENERAR_POST: [MessageHandler(filters.TEXT & ~filters.COMMAND, generar_post)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    application.add_handler(conversation_handler)
    application.add_handler(CommandHandler("cancel", cancel))
    logger.info("Telegram configurado correctamente.")


# 📌 Configurar el webhook
def set_webhook():
    logger.info(f" Intentando configurar Webhook en: {webhook_url}")
    webhook_url = f"https://{PROJECT_ID}.appspot.com/{TOKEN}"  # Usa la URL de tu app
    application.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook configurado en: {webhook_url}")


@app.route('/')
def home():
    return 'Funcionando correctamente'


# 📌 Ruta de Webhook en Flask
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    logger.info(f"📩 Datos recibidos en webhook: {json_str}")  # Log de lo recibido

    try:
        json_data = json.loads(json_str)
        update = Update.de_json(json_data, application.bot)
        application.update_queue.put(update)  # Esto se puede manejar con polling en lugar de async
    except json.JSONDecodeError:
        logger.error("❌ Error al decodificar el JSON")
        return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400

    return jsonify({'status': 'ok'}), 200
    

# 📌 Ruta de depuración en Flask
@app.route('/debug', methods=['GET'])
def debug():
    # Mostrar logs recientes
    try:
        with open("/tmp/app.log", "r") as file:
            logs = file.readlines()
        return jsonify({'logs': logs}), 200
    except Exception as e:
        logger.error(f"Error leyendo el archivo de logs: {e}")
        return jsonify({'status': 'error', 'message': 'Could not read logs'}), 500


if __name__ == "__main__":
    setup_telegram()

    # Iniciar el webhook de Telegram
    set_webhook()

    # Ejecutar la app de Flask
    app.run(host="0.0.0.0", port=8080, debug=True)
