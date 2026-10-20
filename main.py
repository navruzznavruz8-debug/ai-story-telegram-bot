import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import telebot

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)


# Server holatini tekshirish
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


# /start buyrug'i
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "Salom! AI Hikoya botiga xush kelibsiz!\n\n"
        "1. Avval hikoyangiz matnini yuboring.\n"
        "2. Keyin rasmlaringizni yuboring.\n"
        "3. Video funksiyasi uchun /video buyrug'ini yuboring."
    )


# /video buyrug'i
@bot.message_handler(commands=["video"])
def video(message):
    bot.reply_to(
        message,
        "Video tayyorlash funksiyasini hozir sozlayapmiz! 🎬"
    )


# Rasm qabul qilish
@bot.message_handler(content_types=["photo"])
def photo(message):
    bot.reply_to(message, "Rasmingiz qabul qilindi! 🖼")


# Matn qabul qilish
@bot.message_handler(content_types=["text"])
def story(message):
    bot.reply_to(
        message,
        "Hikoyangiz qabul qilindi! 📖"
    )


# Serverni ishga tushirish
threading.Thread(target=start_server, daemon=True).start()

# Botni ishga tushirish
bot.infinity_polling()
