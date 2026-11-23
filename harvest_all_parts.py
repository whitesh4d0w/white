#!/usr/bin/env python3
"""
harvest_all_parts.py - Plné stažení videa a bleskový lokální střih s AI Vision.
Když je na disku 150 GB, stáhneme celé video v kuse přes yt-dlp maximální rychlostí
sítě a pak z něj lokálně na disku vyřežeme 100+ klipů (1 sekunda na klip!).
"""

import os
import sys
import glob
import json
import time
import shutil
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
BROLL_DIR = DOWNLOADS_DIR / "broll"
TEMP_DIR = BASE_DIR / "temp"

for d in [DOWNLOADS_DIR, BROLL_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

WALKTHROUGHS = [
    {"part": 2, "name": "Part 2 (11.8h)", "url": "https://www.youtube.com/watch?v=FE0rJicoBXU"},
    {"part": 3, "name": "Part 3 (6.6h)",  "url": "https://www.youtube.com/watch?v=Sc21BxEFZnM"},
    {"part": 4, "name": "Part 4 (10.6h)", "url": "https://www.youtube.com/watch?v=RfKOBr9FOE4"}
]

def get_gemini_client():
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
        print("❌ Chyba: GEMINI_API_KEY nenalezen v .env!")
        sys.exit(1)
    from google import genai
    return genai.Client(api_key=key)

def classify_frame(client, img_path: Path) -> str:
    from google.genai import types
    try:
        with open(img_path, "rb") as f:
            img_bytes = f.read()

        prompt = """Analyze this GTA 6 gameplay frame and classify it into EXACTLY ONE category:
- 'water' (ocean, speedboats, airboats, swamps, beach, flood, water physics, jet skis)
- 'police' (police cruisers, sirens, helicopters, cops, roadblocks, police pursuits)
- 'cars' (car driving, drifting, customization, motorbikes, supercars, highway traffic)
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
        return "city"

def download_full_video(url: str, dest_file: Path) -> bool:
    """Stáhne celé video maximální rychlostí přes yt-dlp s přímým zobrazením v terminálu."""
    if dest_file.exists() and dest_file.stat().st_size > 100_000_000:
        gb = round(dest_file.stat().st_size / (1024**3), 2)
        print(f"✅ Video již existuje na disku ({gb} GB). Přeskakuji stahování.")
        return True

    print(f"\n📥 Zahajuji stahování celého videa do: {dest_file.name}")
    print("   (Stahuje se čistá 1080p video stopa bez audia pro maximální rychlost a úsporu místa)")

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--ffmpeg-location", FFMPEG_BIN,
        "-f", "bestvideo[height<=1080][ext=mp4]/bestvideo[height<=1080]/best[height<=1080]",
        "-o", str(dest_file),
        url
    ]

    t0 = time.time()
    res = subprocess.run(cmd)
    dur = round(time.time() - t0, 1)

    if res.returncode == 0 and dest_file.exists():
        gb = round(dest_file.stat().st_size / (1024**3), 2)
        print(f"\n✅ Video kompletně staženo: {gb} GB za {dur}s ({dur/60:.1f} min)")
        return True
    else:
        print(f"\n❌ Chyba při stahování videa!")
        return False

def slice_locally(client, local_video: Path, part: int, num_clips: int, duration: float = 4.5):
    """Z lokálního videa vyřeže požadovaný počet 9:16 vertikálních klipů a otaguje je."""
    print("\n🔍 Zjišťuji délku lokálního souboru přes ffprobe...")
    cmd_probe = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(local_video)
    ]
    res = subprocess.run(cmd_probe, capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        print("⚠️ ffprobe selhal, odhaduji délku...")
        total_sec = 40000.0
    else:
        total_sec = float(res.stdout.strip())

    h = int(total_sec // 3600)
    m = int((total_sec % 3600) // 60)
    print(f"✅ Celková délka: {h}h {m}m ({int(total_sec)} s)")

    start_margin = min(900, int(total_sec * 0.05))
    end_margin = max(start_margin + 1200, int(total_sec * 0.95))
    step = (end_margin - start_margin) / (num_clips + 1)
    timestamps = [start_margin + (i + 1) * step for i in range(num_clips)]

    print(f"\n⚡ Spouštím lokální střih {num_clips} klipů na disku:")
    print("=" * 65)

    ts = int(time.time())
    saved = 0
    icons = {"water": "🌊", "police": "🚨", "cars": "🚗", "heist": "💥", "city": "🌆"}

    for i, t in enumerate(timestamps, start=1):
        s_h, s_m, s_s = int(t // 3600), int((t % 3600) // 60), int(t % 60)
        t_str_s = f"{s_h:02d}:{s_m:02d}:{s_s:02d}"

        temp_crop = TEMP_DIR / f"crop_{ts}_{i:03d}.mp4"
        thumb = TEMP_DIR / f"thumb_{ts}_{i:03d}.jpg"

        t_clip_start = time.time()
        print(f"[{i:03d}/{num_clips}] ✂️ Čas: {t_str_s}...", end=" ", flush=True)

        cmd_crop = [
            FFMPEG_BIN, "-y", "-nostdin",
            "-ss", str(t),
            "-i", str(local_video),
            "-t", str(duration),
            "-an",
            "-vf", "crop=w=ih*(9/16):h=ih:x=(iw-ow)/2:y=0,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            str(temp_crop)
        ]
        res_crop = subprocess.run(cmd_crop, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res_crop.returncode != 0 or not temp_crop.exists() or temp_crop.stat().st_size < 50000:
            print("⚠️ Chyba střihu")
            if temp_crop.exists(): temp_crop.unlink()
            continue

        cmd_th = [FFMPEG_BIN, "-y", "-nostdin", "-ss", "2.0", "-i", str(temp_crop), "-vframes", "1", "-q:v", "2", str(thumb)]
        subprocess.run(cmd_th, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        cat = classify_frame(client, thumb) if thumb.exists() else "city"
        out_name = f"{cat}_shirrako_p{part}_{ts}_{i:03d}.mp4"
        dest = BROLL_DIR / out_name

        shutil.move(str(temp_crop), str(dest))
        saved += 1
        icon = icons.get(cat, "🎬")
        tot = round(time.time() - t_clip_start, 1)
        print(f"-> {icon} {cat.upper()} ({out_name}) [{tot}s]")

        if thumb.exists():
            thumb.unlink()

    return saved

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--clips-per-video", type=int, default=100, help="Kolik klipů z každého dílu vyříznout")
    p.add_argument("--part", type=int, default=0, help="Zpracovat pouze konkrétní part (např. 2, 3 nebo 4). 0 = všechny")
    p.add_argument("--cleanup", action="store_true", help="Smazat původní stažené video po dokončení střihu")
    args = p.parse_args()

    client = get_gemini_client()

    targets = WALKTHROUGHS
    if args.part in [2, 3, 4]:
        targets = [w for w in WALKTHROUGHS if w["part"] == args.part]

    print("=" * 65)
    print("🚀 LOKÁLNÍ TĚŽBA ZE STAŽENÉHO VIDEA (150 GB DISK)")
    print(f"Cíl: {args.clips_per_video} klipů na video | Zpracovává se: {[w['name'] for w in targets]}")
    print("=" * 65)

    total_added = 0
    for w in targets:
        local_file = DOWNLOADS_DIR / f"full_walkthrough_p{w['part']}.mp4"
        print(f"\n=======================================================")
        print(f"🎮 {w['name']} - {w['url']}")
        print(f"=======================================================")
        
        ok = download_full_video(w["url"], local_file)
        if not ok:
            continue

        saved = slice_locally(client, local_file, w["part"], num_clips=args.clips_per_video, duration=4.5)
        total_added += saved

        if args.cleanup and local_file.exists():
            print(f"\n🧹 Mažu stažený zdrojový soubor {local_file.name}...")
            local_file.unlink()

    print("\n" + "=" * 65)
    print(f"🎉 CELKEM ÚSPĚŠNĚ VYTVOŘENO {total_added} NOVÝCH REAL PS5 PRO ZÁBĚRŮ!")
    print("=" * 65)

    try:
        from sync_broll import run_sync
        run_sync()
    except Exception as e:
        print(f"Statistika: {e}")

if __name__ == "__main__":
    main()
