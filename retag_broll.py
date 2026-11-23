#!/usr/bin/env python3
import os
import sys
import glob
import json
import time
import shutil
import subprocess
import re
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
BROLL_DIR = DOWNLOADS_DIR / "broll"
TEMP_DIR = BASE_DIR / "temp"

for d in [DOWNLOADS_DIR, BROLL_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

CANDIDATE_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.5-flash"
]

def get_gemini_client():
    from google import genai
    from google.genai import types

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
        print("❌ Chyba: GEMINI_API_KEY nenalezen v .env!", flush=True)
        sys.exit(1)

    http_opts = types.HttpOptions(timeout=12000)
    return genai.Client(api_key=key, http_options=http_opts)

PROMPT = """Analyze this GTA 6 gameplay frame.
Classify it into EXACTLY ONE of these categories:
- water (ocean, speedboats, airboats, swamps, beach, flood, water physics, jet skis)
- police (police cruisers, sirens, helicopters, cops, roadblocks, police pursuits)
- cars (car driving, drifting, customization, motorbikes, supercars, highway traffic)
- heist (gunfights, weapons, aiming guns, robberies, store stick-ups, explosions)
- city (city streets, pedestrians, skyscrapers, clubs, malls, motels)

Reply with ONLY ONE WORD representing the category: water, police, cars, heist, or city."""

def extract_category(text: str) -> str:
    if not text:
        return "city"
    m = re.search(r'\b(water|police|cars?|heist|city)\b', text.lower())
    if m:
        c = m.group(1)
        return "cars" if c == "car" else c
    return "city"

def classify_frame_resilient(client, img_path: Path, preferred_model: str) -> tuple[str, str]:
    from google.genai import types

    with open(img_path, "rb") as f:
        img_bytes = f.read()

    part = types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")

    fast_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        max_output_tokens=20
    )

    idx = CANDIDATE_MODELS.index(preferred_model) if preferred_model in CANDIDATE_MODELS else 0
    ordered_models = CANDIDATE_MODELS[idx:] + CANDIDATE_MODELS[:idx]

    for model in ordered_models:
        for attempt in range(1, 4):
            try:
                res = client.models.generate_content(
                    model=model,
                    contents=[part, PROMPT],
                    config=fast_config
                )
                raw = (res.text or "").strip()
                cat = extract_category(raw)
                return cat, model
            except Exception as e:
                err_str = str(e).lower()
                if "thinking" in err_str or "unsupported" in err_str:
                    try:
                        res = client.models.generate_content(
                            model=model,
                            contents=[part, PROMPT]
                        )
                        raw = (res.text or "").strip()
                        return extract_category(raw), model
                    except Exception as e2:
                        err_str = str(e2).lower()

                if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                    time.sleep(4.0)
                elif "503" in err_str or "unavailable" in err_str or "high demand" in err_str:
                    time.sleep(0.5)
                    break
                elif "404" in err_str:
                    break
                else:
                    time.sleep(1.0)

    return "city", "city"

print_lock = threading.Lock()
completed_counter = 0
stats = {"water": 0, "police": 0, "cars": 0, "heist": 0, "city": 0}
icons = {"water": "🌊", "police": "🚨", "cars": "🚗", "heist": "💥", "city": "🌆"}

def process_single_clip(client, clip_path: Path, preferred_model: str, total: int):
    global completed_counter, stats

    thumb = TEMP_DIR / f"th_{clip_path.stem}.jpg"
    cmd_th = [FFMPEG_BIN, "-y", "-nostdin", "-ss", "2.0", "-i", str(clip_path), "-vframes", "1", "-q:v", "2", str(thumb)]
    subprocess.run(cmd_th, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not thumb.exists():
        with print_lock:
            completed_counter += 1
            print(f"[{completed_counter:03d}/{total}] ❌ {clip_path.name[:25]}... (Chyba náhledu)", flush=True)
        return

    t0 = time.time()
    cat, used_model = classify_frame_resilient(client, thumb, preferred_model)
    dur = round(time.time() - t0, 2)

    old_name = clip_path.name
    parts = old_name.split("_", 1)
    if len(parts) > 1 and parts[0] in ["city", "water", "police", "cars", "heist", "clip", "action"]:
        new_name = f"{cat}_{parts[1]}"
    else:
        new_name = f"{cat}_{old_name}"

    new_path = BROLL_DIR / new_name
    if clip_path != new_path:
        try:
            shutil.move(str(clip_path), str(new_path))
        except Exception:
            pass

    if thumb.exists():
        thumb.unlink()

    with print_lock:
        completed_counter += 1
        stats[cat] = stats.get(cat, 0) + 1
        icon = icons.get(cat, "🎬")
        print(f"[{completed_counter:03d}/{total}] {icon} {cat.upper():<6} -> {new_name[:32]:<32} ({dur:>4.1f}s, {used_model})", flush=True)

    time.sleep(1.2)

def retag_remaining(max_workers: int = 4):
    global completed_counter, stats
    client = get_gemini_client()

    all_clips = sorted([f for f in BROLL_DIR.glob("*.mp4") if f.is_file() and f.stat().st_size > 50000])
    if not all_clips:
        print("❌ Žádné klipy v downloads/broll/ nenalezeny!", flush=True)
        return

    already_done = [f for f in all_clips if f.name.startswith(("water_", "police_", "cars_", "heist_"))]
    clips_to_process = [f for f in all_clips if f not in already_done]

    for f in already_done:
        cat = f.name.split("_")[0]
        stats[cat] = stats.get(cat, 0) + 1

    print("=" * 68, flush=True)
    print(f"🎯 PŘETŘÍDĚNÍ ZBYLÝCH KLIPŮ (ROZLOŽENÍ MEZI 4 NEZÁVISLÉ MODELY)", flush=True)
    print(f"Celkem v knihovně: {len(all_clips)} | Již hotovo: {len(already_done)} | K roztřídění: {len(clips_to_process)}", flush=True)
    print(f"Modely v rotaci: {', '.join(CANDIDATE_MODELS[:4])}", flush=True)
    print("=" * 68, flush=True)

    if not clips_to_process:
        print("✅ Všechny klipy již byly úspěšně roztříděny!", flush=True)
    else:
        total = len(clips_to_process)
        completed_counter = 0
        t_start = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for idx, clip in enumerate(clips_to_process):
                assigned_model = CANDIDATE_MODELS[idx % len(CANDIDATE_MODELS[:4])]
                futures.append(executor.submit(process_single_clip, client, clip, assigned_model, total))

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass

        total_time = round(time.time() - t_start, 1)
        print("\n" + "=" * 68, flush=True)
        print(f"⚡ VŠECH {total} KLIPŮ DŮSLEDNĚ PŘETŘÍDĚNO ZA {total_time}s ({round(total_time/60, 1)} min)!", flush=True)

    print("=" * 68, flush=True)
    print("📊 KONEČNÝ STAV KNIHOVNY B-ROLL PO KOMPLETNÍM PŘETŘÍDĚNÍ:")
    print("=" * 68, flush=True)
    for c in ["water", "police", "cars", "heist", "city"]:
        icon = icons.get(c, "🎬")
        print(f" {icon} {c.upper():<7}: {stats.get(c, 0):>3} klipů", flush=True)
    print("=" * 68 + "\n", flush=True)

    try:
        from sync_broll import run_sync
        run_sync()
    except Exception as e:
        print(f"Info sync: {e}", flush=True)

if __name__ == "__main__":
    retag_remaining(max_workers=4)
