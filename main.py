import logging
import os
import json
import asyncio
import threading
from flask import Flask, request, jsonify, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackContext, CallbackQueryHandler, ConversationHandler
)
import openai
import sys
sys.path.insert(0, 'lib')


# 🔑 Variables de entorno
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

# ✅ Configurar OpenAI
openai.api_key = OPENAI_API_KEY

# ✅ Configurar Flask
app = Flask(__name__)

# ✅ Configurar logging
log_file = "/tmp/app.log"  # App Engine usa /tmp para archivos temporales
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger(__name__)

# 🔄 Estados de conversación
TEMA, CONFIRMAR_TEMA, GENERAR_POST = range(3)

# ✅ Iniciar bot
logger.info("Iniciando la aplicación de Telegram...")
application = Application.builder().token(TOKEN).build()

# 📌 Comando /start
async def start(update: Update, context: CallbackContext) -> None:
    logger.info(f"/start recibido de {update.message.from_user.id}")
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
        await query.edit_message_text("¡Genial! ¿Sobre qué tema te gustaría publicar en el blog?")
        return TEMA
    elif query.data == "nothing":
        await query.edit_message_text("Está bien, olvídalo.")
        return ConversationHandler.END

# 📌 Estado 1: Recibir tema
async def tema(update: Update, context: CallbackContext) -> int:
    context.user_data["tema"] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Confirmar", callback_data="confirm")],
        [InlineKeyboardButton("Repetir", callback_data="repeat")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Has propuesto el tema: {context.user_data['tema']}. ¿Confirmar?", reply_markup=reply_markup)
    return CONFIRMAR_TEMA

# 📌 Estado 2: Confirmar tema
async def confirmar_tema(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "confirm":
        await query.edit_message_text(f"Generando el post sobre '{context.user_data['tema']}'... ⏳")
        return await generar_post(update, context)
    elif query.data == "repeat":
        await query.edit_message_text("Por favor, proporciona nuevamente el tema del post:")
        return TEMA

# 📌 Estado 3: Generar post con OpenAI
async def generar_post(update: Update, context: CallbackContext) -> int:
    tema = context.user_data.get("tema", "un tema interesante")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente experto en redacción de blogs."},
                      {"role": "user", "content": f"Escribe un post sobre {tema} en 600 palabras"}],
            temperature=0.7,
            max_tokens=1000
        )
        post_generado = response["choices"][0]["message"]["content"]
        await update.effective_message.reply_text(f"✍️ Aquí tienes un post generado:\n\n{post_generado}")
    except Exception as e:
        logger.error(f"❌ Error con OpenAI: {e}")
        await update.effective_message.reply_text("❌ Error generando el post. Inténtalo de nuevo.")
    return ConversationHandler.END

# 📌 Función para cancelar la conversación
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("La conversación ha sido cancelada. Puedes comenzar de nuevo en cualquier momento con /start.")
    return ConversationHandler.END

# 📌 Ruta para ver los logs
@app.route('/logs')
def view_logs():
    try:
        with open(log_file, 'r') as file:
            log_content = file.read()  # Leer todo el contenido del archivo de log
        return f"<pre>{log_content}</pre>", 200  # Mostrar los logs en formato de texto plano
    except FileNotFoundError:
        return "No se encontraron logs disponibles.", 404


# 📌 Configurar manejadores de Telegram
def setup_telegram():
    logger.info("⚙️ Configurando Telegram...")
    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), CallbackQueryHandler(button)],
        states={
            TEMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, tema)],
            CONFIRMAR_TEMA: [CallbackQueryHandler(confirmar_tema)],
            GENERAR_POST: [MessageHandler(filters.TEXT & ~filters.COMMAND, generar_post)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]  # Agregado el comando de cancelación
    )
    application.add_handler(conversation_handler)
    application.add_handler(CommandHandler("cancel", cancel))
    logger.info("✅ Telegram configurado.")

# 📌 Configurar webhook
def set_webhook(url):
    logger.info(f"⚙️ Configurando Webhook en: {url}")
    application.bot.set_webhook(url)
    logger.info("✅ Webhook configurado.")

# 📌 Ruta principal de Flask
@app.route('/')
def home():
    return 'Funcionando correctamente'

# 📌 Ruta para recibir Webhook de Telegram
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    update = Update.de_json(json.loads(json_str), application.bot)
    application.update_queue.put(update)
    return jsonify({'status': 'ok'}), 200

# 📌 Ejecutar Flask y bot de Telegram en hilos diferentes
def run_flask():
    app.run(host="0.0.0.0", port=8080, debug=True, threaded=True)

# Iniciar bot y Flask
if __name__ == "__main__":
    if os.getenv("GAE_ENV", "").startswith("standard"):
        logger.info("🚀 Ejecutando en Google App Engine")
        set_webhook(f"https://{PROJECT_ID}.appspot.com/{TOKEN}")
        run_flask()
    else:
        logger.info("🚀 Ejecutando en local")
        # Instalar y lanzar ngrok automáticamente
        from pyngrok import ngrok
        public_url = ngrok.connect(8080).public_url
        logger.info(f"🌍 ngrok iniciado en: {public_url}")

        # Configurar el webhook con ngrok
        set_webhook(f"{public_url}/{TOKEN}")

        # Ejecutar Flask en un hilo
        threading.Thread(target=run_flask).start()

        # Ejecutar el bot de Telegram (en el hilo principal)
        application.run_polling()
