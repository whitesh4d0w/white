import os
import sys
import time
import argparse
import subprocess
import shutil
import numpy as np

BASE_DIR = "/root/gta6_shorts_bot"
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
BROLL_DIR = os.path.join(DOWNLOADS_DIR, "broll")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

os.makedirs(BROLL_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

def harvest(url, target_clips=60, clip_dur=8.5):
    print("=" * 65)
    print(f"🎬 TĚŽBA NOVÉHO GAMEPLAYE: {target_clips} scén po {clip_dur}s")
    print(f"URL: {url}")
    print("=" * 65)

    source_video = os.path.join(TEMP_DIR, "new_gameplay_source.mp4")
    source_audio = os.path.join(TEMP_DIR, "new_gameplay_audio.wav")

    # 1. Stažení 1080p streamu
    print("\n[1/4] Stahuji zdrojové video...")
    cmd_dl = [
        sys.executable, "-m", "yt_dlp",
        "-f", "137+140/399+140/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--merge-output-format", "mp4",
        "-o", source_video,
        "--force-overwrites",
        url
    ]
    subprocess.run(cmd_dl, check=True)

    # 2. Rychlá analýza audia (1kHz) na akční momenty
    print("\n[2/4] Hledám nejlepší akční pasáže (střelba, honičky, motory)...")
    cmd_aud = [
        FFMPEG, "-y", "-i", source_video,
        "-vn", "-ar", "1000", "-ac", "1", "-f", "wav",
        source_audio
    ]
    subprocess.run(cmd_aud, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    raw = np.fromfile(source_audio, dtype=np.int16, offset=44)
    energy = np.zeros(len(raw) // 1000)
    for b in range(len(energy)):
        chunk = raw[b*1000:(b+1)*1000].astype(float)
        energy[b] = np.sqrt(np.mean(chunk**2))

    # Rozprostřít po celém videu s odstupem min 90s
    min_gap = max(60, int((len(energy) - 300) / (target_clips * 1.1)))
    sorted_idx = np.argsort(energy)[::-1]
    chosen = []

    for idx in sorted_idx:
        t = int(idx)
        if t < 90 or t > (len(energy) - 90):
            continue
        if all(abs(t - c) >= min_gap for c in chosen):
            chosen.append(t)
            if len(chosen) >= target_clips:
                break

    chosen.sort()
    print(f"-> Vybráno {len(chosen)} akčních pasáží napříč videem.")

    # 3. Precizní střih s re-encodem na klíčové snímky (žádné záseky ani zelené kostky!)
    print(f"\n[3/4] Stříhám plynulé {clip_dur}s klipy v 9:16 (re-encode bez chyb)...")
    ts = int(time.time())
    saved = 0

    for i, t in enumerate(chosen, 1):
        out_clip = os.path.join(BROLL_DIR, f"new_gameplay_{ts}_{i:03d}.mp4")
        cut_start = max(0, t - 1.0)
        cmd_cut = [
            FFMPEG, "-y",
            "-ss", str(cut_start),
            "-i", source_video,
            "-t", str(clip_dur),
            "-an",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "21",
            "-pix_fmt", "yuv420p",
            out_clip
        ]
        res = subprocess.run(cmd_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0 and os.path.exists(out_clip) and os.path.getsize(out_clip) > 100000:
            saved += 1
            if saved % 10 == 0 or saved == len(chosen):
                print(f"  [+] Hotovo {saved}/{len(chosen)} čistých klipů...")

    # 4. Úklid velkého souboru
    print("\n[4/4] Mažu dočasné zdrojové video z disku...")
    for f in [source_video, source_audio]:
        if os.path.exists(f): os.remove(f)

    print("\n" + "=" * 65)
    print(f"🎉 HOTOVO! Vytvořeno {saved} nových, 100% funkčních 8.5s klipů v {BROLL_DIR}!")
    print("=" * 65)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="https://www.youtube.com/watch?v=BGUTv2K_SWs")
    p.add_argument("--clips", type=int, default=60)
    args = p.parse_args()
    harvest(args.url, target_clips=args.clips)
