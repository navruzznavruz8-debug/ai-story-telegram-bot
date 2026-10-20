import os
import io
import time
import math
import random
import logging
import threading
import tempfile

import telebot
from telebot import types
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    concatenate_videoclips,
)

# ==============================
# SOZLAMALAR
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN Render Environment bo'limida topilmadi.")

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# Har bir foydalanuvchining alohida loyihasi
sessions = {}
sessions_lock = threading.RLock()

# Vaqtinchalik fayllarni saqlash joyi
WORK_DIR = tempfile.gettempdir()


def new_session():
    return {
        "story": "",
        "photos": [],
        "waiting": None,
        "music": False,
        "voice": True,
        "busy": False,
    }


def get_session(user_id):
    with sessions_lock:
        if user_id not in sessions:
            sessions[user_id] = new_session()
        return sessions[user_id]


def reset_session(user_id):
    with sessions_lock:
        sessions[user_id] = new_session()


# ==============================
# MENYU
# ==============================

def main_menu():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    markup.add(
        types.KeyboardButton("🧠 AI hikoya"),
        types.KeyboardButton("🖼 Rasmlar"),
        types.KeyboardButton("🎬 Video yaratish"),
        types.KeyboardButton("🎙 Ovoz yaratish"),
        types.KeyboardButton("📋 Loyiha holati"),
        types.KeyboardButton("🆕 Yangi loyiha"),
    )

    return markup


def send_home(chat_id):
    bot.send_message(
        chat_id,
        "🚀 AI Story Studio Pro\n\n"
        "Men hikoya yozish, rasmlarni birlashtirish "
        "va ovozli video tayyorlashga yordam beraman.\n\n"
        "Quyidagi menyudan kerakli bo‘limni tanlang.",
        reply_markup=main_menu()
    )


# ==============================
# /START — YANGI LOYIHA
# ==============================

@bot.message_handler(commands=["start"])
def start(message):
    reset_session(message.from_user.id)
    send_home(message.chat.id)


@bot.message_handler(commands=["help"])
def help_command(message):
    bot.reply_to(
        message,
        "📌 Buyruqlar:\n\n"
        "/start — yangi loyiha\n"
        "/help — yordam\n\n"
        "Avval hikoya yuboring yoki AI hikoya bo‘limini tanlang. "
        "Keyin rasmlarni yuboring va video yarating."
    )


# ==============================
# AI HIKOYA
# ==============================

def create_story(prompt):
    """
    Hozircha bepul, mahalliy hikoya generatori.
    Bu haqiqiy katta til modeli emas.
    Keyinchalik AI API bilan almashtirish mumkin.
    """

    prompt = prompt.strip()

    if not prompt:
        return "Hikoya mavzusini yozing."

    templates = [
        (
            "Bir kuni {topic} bilan bog‘liq g‘aroyib voqea yuz berdi. "
            "Dastlab hech kim bu voqeaning qanchalik muhimligini anglamadi. "
            "Ammo vaqt o‘tishi bilan hammasi o‘zgara boshladi. "
            "Qahramonimiz qiyinchiliklardan qo‘rqmay, haqiqatni izlashga "
            "qaror qildi. Yo‘lda u kutilmagan sinovlarga duch keldi. "
            "Har bir sinov unga yangi saboq berdi. Oxir-oqibat, "
            "u jasorat va ishonch yordamida o‘z maqsadiga erishdi."
        ),
        (
            "{topic} haqidagi voqea oddiy bir kundan boshlandi. "
            "Qahramonimiz oldida katta imkoniyat paydo bo‘ldi, "
            "lekin bu imkoniyat osonlik bilan qo‘lga kiritilmasdi. "
            "U reja tuzdi, xatolaridan saboq oldi va harakat qilishda "
            "davom etdi. Kutilmagan uchrashuv uning fikrlarini o‘zgartirdi. "
            "Shunda u eng muhim narsa sabr, bilim va qat’iyat ekanini "
            "tushundi. Voqea esa unutilmas yakun bilan tugadi."
        ),
    ]

    return random.choice(templates).format(topic=prompt)


@bot.message_handler(
    func=lambda m: m.text == "🧠 AI hikoya"
)
def story_button(message):
    get_session(message.from_user.id)["waiting"] = "story"

    bot.send_message(
        message.chat.id,
        "🧠 Hikoya mavzusini yozing.\n\n"
        "Masalan: kelajakdagi shahar, do‘stlik, sarguzasht."
    )


@bot.message_handler(
    func=lambda m: m.text == "🖼 Rasmlar"
)
def photos_button(message):
    session = get_session(message.from_user.id)

    bot.send_message(
        message.chat.id,
        f"🖼 Hozirgi loyihada {len(session['photos'])} ta rasm bor.\n\n"
        "Yangi rasmlarni shu chatga yuboring. "
        "Ular faqat joriy loyihaga qo‘shiladi."
    )


@bot.message_handler(
    func=lambda m: m.text == "📋 Loyiha holati"
)
def status_button(message):
    session = get_session(message.from_user.id)

    story = session["story"]
    story_status = "Bor ✅" if story else "Yo‘q"

    bot.send_message(
        message.chat.id,
        "📋 LOYIHA HOLATI\n\n"
        f"📖 Hikoya: {story_status}\n"
        f"🖼 Rasmlar: {len(session['photos'])} ta\n"
        f"🎙 Ovoz: {'Yoqilgan' if session['voice'] else 'O‘chirilgan'}\n"
        f"🎵 Musiqa: {'Yoqilgan' if session['music'] else 'O‘chirilgan'}"
    )


@bot.message_handler(
    func=lambda m: m.text == "🆕 Yangi loyiha"
)
def new_project_button(message):
    reset_session(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "🆕 Yangi loyiha yaratildi!\n"
        "Eski hikoya va rasmlar yangi loyihaga qo‘shilmaydi.",
        reply_markup=main_menu()
    )


# ==============================
# HIKOYA VA MATN QABUL QILISH
# ==============================

@bot.message_handler(
    content_types=["text"],
    func=lambda m: bool(
        m.text
        and not m.text.startswith("/")
        and m.text not in [
            "🧠 AI hikoya",
            "🖼 Rasmlar",
            "🎬 Video yaratish",
            "🎙 Ovoz yaratish",
            "📋 Loyiha holati",
            "🆕 Yangi loyiha",
        ]
    )
)
def receive_text(message):
    user_id = message.from_user.id
    session = get_session(user_id)

    waiting = session["waiting"]

    if waiting == "story":
        story = create_story(message.text)
        session["story"] = story
        session["waiting"] = None

        bot.send_message(
            message.chat.id,
            "📖 Hikoya tayyor!\n\n" + story,
            reply_markup=main_menu()
        )
        return

    # Oddiy yuborilgan matnni hikoya sifatida saqlash
    session["story"] = message.text.strip()
    session["waiting"] = None

    bot.send_message(
        message.chat.id,
        "📖 Matn hikoya sifatida saqlandi!\n"
        "Endi rasmlarni yuborishingiz mumkin.",
        reply_markup=main_menu()
    )


# ==============================
# RASMLARNI QABUL QILISH
# ==============================

@bot.message_handler(content_types=["photo"])
def receive_photo(message):
    user_id = message.from_user.id
    session = get_session(user_id)

    if session["busy"]:
        bot.reply_to(
            message,
            "⏳ Hozir video tayyorlanmoqda. Biroz kuting."
        )
        return

    try:
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        downloaded = bot.download_file(file_info.file_path)

        filename = os.path.join(
            WORK_DIR,
            f"story_{user_id}_{time.time_ns()}.jpg"
        )

        with open(filename, "wb") as file:
            file.write(downloaded)

        # Rasm joriy foydalanuvchining loyihasiga qo‘shiladi
        session["photos"].append(filename)

        bot.reply_to(
            message,
            f"✅ Rasm saqlandi!\n"
            f"Joriy loyihadagi rasmlar: {len(session['photos'])} ta."
        )

    except Exception:
        logging.exception("Rasmni yuklashda xatolik")
        bot.reply_to(
            message,
            "❌ Rasmni saqlashda xatolik yuz berdi. Qayta yuboring."
        )


# ==============================
# VIDEO YARATISH
# ==============================

def create_video(story, photo_paths, add_voice):
    """
    Rasmlardan MP4 video yaratadi.
    Agar ovoz yoqilgan bo‘lsa, hikoya TTS orqali o‘qiladi.
    """

    if not photo_paths:
        raise ValueError("Avval kamida bitta rasm yuboring.")

    temp_files = []
    clips = []
    audio_clip = None
    final_clip = None

    try:
        # Rasmlarni bir xil o‘lchamga tayyorlash
        prepared_images = []

        for path in photo_paths:
            with Image.open(path) as img:
                img = img.convert("RGB")
                img.thumbnail((1280, 720))

                background = Image.new(
                    "RGB",
                    (1280, 720),
                    (15, 15, 25)
                )

                x = (1280 - img.width) // 2
                y = (720 - img.height) // 2

                background.paste(img, (x, y))

                prepared = os.path.join(
                    WORK_DIR,
                    f"prepared_{time.time_ns()}.jpg"
                )

                background.save(prepared, quality=90)
                temp_files.append(prepared)
                prepared_images.append(prepared)

        # Har bir rasm taxminan 3 soniya ko‘rsatiladi
        for path in prepared_images:
            clip = ImageClip(path).set_duration(3)
            clips.append(clip)

        final_clip = concatenate_videoclips(
            clips,
            method="compose"
        )

        # Hikoyani ovozga aylantirish
        if add_voice and story.strip():
            voice_path = os.path.join(
                WORK_DIR,
                f"voice_{time.time_ns()}.mp3"
            )

            tts = gTTS(text=story[:4000], lang="uz")
            tts.save(voice_path)
            temp_files.append(voice_path)

            audio_clip = AudioFileClip(voice_path)

            # Video ovozdan qisqa bo‘lsa, oxirgi kadrni ushlab turish
            if audio_clip.duration > final_clip.duration:
                extra = audio_clip.duration - final_clip.duration

                last_frame = ImageClip(
                    prepared_images[-1]
                ).set_duration(extra)

                clips.append(last_frame)

                final_clip.close()
                final_clip = concatenate_videoclips(
                    clips,
                    method="compose"
                )

            final_clip = final_clip.set_audio(audio_clip)

        output_path = os.path.join(
            WORK_DIR,
            f"video_{time.time_ns()}.mp4"
        )

        final_clip.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            preset="ultrafast"
        )

        return output_path

    finally:
        if audio_clip:
            try:
                audio_clip.close()
            except Exception:
                pass

        if final_clip:
            try:
                final_clip.close()
            except Exception:
                pass

        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

        for path in temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass


def generate_video_for_user(chat_id, user_id):
    session = get_session(user_id)

    if session["busy"]:
        bot.send_message(chat_id, "⏳ Video allaqachon tayyorlanmoqda.")
        return

    if not session["photos"]:
        bot.send_message(
            chat_id,
            "🖼 Avval video uchun rasmlar yuboring."
        )
        return

    session["busy"] = True

    try:
        bot.send_message(
            chat_id,
            "🎬 Video tayyorlanmoqda. Iltimos, kuting..."
        )

        output = create_video(
            session["story"],
            list(session["photos"]),
            session["voice"]
        )

        with open(output, "rb") as video_file:
            bot.send_video(
                chat_id,
                video_file,
                caption="🎬 Videongiz tayyor!"
            )

        try:
            os.remove(output)
        except OSError:
            pass

    except Exception:
        logging.exception("Video yaratishda xatolik")

        bot.send_message(
            chat_id,
            "❌ Video yaratishda xatolik yuz berdi.\n"
            "Rasmlarni tekshiring va qayta urinib ko‘ring."
        )

    finally:
        session["busy"] = False


@bot.message_handler(
    func=lambda m: m.text == "🎬 Video yaratish"
)
def video_button(message):
    generate_video_for_user(
        message.chat.id,
        message.from_user.id
    )


# ==============================
# OVOZ YARATISH
# ==============================

@bot.message_handler(
    func=lambda m: m.text == "🎙 Ovoz yaratish"
)
def voice_button(message):
    user_id = message.from_user.id
    session = get_session(user_id)

    if not session["story"]:
        bot.send_message(
            message.chat.id,
            "📖 Avval hikoya yuboring yoki yarating."
        )
        return

    try:
        voice_path = os.path.join(
            WORK_DIR,
            f"voice_only_{time.time_ns()}.mp3"
        )

        gTTS(
            text=session["story"][:4000],
            lang="uz"
        ).save(voice_path)

        with open(voice_path, "rb") as voice_file:
            bot.send_audio(
                message.chat.id,
                voice_file,
                title="Hikoya ovozi"
            )

        os.remove(voice_path)

    except Exception:
        logging.exception("Ovoz yaratishda xatolik")

        bot.send_message(
            message.chat.id,
            "❌ Ovoz yaratilmadi. Internet aloqasini tekshiring."
        )


# ==============================
# BOTNI ISHGA TUSHIRISH
# ==============================

if __name__ == "__main__":
    logging.info("AIStoryStudioProBot ishga tushmoqda...")

    while True:
        try:
            bot.infinity_polling(
                skip_pending=True,
                timeout=30,
                long_polling_timeout=30
            )
        except Exception:
            logging.exception("Bot polling xatosi")
            time.sleep(5)
