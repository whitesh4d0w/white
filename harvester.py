import warnings
warnings.filterwarnings("ignore")

import os
import sys
import glob
import math
import time
import random
import argparse
import subprocess
import shutil

# Automatická kontrola a doinstalace OpenCV headless & yt-dlp
try:
    import cv2
    import numpy as np
except ImportError:
    print("Instaluji opencv-python-headless pro AI detekci cisteho obrazu...")
    subprocess.run([sys.executable, "-m", "pip", "install", "opencv-python-headless", "numpy", "-q"])
    import cv2
    import numpy as np

try:
    import yt_dlp
except ImportError:
    print("Instaluji yt-dlp...")
    subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp", "-q"])
    import yt_dlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
INBOX_DIR = os.path.join(DOWNLOADS_DIR, "inbox")
ARCHIVE_DIR = os.path.join(INBOX_DIR, "archive")
BROLL_DIR = os.path.join(DOWNLOADS_DIR, "broll")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

for folder in [DOWNLOADS_DIR, INBOX_DIR, ARCHIVE_DIR, BROLL_DIR, TEMP_DIR]:
    os.makedirs(folder, exist_ok=True)

import imageio_ffmpeg
FFMPEG_PATH = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()

def get_face_detector():
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    if os.path.exists(cascade_path):
        return cv2.CascadeClassifier(cascade_path)
    return None

FACE_DETECTOR = get_face_detector()

def inspect_clip_cleanliness(video_path: str, start_sec: float, dur: float = 4.5) -> tuple[bool, str]:
    """
    OpenCV Analýza čistoty záběru:
    1. Ořez na 9:16 střed (odstraní postranní webkamery a chat).
    2. Detekce tmy / loading screenu.
    3. Detekce obličeje streamera (Haar Cascade).
    4. Detekce pohybu (vynechá pauzy, inventář a statické menu).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False, "Nelze otevřít video"

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    total_duration = total_frames / fps if fps > 0 else 0

    if start_sec + dur > total_duration:
        cap.release()
        return False, "Mimo rozsah videa"

    sample_offsets = [1.0, 2.5, 4.0]
    frames = []

    for off in sample_offsets:
        target_sec = start_sec + off
        cap.set(cv2.CAP_PROP_POS_MSEC, target_sec * 1000.0)
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)

    cap.release()

    if len(frames) < 2:
        return False, "Nedostatek snímků"

    h, w, _ = frames[0].shape
    crop_w = int(h * (9 / 16))
    if crop_w >= w:
        return False, "Neplatný poměr stran"
    x_start = max(0, (w - crop_w) // 2)

    center_crops = [f[:, x_start:x_start + crop_w] for f in frames]

    # 1. Kontrola jasu (tma / loading)
    mean_bright = np.mean(cv2.cvtColor(center_crops[0], cv2.COLOR_BGR2GRAY))
    if mean_bright < 18.0:
        return False, f"Tmavá scéna / loading (jas: {mean_bright:.1f})"

    # 2. Detekce obličeje (webkamera streamera v záběru)
    if FACE_DETECTOR:
        for crop in center_crops:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            faces = FACE_DETECTOR.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(50, 50))
            if len(faces) > 0:
                return False, "Detekován obličej streamera v záběru"

    # 3. Pohyb scény (odfiltruje pauzu, menu nebo mapu)
    gray_a = cv2.cvtColor(center_crops[0], cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(center_crops[-1], cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray_a, gray_b)
    motion_score = np.mean(diff)

    if motion_score < 4.0:
        return False, f"Statická scéna / menu (motion: {motion_score:.1f})"

    return True, "Čistý herní záběr"

def slice_clean_clip(input_video: str, start_sec: float, dur: float, output_clip_path: str) -> bool:
    """
    Vyřízne 9:16 vertikální klip bez zvuku (-an) v rozlišení 1080x1920
    """
    cmd = [
        FFMPEG_PATH, "-y",
        "-ss", f"{start_sec:.2f}",
        "-t", f"{dur:.2f}",
        "-i", input_video,
        "-an",  # 0% PŮVODNÍHO ZVUKU = ŽÁDNÝ COPYRIGHT CLAIM
        "-vf", "crop=w=ih*(9/16):h=ih:x=(iw-ow)/2:y=(ih-oh)/2,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        output_clip_path
    ]
    res = subprocess.run(cmd, capture_output=True)
    return res.returncode == 0 and os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 100000

def process_video_into_broll(video_path: str, max_clips: int = 15, clip_dur: float = 4.5) -> int:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Nelze otevřít: {video_path}")
        return 0

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    total_dur = total_frames / fps if fps > 0 else 0
    cap.release()

    base_name = os.path.splitext(os.path.basename(video_path))[0]
    safe_name = "".join(c for c in base_name if c.isalnum() or c in ("_", "-"))[:25]

    print(f"\n--- Analyzuji video: {os.path.basename(video_path)} ({total_dur/60:.1f} min) ---")

    start_pos = 15.0  # Přeskočit YouTube intro
    end_pos = max(start_pos + 10.0, total_dur - 20.0)  # Přeskočit outro

    step = max(clip_dur + 2.0, (end_pos - start_pos) / (max_clips * 2.5))
    curr_time = start_pos
    extracted = 0

    while curr_time + clip_dur < end_pos and extracted < max_clips:
        is_clean, reason = inspect_clip_cleanliness(video_path, curr_time, clip_dur)
        if is_clean:
            ts_str = f"{int(curr_time):04d}"
            out_clip = os.path.join(BROLL_DIR, f"clip_harv_{safe_name}_{ts_str}.mp4")
            if not os.path.exists(out_clip):
                if slice_clean_clip(video_path, curr_time, clip_dur, out_clip):
                    extracted += 1
                    print(f"  [+] Klip {extracted}/{max_clips} uložen: {os.path.basename(out_clip)} ({curr_time/60:.2f} min)")
                    curr_time += clip_dur + 3.0
                    continue

        curr_time += step

    print(f"-> Dokončeno! Vyextrahováno {extracted} čistých záběrů.")
    return extracted

def download_youtube_url(url: str, output_dir: str = INBOX_DIR) -> str:
    print(f"\nStahuji video z URL do {output_dir}...")
    out_tmpl = os.path.join(output_dir, "%(title).60s_%(id)s.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", out_tmpl,
        url
    ]
    subprocess.run(cmd)

    files = glob.glob(os.path.join(output_dir, "*.mp4"))
    if files:
        files.sort(key=os.path.getmtime, reverse=True)
        return files[0]
    return None

def search_youtube_and_download(query: str, limit: int = 2, output_dir: str = INBOX_DIR) -> list:
    print(f"\n[Vyhledávání] Hledám top {limit} videí pro: '{query}'...")
    out_tmpl = os.path.join(output_dir, "%(title).60s_%(id)s.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        f"ytsearch{limit}:{query}",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--match-filter", "duration >= 60 & duration <= 1200",
        "--no-playlist",
        "-o", out_tmpl
    ]
    subprocess.run(cmd)
    return glob.glob(os.path.join(output_dir, "*.mp4"))

def process_inbox(max_clips: int = 15, delete_raw: bool = False):
    videos = [v for v in glob.glob(os.path.join(INBOX_DIR, "*.mp4")) if not os.path.isdir(v)]
    if not videos:
        print(f"Složka {INBOX_DIR} je prázdná. Žádná nová videa ke zpracování.")
        return

    print(f"\nNalezeno {len(videos)} videí v inboxu ke zpracování.")
    total_added = 0
    for v in videos:
        count = process_video_into_broll(v, max_clips=max_clips)
        total_added += count
        if delete_raw:
            try: os.remove(v); print(f"  [!] Původní master smazán: {os.path.basename(v)}")
            except Exception: pass
        else:
            archived = os.path.join(ARCHIVE_DIR, os.path.basename(v))
            try: shutil.move(v, archived); print(f"  [>] Přesunuto do archivu: {os.path.basename(v)}")
            except Exception: pass

    print(f"\n=== HOTOVO! Celkem přidáno {total_added} nových klipů do knihovny. ===")

def print_stats():
    clips = glob.glob(os.path.join(BROLL_DIR, "*.mp4"))
    total_sec = 0.0
    for c in clips:
        try:
            cap = cv2.VideoCapture(c)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            total_sec += (frames / fps)
            cap.release()
        except Exception: pass

    print("\n" + "=" * 55)
    print("  STAV B-ROLL KNIHOVNY PRO AUTONOMNÍ BOT")
    print("=" * 55)
    print(f" Celkem připravených záběrů: {len(clips)} klipů")
    print(f" Celková délka knihovny:     {total_sec / 60:.1f} minut ({total_sec:.0f} s)")
    print(f" Složka:                     {BROLL_DIR}")
    print("=" * 55 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GTA 6 Smart Gameplay Harvester & Cleaner")
    parser.add_argument("--url", help="Stáhnout a okamžitě zpracovat konkrétní YouTube video")
    parser.add_argument("--search", help="Vyhledat na YouTube (např. 'GTA 6 gameplay 4K no commentary')")
    parser.add_argument("--limit", type=int, default=2, help="Počet videí k vyhledání (výchozí: 2)")
    parser.add_argument("--process-inbox", action="store_true", help="Zpracovat všechna videa čekající v downloads/inbox/")
    parser.add_argument("--clips-per-video", type=int, default=15, help="Kolik klipů vyříznout z každého videa (výchozí: 15)")
    parser.add_argument("--delete-raw", action="store_true", help="Smazat původní velká videa po vyřezání klipů")
    parser.add_argument("--stats", action="store_true", help="Zobrazit statistiky B-roll knihovny")

    args = parser.parse_args()

    if args.stats:
        print_stats()
    elif args.url:
        vid = download_youtube_url(args.url)
        if vid:
            process_video_into_broll(vid, max_clips=args.clips_per_video)
            if args.delete_raw:
                try: os.remove(vid)
                except Exception: pass
            else:
                shutil.move(vid, os.path.join(ARCHIVE_DIR, os.path.basename(vid)))
        print_stats()
    elif args.search:
        search_youtube_and_download(args.search, limit=args.limit)
        process_inbox(max_clips=args.clips_per_video, delete_raw=args.delete_raw)
        print_stats()
    elif args.process_inbox:
        process_inbox(max_clips=args.clips_per_video, delete_raw=args.delete_raw)
        print_stats()
    else:
        parser.print_help()
