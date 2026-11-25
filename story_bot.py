import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

if sys.prefix == sys.base_prefix:
    for venv_path in ["/root/gta6_shorts_bot/venv/bin/python3", "/root/minecraft_stories_bot/venv/bin/python3"]:
        if os.path.exists(venv_path):
            os.execv(venv_path, [venv_path] + sys.argv)

import warnings
warnings.filterwarnings("ignore")

import glob
import math
import json
import random
import re
import argparse
import subprocess
import time
import asyncio
import urllib.request
from datetime import datetime, timedelta

from google import genai
from google.genai import types
from whisper_engine import transcribe_and_make_subtitles
from sfx_engine import build_sfx_track

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
PARKOUR_DIR = os.path.join(DOWNLOADS_DIR, "parkour")
MUSIC_DIR = os.path.join(BASE_DIR, "music")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
HISTORY_FILE = os.path.join(BASE_DIR, "history_stories.json")

for folder in [DOWNLOADS_DIR, PARKOUR_DIR, MUSIC_DIR, TEMP_DIR, OUTPUT_DIR]:
    os.makedirs(folder, exist_ok=True)

ENV_PATH = os.path.join(BASE_DIR, ".env")
if not os.path.exists(ENV_PATH):
    parent_env = os.path.join(os.path.dirname(BASE_DIR), "gta6_shorts_bot", ".env")
    if os.path.exists(parent_env): ENV_PATH = parent_env

if os.path.exists(ENV_PATH):
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and v: os.environ.setdefault(k, v)
    except Exception: pass

import shutil, imageio_ffmpeg
FFMPEG_PATH = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()

BG_MUSIC_FILE = os.path.join(MUSIC_DIR, "ambient_story_bg.mp3")

TEXT_MODELS = [
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
]

TTS_MODELS = [
    "gemini-3.8-flash-tts",
    "gemini-3.8-flash-lite-tts",
    "gemini-3.1-flash-tts-preview",
]

OFFLINE_STORIES = [
    {
        "category": "drama_revenge",
        "title": "My Boss Tried To Fire Me In Secret",
        "parts": [
            "My arrogant manager called me into his corner glass office at exactly 5 PM on a freezing Friday afternoon. With a smug grin on his face, he handed me a termination letter and told me I was fired on the spot with zero severance pay. What my manager completely forgot was that three years ago, when the company was broke and just starting out, our CEO had me personally register and pay for the primary web domain and corporate cloud servers under my private personal developer account. As I walked out through the parking lot to my car, I pulled out my phone, logged into my registrar dashboard, and redirected the entire corporate website, payment gateway, and customer login portal to a massive high definition image of a circus clown. Two hours later, my phone began vibrating non stop with forty missed calls from the CEO. Subscribe for Part 2 right now!",
            "Part 2: Why the furious CEO was frantically calling my personal phone. It turns out the CEO was attending an international investor conference and had absolutely no idea that my middle manager had fired me to cover up his own missing quarterly budget. When I finally answered on the tenth ring, the CEO was practically in tears, begging me to restore the online payment portal because the entire business was losing over fifty thousand dollars every fifteen minutes during their biggest promotional campaign of the year. I calmly leaned back on my sofa and explained to him that since I was no longer an employee, my emergency external engineering consulting fee was now thirty thousand dollars upfront via direct bank wire, accompanied by a signed executive release for my full annual severance. Within six minutes, my banking notification chimed with the full payment. Subscribe for Part 3 right now to see the final revenge!",
            "Part 3: The ultimate corporate revenge on my former boss. The moment the wire transfer settled into my account, I restored the company DNS records and emailed the CEO an encrypted digital audit trail showing that my former manager had funneled company funds into his personal crypto wallet and blamed me for the losses. Early Monday morning, the CEO personally arrived at headquarters with building security and two local police detectives. My former manager was escorted out of the executive suite in handcuffs in front of the entire cheering engineering department. To top it all off, the CEO offered me my former boss role with a fifty percent salary increase and company stock options. I declined the offer, thanked him for the payout, and used the consulting cash to launch my own software firm. Would you have taken the job or walked away with the cash? Let me know below!"
        ],
        "description": "My toxic manager fired me with zero severance until he realized who owned the domain. Part 1 of 3! 👇"
    }
]

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return []

def save_to_history(title, category, parts_count=3):
    hist = load_history()
    hist.append({"time": int(time.time()), "title": title, "category": category, "parts": parts_count})
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f: json.dump(hist[-50:], f, indent=2)
    except Exception: pass

def get_next_rotated_parts() -> int:
    hist = load_history()
    if not hist:
        return 2
    last_parts = hist[-1].get("parts", 2)
    rotation = {2: 3, 3: 4, 4: 2}
    return rotation.get(last_parts, 3)

def get_offline_story(history_titles, num_parts=3):
    avail = [s for s in OFFLINE_STORIES if s["title"] not in history_titles]
    if not avail: avail = OFFLINE_STORIES
    st = random.choice(avail)
    st_copy = dict(st)
    st_copy["parts"] = st["parts"][:num_parts]
    return st_copy

def get_available_text_models(client: genai.Client) -> list:
    discovered = []
    try:
        for m in client.models.list():
            m_id = m.name.replace("models/", "")
            actions = getattr(m, "supported_actions", [])
            if "generateContent" in actions or hasattr(m, "input_token_limit"):
                if "tts" not in m_id.lower() and "embed" not in m_id.lower() and "imagen" not in m_id.lower():
                    discovered.append(m_id)
    except Exception: pass

    priority = [
        "gemini-4-hydrogen",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.1-flash-lite",
    ]
    if not discovered:
        return priority

    sorted_models = [p for p in priority if p in discovered]
    for d in discovered:
        if d not in sorted_models:
            sorted_models.append(d)
    return sorted_models or priority

def generate_story(client: genai.Client, num_parts: int = 1) -> dict:
    history = load_history()
    past_titles = [h.get("title", "") for h in history[-20:]]
    past_str = ", ".join(f'"{t}"' for t in past_titles) if past_titles else "None"

    categories = [
        "betrayal exposed publicly with irrefutable proof (wedding, family dinner, or group chat)",
        "petty malicious compliance that legally cost a toxic boss or entitled neighbor thousands",
        "terrifying late-night mystery (baby monitor, dashcam, Ring camera, or 911 call twist)",
        "secret double life discovered on an unlocked phone or hidden bank account",
        "unbelievable workplace revenge where the arrogant coworker dug their own grave",
        "chilling true-crime style stalker or intruder twist with an unexpected savior",
    ]
    chosen_cat = random.choice(categories)

    if num_parts == 1:
        prompt = f"""You are an elite viral Reddit Storytime writer for US TikTok and YouTube Shorts.
Write ONE complete, self-contained, adrenaline-fueled viral story in the theme: '{chosen_cat}'.

STRICT RULES FOR MAXIMUM DRIVE, SUSPENSE & PAYOFF:
1. Do NOT repeat or resemble any of these recent titles: [{past_str}].
2. Word count: Strictly 110-125 words total (~40-46 seconds at fast storytelling pace).
3. RELENTLESS DRIVE (SHORT PUNCHY SENTENCES): Every sentence MUST be 5-12 words max. Short, sharp, breathless sentences only — zero filler, zero slow background explanations!
4. KILLER 2-SECOND HOOK (Sentence 1): Start IN MEDIA RES at the exact moment of shock with concrete details (time, object, betrayal). Example energy: "I found a burner phone taped under my husband's car seat at 2 AM."
5. RISING TENSION: Every 2 sentences must raise the stakes or reveal a sharper clue. Keep the listener leaning in!
6. UNFORGETTABLE CLIMAX & PAYOFF: The ending MUST deliver a ruthless, crystal-clear, jaw-dropping twist or karma payoff (concrete action/consequence, NEVER a vague moral or soft ending), then finish with: "Like and subscribe for more!"
7. Tone: Raw first-person ('I', 'me'), urgent, dramatic, zero AI-sounding clichés.
8. Random seed: {random.randint(100000, 999999)}

Output ONLY valid JSON:
{{
  "title": "Punchy Curiosity Title Under 50 Chars",
  "category": "reddit_story",
  "parts": [
    "Complete 110-125 word high-drive story script..."
  ],
  "description": "1-2 sentence suspense teaser + comment question"
}}"""
    else:
        prompt = f"""You are a master viral storyteller on TikTok and YouTube Shorts.
Write an intensely gripping, suspenseful {num_parts}-PART viral story in the genre: '{chosen_cat}'.

STRICT RULES FOR 45-SECOND RETENTION (EACH PART MUST STAY UNDER 55 SECONDS):
1. Do NOT repeat or resemble any of these recent titles: [{past_str}].
2. Word count: Each part MUST be strictly 110-125 words long (giving ~42-48 seconds of spoken audio).
3. Part 1: Starts with an immediate shocking first-person hook in sentence 1. Builds intense rising action. Ends on a massive cliffhanger with: 'Subscribe for Part 2!'.
4. Middle parts (if {num_parts} >= 3): Start with 'Part [X]: [quick 5-word recap]...'. The situation spirals, reveals an unexpected shocking twist, ends with: 'Subscribe for Part [X+1]!'.
5. Final part (Part {num_parts}): Starts with 'Part {num_parts}: [quick 5-word recap]...'. Delivers the shocking climax, revenge/resolution, and ends with a quick CTA ("Like and subscribe for daily stories!").
6. Tone: First-person ('I', 'me'), conversational, ultra-engaging, fast-paced.
7. Random seed: {random.randint(100000, 999999)}

Output ONLY valid JSON:
{{
  "title": "Catchy Story Title Under 50 Chars",
  "category": "{chosen_cat}",
  "parts": [
    "Part 1 script (110-125 words)...",
    "Part 2 script (110-125 words)..."
  ],
  "description": "Short YouTube teaser description for Part 1"
}}"""

    models = get_available_text_models(client)
    MAX_ATTEMPTS = 3
    print(f"🔍 Nalezeno {len(models)} textových modelů. Zahajuji generování (až {MAX_ATTEMPTS} pokusy na model)...")

    for model_name in models:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.time()
            attempt_str = f" (pokus {attempt}/{MAX_ATTEMPTS})" if MAX_ATTEMPTS > 1 else ""
            print(f"Zkouším Gemini model: {model_name}{attempt_str}...")
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=1.0,
                        http_options=types.HttpOptions(timeout=180000)
                    )
                )
                raw = res.text.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
                    raw = re.sub(r"\n?```$", "", raw).strip()
                data = json.loads(raw)
                if "parts" in data and len(data["parts"]) >= num_parts:
                    print(f"-> {num_parts}-dílný příběh (~50s/díl) úspěšně vytvořen ({model_name}) za {time.time() - t0:.1f}s!")
                    return data
            except Exception as e:
                err = str(e)
                if "404" in err or "NOT_FOUND" in err:
                    break
                elif "503" in err or "UNAVAILABLE" in err:
                    print(f"   Model {model_name} je dočasně přetížen (503), čekám 15s... (pokus {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(15)
                elif "429" in err or "RESOURCE_EXHAUSTED" in err:
                    print(f"   Model {model_name} vyčerpal limit (429), čekám 5s... (pokus {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(5)
                elif "504" in err or "DEADLINE" in err:
                    print(f"   Model {model_name} nestihl odpovědět včas (timeout 180s)... (pokus {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(3)
                else:
                    print(f"   Model {model_name} chyba: {err[:60]} (pokus {attempt}/{MAX_ATTEMPTS})")
                    if attempt < MAX_ATTEMPTS:
                        time.sleep(2)

    print(f"-> Všechny textové modely vyčerpány, aktivuji offline příběhovou databázi ({num_parts} díly)...")
    return get_offline_story(past_titles, num_parts=num_parts)

def generate_voiceover_edge_fallback(text: str, output_audio: str):
    try:
        import edge_tts
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "edge-tts", "-q"])
        import edge_tts

    async def _run():
        # AndrewMultilingualNeural +10% má výrazně lepší drive a přirozenější intonaci než plochý Christopher
        communicate = edge_tts.Communicate(text, "en-US-AndrewMultilingualNeural", rate="+10%")
        await communicate.save(output_audio)

    try:
        asyncio.run(_run())
    except Exception:
        cmd = ["edge-tts", "--voice", "en-US-AndrewMultilingualNeural", "--rate=+10%", "--text", text, "--write-media", output_audio]
        subprocess.run(cmd, check=True)

def generate_voiceover(text: str, output_audio: str, api_key: str = None) -> float:
    key = api_key or os.environ.get("GEMINI_API_KEY")
    audio_bytes = None

    if key:
        client = genai.Client(api_key=key, http_options=types.HttpOptions(api_version="v1alpha", timeout=60000))
        MAX_TTS_ATTEMPTS = 2
        tts_prompt = (
            "Read this as an intense, breathless, high-retention viral TikTok storyteller "
            "with sharp dramatic emphasis, rising urgency, and zero monotone:\n\n"
            f"{text}"
        )
        for model_name in TTS_MODELS:
            for attempt in range(1, MAX_TTS_ATTEMPTS + 1):
                attempt_str = f" (pokus {attempt}/{MAX_TTS_ATTEMPTS})" if MAX_TTS_ATTEMPTS > 1 else ""
                print(f"Zkouším Gemini TTS: {model_name}{attempt_str} (Hlas: Fenrir)...")
                t0 = time.time()
                try:
                    res = client.models.generate_content(
                        model=model_name,
                        contents=tts_prompt,
                        config=types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=types.SpeechConfig(
                                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Fenrir"))
                            ),
                            http_options=types.HttpOptions(timeout=60000)
                        )
                    )
                    if res and res.candidates:
                        for cand in res.candidates:
                            for part in cand.content.parts:
                                if part.inline_data and part.inline_data.data:
                                    audio_bytes = part.inline_data.data
                                    break
                    if audio_bytes:
                        print(f"-> Hlas Fenrir úspěšně vygenerován za {time.time() - t0:.1f}s!")
                        break
                except Exception as e:
                    err = str(e)
                    if "404" in err or "NOT_FOUND" in err:
                        break
                    elif "503" in err or "UNAVAILABLE" in err:
                        print(f"   Model {model_name} dočasně přetížen (503), čekám 15s... (pokus {attempt}/{MAX_TTS_ATTEMPTS})")
                        time.sleep(15)
                    elif "429" in err or "RESOURCE_EXHAUSTED" in err:
                        print(f"   Model {model_name} vyčerpal limit (429), čekám 5s... (pokus {attempt}/{MAX_TTS_ATTEMPTS})")
                        time.sleep(5)
                    elif "504" in err or "DEADLINE" in err:
                        print(f"   Model {model_name} nestihl odpovědět včas (timeout 180s)... (pokus {attempt}/{MAX_TTS_ATTEMPTS})")
                        time.sleep(3)
                    else:
                        print(f"   Model {model_name} nedostupný ({err[:60]}).")
                        if attempt < MAX_TTS_ATTEMPTS:
                            time.sleep(2)
            if audio_bytes:
                break

    if not audio_bytes:
        print("-> Přepínám na Edge-TTS (dynamický hlas AndrewMultilingual +10%)...")
        generate_voiceover_edge_fallback(text, output_audio)
    else:
        temp_raw = os.path.join(TEMP_DIR, "raw_audio_story.dat")
        with open(temp_raw, "wb") as f: f.write(audio_bytes)
        conv_cmd = [FFMPEG_PATH, "-y", "-i", temp_raw, "-c:a", "libmp3lame", "-b:a", "192k", output_audio]
        if subprocess.run(conv_cmd, capture_output=True).returncode != 0:
            subprocess.run([FFMPEG_PATH, "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", temp_raw, "-c:a", "libmp3lame", "-b:a", "192k", output_audio], check=True)
        if os.path.exists(temp_raw): os.remove(temp_raw)

    return True

def _probe_duration(video_path: str) -> float:
    ffprobe_bin = FFMPEG_PATH.replace("ffmpeg", "ffprobe") if "ffmpeg" in FFMPEG_PATH else "ffprobe"
    try:
        res = subprocess.run(
            [ffprobe_bin, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=15
        )
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def render_story_short(voice_audio: str, ass_sub: str, output_path: str, duration: float) -> bool:
    ass_esc = os.path.abspath(ass_sub).replace("\\", "/").replace(":", "\\:")
    clips = [c for c in glob.glob(os.path.join(PARKOUR_DIR, "*.mp4")) if os.path.getsize(c) > 5000000]

    if not clips:
        print("Chyba: Žádné parkour klipy v downloads/parkour/! Spusť nejdříve parkour_setup.py.")
        return False

    bg_clip = random.choice(clips)
    clip_dur = _probe_duration(bg_clip)
    # Náhodný začátek v parkour videu, aby každý Short nezačínal stejnými snímky od 00:00
    max_start = max(0.0, clip_dur - min(duration, 58.0) - 5.0)
    rand_start = round(random.uniform(0.0, max_start), 2) if max_start > 2.0 else 0.0

    # Tvrdý strop < 58.5s, aby YouTube video vždy zařadil mezi #Shorts (limit 60.0s)
    safe_dur = min(duration + 0.2, 58.5)

    inputs = []
    if rand_start > 0.0:
        inputs.extend(["-ss", f"{rand_start:.2f}"])
    inputs.extend([
        "-stream_loop", "-1", "-i", bg_clip,
        "-i", voice_audio
    ])

    # SFX intro impact pro okamžité zadržení diváka
    sfx_path = os.path.join(TEMP_DIR, f"sfx_story_{int(time.time())}.wav")
    build_sfx_track([], safe_dur, sfx_path)
    inputs.extend(["-i", sfx_path])
    voice_idx = 1
    sfx_idx = 2

    sub_filter = f"subtitles=filename='{ass_esc}'" if os.name == 'nt' else f"subtitles='{ass_esc}'"
    v_filter = f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,eq=contrast=1.05:saturation=1.1,{sub_filter}[v]"

    if os.path.exists(BG_MUSIC_FILE):
        inputs.extend(["-stream_loop", "-1", "-i", BG_MUSIC_FILE])
        music_idx = 3
        filter_complex = f"{v_filter};[{music_idx}:a]volume=0.05[bg];[{voice_idx}:a]volume=1.0[voice];[{sfx_idx}:a]volume=0.85[sfx];[voice][bg][sfx]amix=inputs=3:duration=first:dropout_transition=2[a]"
    else:
        filter_complex = f"{v_filter};[{voice_idx}:a]volume=1.0[voice];[{sfx_idx}:a]volume=0.85[sfx];[voice][sfx]amix=inputs=2:duration=first:dropout_transition=2[a]"

    cmd = [
        FFMPEG_PATH, "-y", "-nostdin", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-t", f"{safe_dur:.2f}",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-shortest", output_path
    ]

    print(f"Renderuji Top-Tier Story Short ({safe_dur:.1f}s, parkour: {os.path.basename(bg_clip)} @ {rand_start:.1f}s, kinetické titulky + SFX)...")
    res = subprocess.run(cmd)
    if os.path.exists(sfx_path):
        try: os.remove(sfx_path)
        except Exception: pass
    return res.returncode == 0

def run_story_cycle(parts="1", privacy="unlisted", schedule=None, dry_run=False):
    # Výchozí '1' (i při 'auto') generuje kompletní uzavřený příběh do 50s — výrazně vyšší retence než Part 1/2/3 spam
    if str(parts).lower() == "auto":
        resolved_parts = 1
        print("🎯 Režim 'auto': generuji 1 kompletní uzavřený Short (<55s) pro maximální dosah.")
    else:
        resolved_parts = int(parts)

    print("=" * 65)
    print(f"  AUTONOMNI STORY BOT (MINECRAFT PARKOUR, {resolved_parts} DÍLY, ~50s/DÍL)")
    print("=" * 65)

    key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=key) if key else None

    story = generate_story(client, num_parts=resolved_parts) if client else get_offline_story(load_history(), num_parts=resolved_parts)

    title = story.get("title", "Insane True Story You Wont Believe")
    category = story.get("category", "drama_revenge")
    parts_scripts = story.get("parts", [])[:resolved_parts]

    print(f"\n[Vybraný příběh]: '{title}' (Kategorie: {category}, Počet dílů: {len(parts_scripts)})")
    ts = int(time.time())

    base_h, base_m = None, None
    if schedule and ":" in schedule:
        try:
            base_h, base_m = map(int, schedule.split(":"))
        except Exception: pass

    for idx, script_text in enumerate(parts_scripts, start=1):
        print("\n" + "-" * 50)
        print(f">>> ZPRACOVAVAM PART {idx} / {resolved_parts} <<<")
        print("-" * 50)

        p_aud = os.path.join(TEMP_DIR, f"story_p{idx}_{ts}.mp3")
        p_ass = os.path.join(TEMP_DIR, f"story_p{idx}_{ts}.ass")
        generate_voiceover(script_text, p_aud, api_key=key)
        badge_txt = "TRUE STORY" if resolved_parts == 1 else f"PART {idx} / {resolved_parts}"
        dur = transcribe_and_make_subtitles(p_aud, p_ass, part_label=badge_txt)

        safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).replace(" ", "_")
        suffix = "" if resolved_parts == 1 else f"_Part{idx}"
        p_out = os.path.join(OUTPUT_DIR, f"Story_{safe_title}{suffix}_{ts}.mp4")

        if render_story_short(p_aud, p_ass, p_out, dur):
            print(f"[+] Part {idx} hotov ({dur:.1f}s): {os.path.basename(p_out)}")

            if not dry_run:
                part_sched = None
                if base_h is not None:
                    sched_h = (base_h + (idx - 1) * 2) % 24
                    part_sched = f"{sched_h:02d}:{base_m:02d}"

                yt_url = None
                try:
                    from uploader import upload_short
                    yt_title = f"{title} #Shorts" if resolved_parts == 1 else f"{title} (Part {idx}/{resolved_parts}) #Shorts"
                    if resolved_parts == 1:
                        teaser = f"{title}. What would you have done? Comment below!"
                    else:
                        teaser = f"{title} - Part {idx} of {resolved_parts}. "
                        teaser += "Subscribe right now for the next part!" if idx < resolved_parts else "What would you have done? Let me know below!"
                    yt_url = upload_short(p_out, title=yt_title, description=teaser, privacy=privacy, schedule=part_sched, delete_after=False)
                except Exception as e:
                    print(f"Info: YouTube uploader selhal ({e}). Video uloženo v output/.")

                if os.getenv("BUFFER_API_KEY"):
                    try:
                        from tiktok_buffer import post_video_to_buffer_queue
                        print(f"[+] Přidávám Part {idx} do Buffer fronty pro TikTok...")
                        caption = f"{title} #RedditStories #StoryTime #Shorts #Viral" if resolved_parts == 1 else f"{title} (Part {idx}/{resolved_parts}) #Minecraft #Stories #Parkour #Viral"
                        post_video_to_buffer_queue(p_out, caption=caption, channel_filter="stories")
                    except Exception as e:
                        print(f"Info: TikTok Buffer upload pro Part {idx} přeskočen/selhal: {e}")

                if yt_url:
                    try:
                        if os.path.exists(p_out): os.remove(p_out)
                    except Exception: pass

    save_to_history(title, category, resolved_parts)
    print("\n" + "=" * 65)
    print(f"  CYKLUS MINECRAFT STORIES ({resolved_parts} DÍLY) DOKONČEN!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--parts", default="auto", help="Počet partů: 2, 3, 4 nebo 'auto' pro rotaci (2 -> 3 -> 4 -> 2...)")
    p.add_argument("--privacy", default="unlisted", choices=["public", "unlisted", "private"])
    p.add_argument("--schedule", default=None, help="Čas publikace Part 1 (např. 16:00). Další díly se automaticky naplánují po 2 hodinách!")
    p.add_argument("--dry-run", action="store_true", help="Pouze vyrenderovat lokálně bez uploadu na YouTube/TikTok")
    args = p.parse_args()
    run_story_cycle(parts=args.parts, privacy=args.privacy, schedule=args.schedule, dry_run=args.dry_run)
