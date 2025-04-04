import logging
import os
import json
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler
import openai

# 🔑 Variables de entorno
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

# ✅ Configurar OpenAI
openai.api_key = OPENAI_API_KEY

# ✅ Configurar Flask
app = Flask(__name__)

# ✅ Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 🔄 Estados de conversación
TEMA, CONFIRMAR_TEMA, GENERAR_POST = range(3)

# ✅ Iniciar bot
application = Application.builder().token(TOKEN).build()

# 📌 Comando /start
async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("Publicar post en blog", callback_data="publish_blog")],
        [InlineKeyboardButton("Nada, olvídalo", callback_data="nothing")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Selecciona una opción:", reply_markup=reply_markup)

# 📌 Manejo de botones
async def button(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "publish_blog":
        await query.edit_message_text("¡Genial! ¿Sobre qué tema te gustaría publicar en el blog?")
        return TEMA
    elif query.data == "nothing":
        await query.edit_message_text("Está bien, olvídalo.")
        return ConversationHandler.END

# 📌 Estado 1: Recibir tema
async def tema(update: Update, context):
    context.user_data["tema"] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Confirmar", callback_data="confirm")],
        [InlineKeyboardButton("Repetir", callback_data="repeat")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Has propuesto el tema: {context.user_data['tema']}. ¿Confirmar?", reply_markup=reply_markup)
    return CONFIRMAR_TEMA

# 📌 Estado 2: Confirmar tema
async def confirmar_tema(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm":
        await query.edit_message_text(f"Generando el post sobre '{context.user_data['tema']}'... ⏳")
        return await generar_post(update, context)
    elif query.data == "repeat":
        await query.edit_message_text("Por favor, proporciona nuevamente el tema del post:")
        return TEMA

# 📌 Estado 3: Generar post con OpenAI
async def generar_post(update: Update, context):
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
async def cancel(update: Update, context):
    await update.message.reply_text("La conversación ha sido cancelada. Puedes comenzar de nuevo en cualquier momento con /start.")
    return ConversationHandler.END

# 📌 Configurar manejadores de Telegram
def setup_telegram():
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

# 📌 Configurar webhook
def set_webhook(url):
    application.bot.set_webhook(url)

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

# Ahora no ejecutamos Flask directamente, sino con Gunicorn
# Este bloque solo debe ejecutarse si el script se corre directamente (no cuando se usa Gunicorn)
if __name__ == "__main__":
    if os.getenv("GAE_ENV", "").startswith("standard"):
        set_webhook(f"https://{PROJECT_ID}.appspot.com/{TOKEN}")
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 8080)))
    else:
        # Usar ngrok solo si estás corriendo localmente
        from pyngrok import ngrok
        public_url = ngrok.connect(8080).public_url
        set_webhook(f"{public_url}/{TOKEN}")
        app.run(host="0.0.0.0", port=8080)


