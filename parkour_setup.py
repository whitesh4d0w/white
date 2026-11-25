import os
import sys
import glob
import subprocess
import shutil

# Automatický přechod do venv pokud existuje
_base_dir = os.path.dirname(os.path.abspath(__file__))
_venv_python = os.path.join(_base_dir, "venv", "bin", "python3")
if sys.executable != _venv_python and os.path.exists(_venv_python):
    os.execv(_venv_python, [_venv_python] + sys.argv)

import imageio_ffmpeg

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
PARKOUR_DIR = os.path.join(DOWNLOADS_DIR, "parkour")
MUSIC_DIR = os.path.join(BASE_DIR, "music")

for folder in [DOWNLOADS_DIR, PARKOUR_DIR, MUSIC_DIR]:
    os.makedirs(folder, exist_ok=True)

FFMPEG_PATH = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()

# 2.5hodinový 100% Copyright-Free Minecraft Parkour (2:29:21)
PARKOUR_URL = "https://www.youtube.com/watch?v=85z7jqGAGcc"
PARKOUR_MASTER = os.path.join(DOWNLOADS_DIR, "minecraft_parkour_master.mp4")

STORY_MUSIC_URL = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sneaky%20Adventure.mp3"
STORY_MUSIC_FILE = os.path.join(MUSIC_DIR, "ambient_story_bg.mp3")

def download_parkour():
    print("=" * 65)
    print("  STAHUJI 2.5H MINECRAFT PARKOUR MASTER (COPYRIGHT-FREE)")
    print("=" * 65)
    print(f"URL: {PARKOUR_URL}")
    print(f"Cílový soubor: {PARKOUR_MASTER}\n")

    if not os.path.exists(PARKOUR_MASTER) or os.path.getsize(PARKOUR_MASTER) < 10000000:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
            "--merge-output-format", "mp4",
            "-o", PARKOUR_MASTER,
            "--force-overwrites",
            PARKOUR_URL
        ]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print("Chyba stahování parkour masteru!")
            return False
    else:
        print("-> Master parkour již existuje na disku.")
    return True

def download_ambient_music():
    if not os.path.exists(STORY_MUSIC_FILE):
        print("Stahuji ambientní hudební podkres pro příběhy...")
        try:
            import urllib.request
            urllib.request.urlretrieve(STORY_MUSIC_URL, STORY_MUSIC_FILE)
            print("-> Hudba stažena.")
        except Exception as e:
            print(f"Varování: Hudba se nestáhla: {e}")

def slice_parkour_clips(num_clips: int = 30, clip_dur: int = 55, delete_master: bool = False):
    """
    Vyřeže pestré 55sekundové smyčky napříč celým 2.5hodinovým videem
    (různé biomy: spirálová věž, nether, duhový parkour, ledový svět atd.)
    """
    print("\n" + "=" * 65)
    print(f"  REZAM {num_clips} PESTRYCH CLIPS ({clip_dur}s) PRO STORIES")
    print("=" * 65)

    created = 0
    # Celé video má 2h 29m (cca 8900 s). Rozprostřeme výběr s krokem 280 sekund (každých cca 4.5 minuty)
    step = 280
    start_offset = 60

    for i in range(1, num_clips + 1):
        out_name = f"parkour_clip_{i:02d}.mp4"
        out_clip = os.path.join(PARKOUR_DIR, out_name)
        s_time = start_offset + (i - 1) * step

        if not os.path.exists(out_clip) or os.path.getsize(out_clip) < 50000:
            mins = s_time // 60
            secs = s_time % 60
            print(f"-> Vytvářím {out_name} (čas {mins:02d}:{secs:02d} - {clip_dur}s)...")
            cmd = [
                FFMPEG_PATH, "-y",
                "-ss", str(s_time),
                "-t", str(clip_dur),
                "-i", PARKOUR_MASTER,
                "-an",  # 0% ZVUKU HRY (ČISTÝ VSTUP)
                "-vf", "crop=w=ih*(9/16):h=ih:x=(iw-ow)/2:y=0,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                out_clip
            ]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode == 0:
                created += 1
        else:
            print(f"-> {out_name} již existuje.")

    total_clips = len(glob.glob(os.path.join(PARKOUR_DIR, "*.mp4")))
    print("\n" + "=" * 65)
    print(f"  HOTOVO! Knihovna má nyní {total_clips} parkour záběrů.")
    print("=" * 65)

    if delete_master and os.path.exists(PARKOUR_MASTER):
        try:
            os.remove(PARKOUR_MASTER)
            print("-> Velký 2.5h master byl smazán pro úsporu místa na disku.")
        except Exception: pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips", type=int, default=30, help="Počet klipů k vyřezání (výchozí: 30)")
    parser.add_argument("--delete-master", action="store_true", help="Smazat velký master soubor po vyřezání klipů")
    args = parser.parse_args()

    if download_parkour():
        download_ambient_music()
        slice_parkour_clips(num_clips=args.clips, clip_dur=55, delete_master=args.delete_master)
