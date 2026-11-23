import os
import sys
import math
import time
import argparse
import subprocess
import glob
import shutil

# Automatická kontrola a instalace prerekvizit
try:
    import numpy as np
except ImportError:
    print("Inštalujem numpy...")
    subprocess.run([sys.executable, "-m", "pip", "install", "numpy", "-q"])
    import numpy as np

try:
    import yt_dlp
except ImportError:
    print("Inštalujem yt-dlp...")
    subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp", "-q"])
    import yt_dlp

FFMPEG_BIN = shutil.which("ffmpeg")
if not FFMPEG_BIN:
    try:
        import imageio_ffmpeg
        FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "imageio-ffmpeg", "-q"])
        import imageio_ffmpeg
        FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
BROLL_DIR = os.path.join(DOWNLOADS_DIR, "broll")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

os.makedirs(BROLL_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

def harvest_gameplay(url: str, target_clips: int = 180, clip_duration: float = 4.0):
    print("=" * 65)
    print("🎬 B-ROLL HARVESTER: Autonomní těžba akčních scén")
    print(f"URL: {url}")
    print(f"Cílový počet klipů: {target_clips} (délka: {clip_duration}s)")
    print("=" * 65)

    source_video = os.path.join(TEMP_DIR, "source_gameplay.mp4")
    source_audio = os.path.join(TEMP_DIR, "source_audio.wav")

    # 1. Stažení v 1080p
    print("\n[1/4] Stahuji 1080p video z YouTube (může trvat pár minut)...")
    cmd_dl = [
        sys.executable, "-m", "yt_dlp",
        "--ffmpeg-location", FFMPEG_BIN,
        "-f", "137+140/399+140/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--merge-output-format", "mp4",
        "-o", source_video,
        "--force-overwrites",
        url
    ]
    subprocess.run(cmd_dl, check=True)
    size_gb = os.path.getsize(source_video) / (1024 * 1024 * 1024)
    print(f"-> Video staženo: {size_gb:.2f} GB")

    # 2. Rychlá extrakce odlehčeného 1kHz audia pro bleskovou analýzu (šetří RAM)
    print("\n[2/4] Analyzuji zvukovou stopu na výbuchy, střelbu a honičky...")
    cmd_audio = [
        FFMPEG_BIN, "-y", "-i", source_video,
        "-vn", "-ar", "1000", "-ac", "1", "-f", "wav",
        source_audio
    ]
    subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Hledání akčních špiček v NumPy
    raw_data = np.fromfile(source_audio, dtype=np.int16, offset=44)
    block_size = 1000  # 1000 vzorků = přesně 1 sekunda
    num_blocks = len(raw_data) // block_size
    energy = np.zeros(num_blocks)
    for b in range(num_blocks):
        chunk = raw_data[b * block_size : (b + 1) * block_size].astype(float)
        energy[b] = np.sqrt(np.mean(chunk**2))

    # Hledáme špičky rozestoupené rovnoměrně po celém gameplayi
    min_gap = max(30, int((num_blocks - 300) / (target_clips * 1.1)))
    sorted_indices = np.argsort(energy)[::-1]
    chosen_timestamps = []

    while len(chosen_timestamps) < target_clips and min_gap >= 25:
        chosen_timestamps = []
        for idx in sorted_indices:
            t_sec = int(idx)
            # Ignorujeme úvodních 90s (loga) a konec videa
            if t_sec < 90 or t_sec > (num_blocks - 90):
                continue
            if all(abs(t_sec - c) >= min_gap for c in chosen_timestamps):
                chosen_timestamps.append(t_sec)
                if len(chosen_timestamps) >= target_clips:
                    break
        if len(chosen_timestamps) < target_clips:
            min_gap = int(min_gap * 0.8)

    chosen_timestamps.sort()
    print(f"-> Nalezeno {len(chosen_timestamps)} akčních momentů napříč celým gameplayem (rozestup min ~{min_gap}s)!")

    # 4. Bezztrátový střih přímo do B-rollu (-c:v copy -an = 0% audia, blesková rychlost)
    print(f"\n[3/4] Provádím chirurgický bezztrátový střih {len(chosen_timestamps)} klipů (stream copy)...")
    ts_now = int(time.time())
    saved_count = 0

    for i, t in enumerate(chosen_timestamps, start=1):
        out_clip = os.path.join(BROLL_DIR, f"action_gameplay_{ts_now}_{i:03d}.mp4")
        cut_start = max(0, t - 1.0)
        cmd_cut = [
            FFMPEG_BIN, "-y",
            "-ss", str(cut_start),
            "-i", source_video,
            "-t", str(clip_duration),
            "-c:v", "copy",
            "-an",
            out_clip
        ]
        res = subprocess.run(cmd_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0 and os.path.exists(out_clip) and os.path.getsize(out_clip) > 50000:
            saved_count += 1
            if saved_count % 20 == 0 or saved_count == len(chosen_timestamps):
                h = int(cut_start // 3600)
                m = int((cut_start % 3600) // 60)
                s = int(cut_start % 60)
                print(f"  [+] Vyříznuto {saved_count:03d}/{len(chosen_timestamps)} klipů (aktuální pozice: {h:02d}:{m:02d}:{s:02d})")

    # 5. Úklid velkých dočasných souborů
    print("\n[4/4] Čistím disk od velkého zdrojového videa...")
    if os.path.exists(source_video): os.remove(source_video)
    if os.path.exists(source_audio): os.remove(source_audio)

    print("\n" + "=" * 65)
    print(f"🎉 HOTOVO! Úspěšně vytvořeno {saved_count} nových akčních B-roll klipů v {BROLL_DIR}!")
    print("=" * 65)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="YouTube video URL")
    p.add_argument("--clips", type=int, default=180, help="Počet klipů k vyřezání")
    p.add_argument("--duration", type=float, default=4.0, help="Délka každého klipu v sekundách")
    args = p.parse_args()
    harvest_gameplay(args.url, target_clips=args.clips, clip_duration=args.duration)
