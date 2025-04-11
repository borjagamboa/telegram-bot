from flask import Flask, request
import telegram
from telegram.ext import Dispatcher
from bot.handlers import conv_handler
from config.secrets import get_config

app = Flask(__name__)

# Carga de credenciales y objetos globales
telegram_token, wp_url, wp_user, wp_password, openai_api_key = get_config()
bot = telegram.Bot(token=telegram_token)
dispatcher = Dispatcher(bot, None, workers=0)
dispatcher.add_handler(conv_handler)

@app.route('/webhook', methods=['POST'])
def webhook():
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
    app.run(host='0.0.0.0', port=8080)
