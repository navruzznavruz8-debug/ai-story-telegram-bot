import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import telebot

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AI Hikoya bot ishlayapti!")

    def log_message(self, *args):
        pass

def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "Salom! AI Hikoya botiga xush kelibsiz!\n\n"
        "1. Avval hikoyangiz matnini yuboring.\n"
        "2. Keyin rasmlaringizni yuboring.\n\n"
        "Hozir botni ishga tushirishni sozlayapmiz."
    )

@bot.message_handler(content_types=["text"])
def story(message):
    bot.reply_to(
        message,
        "Hikoyangiz qabul qilindi! Keyingi bosqichda "
        "rasmlar bilan ishlashni sozlaymiz."
    )

@bot.message_handler(content_types=["photo"])
def photo(message):
    bot.reply_to(message, "Rasmingiz qabul qilindi!")

threading.Thread(target=start_server, daemon=True).start()
bot.infinity_polling()
