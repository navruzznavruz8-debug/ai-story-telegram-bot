import os
import telebot

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "Salom! AI Hikoya botiga xush kelibsiz!\n"
        "Avval hikoyangiz matnini yuboring, "
        "keyin rasmlaringizni yuborishingiz mumkin."
    )

@bot.message_handler(content_types=["text"])
def story(message):
    bot.reply_to(
        message,
        "Hikoyangiz qabul qilindi!\n"
        "Video yaratish funksiyalarini keyingi bosqichda ulaymiz."
    )

bot.infinity_polling()
