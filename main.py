import os
import telebot

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "Salom! 🎬 AI Story Studio botiga xush kelibsiz!\n\n"
        "Menga hikoyangizni va rasmlaringizni yuboring.\n"
        "Hozircha bot sozlanmoqda."
    )

@bot.message_handler(content_types=["text"])
def story(message):
    bot.reply_to(
        message,
        "📖 Hikoyangiz qabul qilindi!\n"
        "Rasmlarni ham yuborishingiz mumkin."
    )

bot.infinity_polling()
