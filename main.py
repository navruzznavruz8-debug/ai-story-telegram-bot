"""
Telegram AI Video Bot
Mavzu -> hikoya (Claude) -> rasm (Pollinations) -> ovoz (edge-tts) -> video (ffmpeg)
"""
import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

import aiohttp
import edge_tts
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("storybot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
SCENES = int(os.getenv("SCENES", "5"))
WIDTH, HEIGHT = 720, 1280  # 9:16 (Telegram/Reels/Shorts uchun)
FPS = 25

LANGS = {
    "uz": {"name": "Uzbek (Latin script)", "voice": "uz-UZ-MadinaNeural"},
    "ru": {"name": "Russian", "voice": "ru-RU-SvetlanaNeural"},
    "en": {"name": "English", "voice": "en-US-AriaNeural"},
}
user_lang: dict[int, str] = {}

claude = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
dp = Dispatcher()
job_limit = asyncio.Semaphore(2)  # bir vaqtda 2 ta video


# ---------- 1. HIKOYA ----------
async def make_story(topic: str, lang: str) -> dict:
    prompt = f"""Write a short, engaging story for a video about: "{topic}".
Split it into exactly {SCENES} scenes. Each scene's narration should be 1-3 sentences.
Narration language: {LANGS[lang]['name']}.
For each scene also write "image_prompt": a vivid visual description IN ENGLISH
(consistent characters and art style across scenes, no text in the image).

Reply with ONLY valid JSON, no other text:
{{"title": "...", "scenes": [{{"narration": "...", "image_prompt": "..."}}]}}"""
    resp = await claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text
    match = re.search(r"\{.*\}", text, re.S)
    data = json.loads(match.group(0))
    if not data.get("scenes"):
        raise ValueError("Hikoya bo'sh qaytdi")
    return data


# ---------- 2. RASM ----------
async def make_image(session: aiohttp.ClientSession, prompt: str, path: Path, seed: int):
    url = (
        f"https://image.pollinations.ai/prompt/{quote(prompt)}"
        f"?width={WIDTH}&height={HEIGHT}&nologo=true&seed={seed}"
    )
    for attempt in range(3):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as r:
                if r.status == 200:
                    path.write_bytes(await r.read())
                    return
                log.warning("Rasm xato %s (urinish %s)", r.status, attempt + 1)
        except Exception as e:  # noqa: BLE001
            log.warning("Rasm xatosi: %s", e)
        await asyncio.sleep(3)
    raise RuntimeError("Rasm yaratib bo'lmadi")


# ---------- 3. OVOZ ----------
async def make_voice(text: str, voice: str, path: Path):
    await edge_tts.Communicate(text, voice).save(str(path))


# ---------- 4. MONTAJ ----------
def audio_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def build_scene_clip(img: Path, audio: Path, out: Path):
    dur = audio_duration(audio) + 0.4
    frames = int(dur * FPS)
    vf = (
        f"scale={WIDTH * 2}:{HEIGHT * 2}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='min(zoom+0.0007,1.25)':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS},"
        "format=yuv420p"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(img), "-i", str(audio),
         "-vf", vf, "-af", "apad", "-t", f"{dur:.2f}",
         "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
         "-ar", "44100", "-ac", "2", str(out)],
        capture_output=True, check=True,
    )


def concat_clips(clips: list[Path], out: Path, workdir: Path):
    lst = workdir / "list.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(out)],
        capture_output=True, check=True,
    )


# ---------- BOT ----------
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "Salom! Menga mavzu yozing, men hikoya, rasm va ovozni birlashtirib video qilib beraman.\n\n"
        "Masalan: Uzoq orolda yashagan kichkina robot\n\n"
        "Til: /lang uz | ru | en (hozirgi: "
        f"{user_lang.get(m.from_user.id, 'uz')})"
    )


@dp.message(Command("lang"))
async def lang(m: Message):
    arg = (m.text or "").split(maxsplit=1)[1:] 
    code = arg[0].strip().lower() if arg else ""
    if code not in LANGS:
        await m.answer("Foydalanish: /lang uz  yoki  /lang ru  yoki  /lang en")
        return
    user_lang[m.from_user.id] = code
    await m.answer(f"Til o'zgartirildi: {code}")


@dp.message()
async def handle_topic(m: Message):
    topic = (m.text or "").strip()
    if not topic or topic.startswith("/"):
        return
    lang_code = user_lang.get(m.from_user.id, "uz")
    status = await m.answer("Navbatda...")

    async with job_limit:
        workdir = Path(tempfile.mkdtemp(prefix="storybot_"))
        try:
            await status.edit_text("1/4 Hikoya yozilmoqda...")
            story = await make_story(topic, lang_code)
            scenes = story["scenes"]

            await status.edit_text("2/4 Rasmlar va ovozlar yaratilmoqda...")
            voice = LANGS[lang_code]["voice"]
            async with aiohttp.ClientSession() as session:
                tasks = []
                for i, s in enumerate(scenes):
                    tasks.append(make_image(session, s["image_prompt"], workdir / f"{i}.jpg", seed=i + 7))
                    tasks.append(make_voice(s["narration"], voice, workdir / f"{i}.mp3"))
                await asyncio.gather(*tasks)

            await status.edit_text("3/4 Video montaj qilinmoqda...")
            clips = []
            for i in range(len(scenes)):
                clip = workdir / f"clip{i}.mp4"
                await asyncio.to_thread(build_scene_clip, workdir / f"{i}.jpg", workdir / f"{i}.mp3", clip)
                clips.append(clip)
            final = workdir / "final.mp4"
            await asyncio.to_thread(concat_clips, clips, final, workdir)

            await status.edit_text("4/4 Yuborilmoqda...")
            await m.answer_video(
                FSInputFile(final),
                caption=story.get("title", topic)[:200],
                width=WIDTH, height=HEIGHT, supports_streaming=True,
            )
            await status.delete()
        except Exception as e:  # noqa: BLE001
            log.exception("Xato")
            await status.edit_text(f"Xatolik yuz berdi: {e}\nQayta urinib ko'ring.")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


async def main():
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
