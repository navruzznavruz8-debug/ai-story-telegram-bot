import os
import io
import json
import time
import uuid
import shutil
import logging
import tempfile
import threading
import subprocess

from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

import telebot
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
    CompositeAudioClip,
)

# ==============================
# SOZLAMALAR
# ==============================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN sozlanmagan!")

bot = telebot.TeleBot(TOKEN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AI_VIDEO_AGENT")

BASE_DIR = Path(tempfile.gettempdir()) / "ai_video_agent"
BASE_DIR.mkdir(parents=True, exist_ok=True)

VIDEO_WIDTH = 720
VIDEO_HEIGHT = 1280
FPS = 24

user_sessions = {}
user_locks = {}
session_lock = threading.Lock()


# ==============================
# HEALTH CHECK SERVER
# ==============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AI Video Agent ishlayapti!")

    def log_message(self, *args):
        pass


def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


# ==============================
# FOYDALANUVCHI SESSIYASI
# ==============================

def get_session(user_id):
    with session_lock:
        if user_id not in user_sessions:
            user_sessions[user_id] = {
                "story": "",
                "photos": [],
                "busy": False,
            }

        if user_id not in user_locks:
            user_locks[user_id] = threading.Lock()

        return user_sessions[user_id]


# ==============================
# MATNNI SAHNALARGA AJRATISH
# ==============================

def split_story(text):
    text = " ".join(text.split())

    sentences = []
    current = ""

    for char in text:
        current += char

        if char in ".!?":
            if current.strip():
                sentences.append(current.strip())
            current = ""

    if current.strip():
        sentences.append(current.strip())

    # Har bir sahnada bir yoki bir nechta jumla.
    scenes = []
    chunk_size = 2

    for i in range(0, len(sentences), chunk_size):
        scenes.append(" ".join(sentences[i:i + chunk_size]))

    return scenes or [text]


# ==============================
# RASMLARNI TAYYORLASH
# ==============================

def prepare_image(source, output_path):
    """
    Rasmni vertikal video formatiga moslaydi.
    Asl rasm faylini o'zgartirmaydi.
    """
    with Image.open(source) as original:
        image = original.convert("RGB")

        ratio = max(
            VIDEO_WIDTH / image.width,
            VIDEO_HEIGHT / image.height
        )

        new_size = (
            int(image.width * ratio),
            int(image.height * ratio)
        )

        image = image.resize(new_size, Image.Resampling.LANCZOS)

        left = (image.width - VIDEO_WIDTH) // 2
        top = (image.height - VIDEO_HEIGHT) // 2

        image = image.crop((
            left,
            top,
            left + VIDEO_WIDTH,
            top + VIDEO_HEIGHT
        ))

        image.save(output_path, quality=94)


def make_placeholder(scene_text, output_path):
    """
    Foydalanuvchi rasm yubormagan sahna uchun
    matnli vaqtinchalik fon yaratadi.
    Bu AI yaratgan rasm emas.
    """
    image = Image.new(
        "RGB",
        (VIDEO_WIDTH, VIDEO_HEIGHT),
        (24, 28, 42)
    )

    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            34
        )
    except OSError:
        font = ImageFont.load_default()

    words = scene_text.split()
    lines = []
    line = ""

    for word in words:
        candidate = (line + " " + word).strip()

        if draw.textbbox((0, 0), candidate, font=font)[2] > 600:
            if line:
                lines.append(line)
            line = word
        else:
            line = candidate

    if line:
        lines.append(line)

    y = VIDEO_HEIGHT // 2 - len(lines) * 24

    for line in lines:
        draw.text(
            (60, y),
            line,
            font=font,
            fill="white"
        )
        y += 55

    image.save(output_path)


# ==============================
# OVOZ YARATISH
# ==============================

def create_narration(text, output_path):
    """
    gTTS internet orqali matnni ovozga aylantiradi.
    """
    tts = gTTS(text=text, lang="uz", slow=False)
    tts.save(str(output_path))


# ==============================
# SUBTITRLI SAHNA
# ==============================

def make_subtitle(text, output_path):
    image = Image.new(
        "RGBA",
        (VIDEO_WIDTH, 180),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            27
        )
    except OSError:
        font = ImageFont.load_default()

    # Uzun matnni bir necha qatorga ajratish.
    words = text.split()
    lines = []
    line = ""

    for word in words:
        candidate = (line + " " + word).strip()

        if draw.textbbox((0, 0), candidate, font=font)[2] > 640:
            if line:
                lines.append(line)
            line = word
        else:
            line = candidate

    if line:
        lines.append(line)

    lines = lines[:3]
    line_height = 38
    y = (180 - len(lines) * line_height) // 2

    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        width = box[2] - box[0]
        x = (VIDEO_WIDTH - width) // 2

        draw.text(
            (x + 2, y + 2),
            line,
            font=font,
            fill=(0, 0, 0, 230),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 230)
        )

        draw.text(
            (x, y),
            line,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=1,
            stroke_fill=(0, 0, 0, 255)
        )

        y += line_height

    image.save(output_path)


# ==============================
# VIDEO MONTAJ
# ==============================

def create_video(story, photos, output_path, workdir):
    scenes = split_story(story)

    if not scenes:
        raise ValueError("Hikoya matni bo'sh!")

    clips = []
    audio_clips = []
    subtitle_clips = []
    current_time = 0.0

    try:
        for index, scene in enumerate(scenes):
            audio_path = workdir / f"audio_{index}.mp3"
            image_path = workdir / f"scene_{index}.jpg"
            subtitle_path = workdir / f"subtitle_{index}.png"

            # Har bir sahna uchun ovoz.
            create_narration(scene, audio_path)

            audio = AudioFileClip(str(audio_path))
            duration = max(audio.duration, 0.5)

            # Mavjud rasmlardan navbat bilan foydalanish.
            if photos:
                photo_path = photos[index % len(photos)]
                prepare_image(photo_path, image_path)
            else:
                make_placeholder(scene, image_path)

            # Ken Burns uslubidagi sekin zoom.
            clip = (
                ImageClip(str(image_path))
                .set_duration(duration)
                .resize(lambda t: 1.0 + 0.035 * t / max(duration, 0.1))
                .set_position("center")
            )

            # O'lcham kattalashganda ekranni to'ldirish.
            clip = clip.crop(
                x_center=clip.w / 2,
                y_center=clip.h / 2,
                width=VIDEO_WIDTH,
                height=VIDEO_HEIGHT
            )

            clip = clip.set_audio(audio)

            clips.append(clip)
            audio_clips.append(audio)

            # Subtitrni sahna davomida ko'rsatish.
            make_subtitle(scene, subtitle_path)

            subtitle = (
                ImageClip(str(subtitle_path))
                .set_duration(duration)
                .set_position(
                    ("center", VIDEO_HEIGHT - 240)
                )
                .set_start(current_time)
            )

            subtitle_clips.append(subtitle)
            current_time += duration

        # Sahna almashinuvi uchun yumshoq fade.
        final_clips = []

        for index, clip in enumerate(clips):
            if index > 0:
                clip = clip.crossfadein(0.35)
            final_clips.append(clip)

        base = concatenate_videoclips(
            final_clips,
            method="compose",
            padding=-0.35 if len(final_clips) > 1 else 0
        )

        subtitles = CompositeVideoClip(
            [base] + subtitle_clips,
            size=(VIDEO_WIDTH, VIDEO_HEIGHT)
        )

        subtitles = subtitles.set_audio(base.audio)

        subtitles.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            threads=2,
            logger=None
        )

        subtitles.close()
        base.close()

    finally:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

        for audio in audio_clips:
            try:
                audio.close()
            except Exception:
                pass


# ==============================
# VIDEO ISHINI FONDA BAJARISH
# ==============================

def render_job(message, user_id):
    session = get_session(user_id)
    workdir = BASE_DIR / f"{user_id}_{uuid.uuid4().hex[:8]}"
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        story = session["story"]
        photos = list(session["photos"])

        if not story.strip():
            bot.send_message(
                user_id,
                "Avval hikoya matnini yuboring."
            )
            return

        bot.send_message(
            user_id,
            "🎬 Hikoya tahlil qilinmoqda va video tayyorlanmoqda. "
            "Iltimos, kuting..."
        )

        output_path = workdir / "final_video.mp4"

        create_video(
            story=story,
            photos=photos,
            output_path=output_path,
            workdir=workdir
        )

        with open(output_path, "rb") as video_file:
            bot.send_video(
                user_id,
                video_file,
                caption="🎬 Video tayyor!"
            )

    except Exception:
        logger.exception("Video yaratishda xato")

        bot.send_message(
            user_id,
            "Video yaratishda xato yuz berdi. "
            "Hikoya qisqaroq ekanini tekshirib, qayta urinib ko'ring."
        )

    finally:
        with session_lock:
            session["busy"] = False

        shutil.rmtree(workdir, ignore_errors=True)


# ==============================
# TELEGRAM BUYRUQLARI
# ==============================

@bot.message_handler(commands=["start"])
def start(message):
    get_session(message.from_user.id)

    bot.reply_to(
        message,
        "🎬 AI Video Agentga xush kelibsiz!\n\n"
        "1. Hikoya matnini yuboring.\n"
        "2. Hikoyaga mos rasmlarni yuboring.\n"
        "3. /video buyrug'ini yuboring.\n\n"
        "Bot ovozli, subtitrli video yaratadi.\n"
        "Rasm yuborilmasa, vaqtinchalik matnli fon ishlatiladi."
    )


@bot.message_handler(commands=["video"])
def video(message):
    user_id = message.from_user.id
    session = get_session(user_id)

    with session_lock:
        if session["busy"]:
            bot.reply_to(
                message,
                "⏳ Videongiz tayyorlanmoqda. Iltimos, kuting."
            )
            return

        if not session["story"].strip():
            bot.reply_to(
                message,
                "Avval hikoyangizni matn ko'rinishida yuboring."
            )
            return

        session["busy"] = True

    threading.Thread(
        target=render_job,
        args=(message, user_id),
        daemon=True
    ).start()


@bot.message_handler(content_types=["text"])
def story(message):
    user_id = message.from_user.id
    session = get_session(user_id)

    if message.text.startswith("/"):
        return

    session["story"] = message.text.strip()

    bot.reply_to(
        message,
        "📖 Hikoyangiz qabul qilindi!\n\n"
        "Endi istasangiz, rasmlarni yuboring.\n"
        "Tayyor bo'lgach /video buyrug'ini bosing."
    )


@bot.message_handler(content_types=["photo"])
def photo(message):
    user_id = message.from_user.id
    session = get_session(user_id)

    try:
        file_info = bot.get_file(
            message.photo[-1].file_id
        )

        downloaded = bot.download_file(
            file_info.file_path
        )

        image_path = BASE_DIR / (
            f"{user_id}_{uuid.uuid4().hex[:10]}.jpg"
        )

        with open(image_path, "wb") as image_file:
            image_file.write(downloaded)

        session["photos"].append(str(image_path))

        bot.reply_to(
            message,
            f"🖼 Rasm qabul qilindi! "
            f"Jami rasmlar: {len(session['photos'])}"
        )

    except Exception:
        logger.exception("Rasm yuklashda xato")

        bot.reply_to(
            message,
            "Rasmni qabul qilishda xato yuz berdi."
        )


# ==============================
# ISHGA TUSHIRISH
# ==============================

threading.Thread(
    target=start_server,
    daemon=True
).start()

bot.infinity_polling()
