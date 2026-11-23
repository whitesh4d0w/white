#!/usr/bin/env python3
import os, sys, glob, json, time, shutil, subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
BROLL_DIR = DOWNLOADS_DIR / "broll"
RAW_DIR = BROLL_DIR / "raw_gameplay"
TEMP_DIR = BASE_DIR / "temp"

for d in [DOWNLOADS_DIR, BROLL_DIR, RAW_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

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
        print("❌ Chyba: GEMINI_API_KEY nebyl nalezen v .env!")
        sys.exit(1)
    from google import genai
    return genai.Client(api_key=key)

def classify_frame(client, img_path: Path) -> str:
    from google.genai import types
    with open(img_path, "rb") as f:
        img_bytes = f.read()

    prompt = """You are a video editor tagger for GTA 6 gameplay clips.
Look at this video screenshot and categorize it into EXACTLY ONE category:
- 'water' (if showing ocean, speedboats, airboats, swamps, beach, waves, flooding, watercraft)
- 'police' (if showing police cars, sirens, helicopters, cops, roadblocks, police pursuits)
- 'cars' (if showing driving sports cars, drifting, car tuning, motorbikes, highway traffic)
- 'heist' (if showing shootouts, aiming guns, robberies, store stick-ups, weapons, explosions)
- 'city' (if showing city streets, pedestrians, skyscrapers, luxury malls, motels, neon clubs)

Output ONLY valid JSON: {"category": "..."}"""

    try:
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
        print(f"    Chyba vision: {e}")
        return "city"

def scan_and_tag_all():
    client = get_gemini_client()
    raw_clips = sorted(glob.glob(str(RAW_DIR / "*.mp4")))
    if not raw_clips:
        # Pokud nejsou v raw_gameplay, zkusíme najít neotagované přímo v broll
        raw_clips = sorted(glob.glob(str(BROLL_DIR / "action_gameplay_*.mp4")))

    if not raw_clips:
        print("📁 Žádné nezařazené gameplay klipy nebyly nalezeny.")
        return

    print("=" * 65)
    print(f"👁️ AI VISION SCANNER: Skenuji {len(raw_clips)} gameplay klipů...")
    print("=" * 65)

    stats = {"water": 0, "police": 0, "cars": 0, "heist": 0, "city": 0}
    ts = int(time.time())

    for idx, clip in enumerate(raw_clips, start=1):
        c_path = Path(clip)
        thumb_path = TEMP_DIR / f"scan_{ts}_{idx}.jpg"

        # 1. Extrakce 1 snímku z poloviny videa
        cmd_thumb = [
            FFMPEG_BIN, "-y",
            "-ss", "2.0",
            "-i", str(c_path),
            "-vframes", "1",
            "-q:v", "2",
            str(thumb_path)
        ]
        subprocess.run(cmd_thumb, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not thumb_path.exists():
            continue

        # 2. Gemini Vision se podívá a určí kategorii
        cat = classify_frame(client, thumb_path)
        stats[cat] = stats.get(cat, 0) + 1

        # 3. Přejmenování a přesun do broll/
        new_name = f"{cat}_gameplay_{ts}_{idx:03d}.mp4"
        dest_path = BROLL_DIR / new_name
        shutil.move(str(c_path), str(dest_path))

        icons = {"water": "🌊", "police": "🚨", "cars": "🚗", "heist": "💥", "city": "🌆"}
        print(f"  [{idx:02d}/{len(raw_clips)}] {icons.get(cat, '🎬')} {cat.upper():<7} -> Přesunuto jako: {new_name}")

        if thumb_path.exists():
            thumb_path.unlink()

    print("\n" + "=" * 65)
    print("🎉 DOKONČENO! Výsledky AI vizuální analýzy:")
    print("=" * 65)
    for c, count in stats.items():
        print(f" - {c.upper():<8}: {count} klipů")
    print("=" * 65 + "\n")

    # Spustit vypsání finálních statistik
    try:
        from sync_broll import run_sync
        run_sync()
    except Exception as e:
        print(f"Info: {e}")

if __name__ == "__main__":
    scan_and_tag_all()
