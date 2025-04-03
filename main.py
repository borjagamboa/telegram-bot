import os
import logging
from flask import Flask, request, jsonify
import openai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler, ConversationHandler
from threading import Thread

# Configurar OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Configurar Flask
app = Flask(__name__)

# Configurar logging
log_file = '/tmp/app.log'  # Ruta de archivo en Google Cloud (usualmente en /tmp)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    handlers=[logging.StreamHandler(), logging.FileHandler(log_file)]
)
logger = logging.getLogger(__name__)

# Estados de la conversación
TEMA, CONFIRMAR_TEMA, GENERAR_POST = range(3)

# Crear instancia del bot
TOKEN = os.getenv("TELEGRAM_TOKEN")
application = Application.builder().token(TOKEN).build()

logger.info("La aplicación de Telegram ha sido inicializada.")

# Comando /start
async def start(update: Update, context: CallbackContext) -> None:
    logger.info(f"🚀 /start recibido de {update.message.from_user.first_name} ({update.message.from_user.id})")
    await update.message.reply_text("¡Hola! ¿Cómo puedo ayudarte?")

    keyboard = [
        [InlineKeyboardButton("Publicar post en blog", callback_data="publish_blog")],
        [InlineKeyboardButton("Nada, olvídalo", callback_data="nothing")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Selecciona una opción:", reply_markup=reply_markup)

# Manejo de botones
async def button(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "publish_blog":
        await query.edit_message_text(text="¡Genial! ¿Sobre qué tema te gustaría publicar en el blog?")
        return TEMA

    elif query.data == "nothing":
        await query.edit_message_text(text="Está bien, olvídalo.")
        return ConversationHandler.END

# Estado 1: Recibir el tema
async def tema(update: Update, context: CallbackContext) -> int:
    context.user_data["tema"] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Confirmar", callback_data="confirm")],
        [InlineKeyboardButton("Repetir", callback_data="repeat")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Has propuesto el tema: {context.user_data['tema']}. ¿Confirmar?", reply_markup=reply_markup)
    return CONFIRMAR_TEMA

# Estado 2: Confirmar o repetir el tema
async def confirmar_tema(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "confirm":
        await query.edit_message_text(f"¡Perfecto! Generando el post sobre '{context.user_data['tema']}'... ⏳")
        return await generar_post(update, context)

    elif query.data == "repeat":
        await query.edit_message_text(text="Por favor, proporciona nuevamente el tema del post:")
        return TEMA

# Estado 3: Generar post con OpenAI
async def generar_post(update: Update, context: CallbackContext) -> int:
    tema = context.user_data.get("tema", "un tema interesante")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente experto en redacción de blogs."},
                      {"role": "user", "content": f"Escribe un post sobre {tema}. Que tenga unas 600 palabras"}],
            temperature=0.7,
            max_tokens=1000
        )

        post_generado = response.choices[0].message['content']
        await update.effective_message.reply_text(f"✍️ Aquí tienes un post generado:\n\n{post_generado}")

    except Exception as e:
        await update.effective_message.reply_text("❌ Error generando el post. Inténtalo de nuevo.")
        logger.error(f"Error con OpenAI: {e}")

    return ConversationHandler.END

# Cancelar conversación
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("La conversación ha sido cancelada. Escribe /start para comenzar de nuevo.")
    return ConversationHandler.END

# Configuración del manejador de Telegram
def setup_telegram():
    logger.info("Configurando Telegram.")
    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), CallbackQueryHandler(button)],
        states={TEMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, tema)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conversation_handler)
    logger.info("Telegram configurado correctamente.")

# Webhook
def set_webhook():
    logger.info("Configurando Webhook.")
    webhook_url = f"https://{os.getenv('GOOGLE_CLOUD_PROJECT')}.appspot.com/{TOKEN}"
    application.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook configurado en: {webhook_url}")

# Ejecutar Flask en un hilo separado
def run_flask():
    app.run(host="0.0.0.0", port=8080, debug=True)

@app.route('/')
def home():
    return 'Funcionando correctamente'

# Ruta de Webhook en Flask
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    logger.info(f"📩 Datos recibidos en webhook: {json_str}")
    json_data = json.loads(json_str)
    update = Update.de_json(json_data, application.bot)
    application.update_queue.put(update)
    return jsonify({'status': 'ok'}), 200

# Configurar y ejecutar el bot
setup_telegram()
set_webhook()

# Ejecutar Flask en un hilo separado
from threading import Thread
flask_thread = Thread(target=run_flask)
flask_thread.start()

# Iniciar el bot de Telegram
application.run_polling()

