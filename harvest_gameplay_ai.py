#!/usr/bin/env python3
import os, sys, json, time, shutil, argparse, subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
BROLL_DIR = DOWNLOADS_DIR / "broll"
TEMP_DIR = BASE_DIR / "temp"

for d in [DOWNLOADS_DIR, BROLL_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

def load_gemini_client():
    env_file = BASE_DIR / ".env"
    key = ""
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("GEMINI_API_KEY="):
                    key = line.strip().split("=", 1)[1].strip('"').strip("'")
    if not key:
        key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=key)
    except Exception:
        return None

def classify_frame_with_gemini(client, image_path: Path) -> str:
    if not client:
        return "city"
    try:
        from google.genai import types
        with open(image_path, "rb") as f:
            img_bytes = f.read()

        prompt = """Analyze this GTA 6 gameplay frame and classify it into EXACTLY ONE category:
- 'water' (ocean, boats, swamps, beach, flood, water physics, jet skis)
- 'police' (police cruisers, sirens, helicopters, cop pursuits)
- 'cars' (car driving, drifting, customization, motorbikes, supercars)
- 'heist' (gunfights, weapons, aiming guns, robberies, store stick-ups, explosions)
- 'city' (city streets, pedestrians, skyscrapers, clubs, malls, motels)

Output ONLY valid JSON: {"category": "..."}"""

        res = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        )
        data = json.loads(res.text.strip())
        cat = data.get("category", "city").lower()
        if cat in ["water", "police", "cars", "heist", "city"]:
            return cat
        return "city"
    except Exception as e:
        print(f"    [Vision AI] Fallback na city: {e}")
        return "city"

def harvest_gameplay(url: str, num_clips: int = 25, clip_duration: float = 4.5):
    client = load_gemini_client()
    print("=" * 65)
    print("🎬 AI GAMEPLAY HARVESTER & VISION TAGGER")
    print(f"URL: {url}")
    print(f"Počet požadovaných klipů: {num_clips} (délka: {clip_duration}s)")
    print("=" * 65)

    print("\n[1/3] Zjišťuji délku a časovou osu videa...")
    cmd_info = ["yt-dlp", "--dump-json", "--no-playlist", url]
    res_info = subprocess.run(cmd_info, capture_output=True, text=True)
    if res_info.returncode != 0:
        print(f"Chyba při načítání informací o videu: {res_info.stderr[:200]}")
        return

    info = json.loads(res_info.stdout)
    total_sec = int(info.get("duration", 3600))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    print(f"-> Nalezeno video: '{info.get('title')}'")
    print(f"-> Celková délka: {h}h {m}m ({total_sec} sekund)")

    start_margin = min(600, int(total_sec * 0.05))
    end_margin = max(start_margin + 600, int(total_sec * 0.95))
    step = (end_margin - start_margin) // (num_clips + 1)
    timestamps = [start_margin + (i + 1) * step for i in range(num_clips)]

    print(f"\n[2/3] Naplánováno {len(timestamps)} časových bodů napříč celým walkthrough...")
    print("\n[3/3] Stahuji konkrétní výřezy a analyzuji scénu přes Gemini Vision...")
    ts_now = int(time.time())
    saved_clips = []

    for i, t in enumerate(timestamps, start=1):
        t_start = t
        t_end = t + clip_duration
        t_str_start = f"{int(t_start // 3600):02d}:{int((t_start % 3600) // 60):02d}:{int(t_start % 60):02d}"
        t_str_end = f"{int(t_end // 3600):02d}:{int((t_end % 3600) // 60):02d}:{int(t_end % 60):02d}"

        raw_clip = TEMP_DIR / f"raw_harvest_{ts_now}_{i:03d}.mp4"
        thumb = TEMP_DIR / f"thumb_{ts_now}_{i:03d}.jpg"

        print(f"\n  [{i:02d}/{num_clips}] Stahuji úsek {t_str_start} - {t_str_end}...")
        cmd_dl = [
            "yt-dlp",
            "--ffmpeg-location", FFMPEG_BIN,
            "--download-sections", f"*{t_str_start}-{t_str_end}",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
            "--merge-output-format", "mp4",
            "-o", str(raw_clip),
            "--force-overwrites",
            url
        ]
        res = subprocess.run(cmd_dl, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode != 0 or not raw_clip.exists() or raw_clip.stat().st_size < 100000:
            print("    ⚠️ Stažení úseku selhalo, přeskakuji...")
            continue

        # Extrakce kontrolního snímku pro AI
        cmd_thumb = [
            FFMPEG_BIN, "-y",
            "-ss", str(clip_duration / 2.0),
            "-i", str(raw_clip),
            "-vframes", "1",
            "-q:v", "2",
            str(thumb)
        ]
        subprocess.run(cmd_thumb, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # AI Vision analýza
        cat = "city"
        if thumb.exists() and client:
            cat = classify_frame_with_gemini(client, thumb)
        print(f"    👁️ Gemini Vision detekovalo: {cat.upper()}")

        # 9:16 vertikální ořez bez audia (-an) přímo do knihovny
        out_name = f"{cat}_shirrako_{ts_now}_{i:03d}.mp4"
        final_clip = BROLL_DIR / out_name

        cmd_crop = [
            FFMPEG_BIN, "-y",
            "-i", str(raw_clip),
            "-an",
            "-vf", "crop=w=ih*(9/16):h=ih:x=(iw-ow)/2:y=0,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(final_clip)
        ]
        res_crop = subprocess.run(cmd_crop, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res_crop.returncode == 0 and final_clip.exists() and final_clip.stat().st_size > 50000:
            saved_clips.append(out_name)
            print(f"    ✅ Uloženo: {out_name}")

        if raw_clip.exists(): raw_clip.unlink()
        if thumb.exists(): thumb.unlink()

    print("\n" + "=" * 65)
    print(f"🎉 HOTOVO! Úspěšně vytvořeno a AI otagováno {len(saved_clips)} nových reálných záběrů.")
    print("=" * 65)

    try:
        from sync_broll import run_sync
        run_sync()
    except Exception as e:
        print(f"Statistika: {e}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="https://www.youtube.com/watch?v=FE0rJicoBXU")
    p.add_argument("--clips", type=int, default=30)
    args = p.parse_args()
    harvest_gameplay(args.url, num_clips=args.clips)
