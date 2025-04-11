from telegram.ext import (
    ConversationHandler, MessageHandler, Filters, CallbackQueryHandler
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from bot.states import MODELO, TEMA, PROPUESTA, SUGERENCIAS
from core.content import generate_content_with_model, apply_suggestions
from core.wordpress import publish_to_wordpress
from bot.utils import animated_loading, diff_highlight
import telegram

user_posts = {}

def start(update, context):
    keyboard = [
        [InlineKeyboardButton("GPT-3.5 Turbo 💸 Muy barato", callback_data="gpt-3.5-turbo")],
        [InlineKeyboardButton("GPT-3.5 Instruct 💵 Barato", callback_data="gpt-3.5-turbo-instruct")],
        [InlineKeyboardButton("GPT-4 💰 Caro", callback_data="gpt-4")],
        [InlineKeyboardButton("GPT-4 Turbo 💎 Muy caro", callback_data="gpt-4-turbo")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("👋 ¡Hola! ¿Con qué modelo de OpenAI quieres trabajar?", reply_markup=reply_markup)
    return MODELO

def seleccionar_modelo(update, context):
    query = update.callback_query
    query.answer()
    model = query.data
    context.user_data['modelo'] = model
    query.edit_message_text(f"✅ Modelo seleccionado: {model}\n\n🧠 Ahora dime el tema del post.")
    return TEMA

def handle_message(update, context):
    user_id = update.effective_user.id
    tema = update.message.text.strip()
    model = context.user_data.get("modelo", "gpt-3.5-turbo")
    loading_msg = update.message.reply_text("⏳ Generando.")
    stop_flag = animated_loading(loading_msg)
    title, content = generate_content_with_model(tema, model)
    stop_flag.set()
    user_posts[user_id] = {"title": title, "content": content, "tema": tema}
    update.message.reply_text(
        f"📝 <b>{title}</b>\n\n{content}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Rehacer propuesta", callback_data="rehacer")],
            [InlineKeyboardButton("✏️ Sugerir cambios", callback_data="cambios")],
            [InlineKeyboardButton("🆕 Cambiar tema", callback_data="cambiar")],
            [InlineKeyboardButton("✅ Publicar", callback_data="publicar")]
        ])
    )
    return PROPUESTA

def button_callback(update, context):
    # Igual que antes, moveríamos toda esta lógica como está a funciones internas aquí.
    pass

def handle_sugerencias(update, context):
    # Igual que antes, podríamos importar la lógica desde core.content
    pass

conv_handler = ConversationHandler(
    entry_points=[MessageHandler(Filters.command, start)],
    states={
        MODELO: [CallbackQueryHandler(seleccionar_modelo)],
        TEMA: [MessageHandler(Filters.text & ~Filters.command, handle_message)],
        PROPUESTA: [CallbackQueryHandler(button_callback)],
        SUGERENCIAS: [MessageHandler(Filters.text & ~Filters.command, handle_sugerencias)],
    },
    fallbacks=[MessageHandler(Filters.command, start)]
)
