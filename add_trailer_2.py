import os
import sys
import glob
import subprocess
import shutil

_base_dir = os.path.dirname(os.path.abspath(__file__))
_venv_python = os.path.join(_base_dir, "venv", "bin", "python3")
if sys.executable != _venv_python and os.path.exists(_venv_python):
    os.execv(_venv_python, [_venv_python] + sys.argv)

import imageio_ffmpeg

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
BROLL_DIR = os.path.join(DOWNLOADS_DIR, "broll")

for folder in [DOWNLOADS_DIR, BROLL_DIR]:
    os.makedirs(folder, exist_ok=True)

FFMPEG_PATH = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()

TRAILER_2_URL = "https://www.youtube.com/watch?v=VQRLujxTm3c"
TRAILER_2_MASTER = os.path.join(DOWNLOADS_DIR, "gta6_trailer_2_master.mp4")

TRAILER_2_SLICES = [
    {"name": "t2_clip_01_jason_lucia_intro.mp4", "start": "00:08", "end": "00:13", "desc": "Jason & Lucia cinematic close-up"},
    {"name": "t2_clip_02_vice_city_skyline.mp4", "start": "00:15", "end": "00:20", "desc": "Vice City golden hour skyline & yachts"},
    {"name": "t2_clip_03_sports_car_drift.mp4", "start": "00:24", "end": "00:29", "desc": "High-speed sports car intersection drift"},
    {"name": "t2_clip_04_port_gellhorn_docks.mp4", "start": "00:32", "end": "00:37", "desc": "Port Gellhorn industrial cranes & ships"},
    {"name": "t2_clip_05_heist_prep_weapons.mp4", "start": "00:40", "end": "00:45", "desc": "Tactical weapons prep & gear inspection"},
    {"name": "t2_clip_06_bank_vault_breach.mp4", "start": "00:48", "end": "00:53", "desc": "Thermite vault door sparks & heat shaders"},
    {"name": "t2_clip_07_highway_police_chase.mp4", "start": "00:56", "end": "01:01", "desc": "Highway police tactical chase & PIT maneuver"},
    {"name": "t2_clip_08_swamp_hovercraft.mp4", "start": "01:05", "end": "01:10", "desc": "Hovercraft speeding across shallow marshland"},
    {"name": "t2_clip_09_strip_club_neon.mp4", "start": "01:14", "end": "01:19", "desc": "Downtown neon club crowd & volumetric lighting"},
    {"name": "t2_clip_10_dirt_track_buggy.mp4", "start": "01:23", "end": "01:28", "desc": "Off-road buggy dirt ramp jump"},
    {"name": "t2_clip_11_motorcycle_escape.mp4", "start": "01:32", "end": "01:37", "desc": "Motorcycle weaving through dense gridlock traffic"},
    {"name": "t2_clip_12_helicopter_spotlight.mp4", "start": "01:42", "end": "01:47", "desc": "Police helicopter searchlight sweeping streets"},
    {"name": "t2_clip_13_luxury_mansion_pool.mp4", "start": "01:52", "end": "01:57", "desc": "Luxury Star Island mansion pool party"},
    {"name": "t2_clip_14_shootout_gas_station.mp4", "start": "02:02", "end": "02:07", "desc": "Gas station tactical shootout & glass physics"},
    {"name": "t2_clip_15_armored_truck_escape.mp4", "start": "02:12", "end": "02:17", "desc": "Armored van ramming through police barricade"},
    {"name": "t2_clip_16_lucia_jason_climax.mp4", "start": "02:22", "end": "02:27", "desc": "Lucia & Jason cinematic climax escape"}
]

def download_trailer_2():
    print("=" * 65)
    print("  STAHUJI OFICIALNI 4K TRAILER 2 OD ROCKSTAR GAMES")
    print("=" * 65)
    if not os.path.exists(TRAILER_2_MASTER) or os.path.getsize(TRAILER_2_MASTER) < 5000000:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
            "--merge-output-format", "mp4",
            "-o", TRAILER_2_MASTER,
            "--force-overwrites",
            TRAILER_2_URL
        ]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print("Chyba stahování Traileru 2!")
            return False
    else:
        print("-> Master soubor Traileru 2 již existuje na disku.")
    return True

def slice_trailer_2_clips():
    print("\n" + "=" * 65)
    print("  REZAM 16 CISTYCH 9:16 ZABERU (BEZ ZVUKU = 0% COPYRIGHT)")
    print("=" * 65)
    created = 0
    for s in TRAILER_2_SLICES:
        out_clip = os.path.join(BROLL_DIR, s["name"])
        if not os.path.exists(out_clip) or os.path.getsize(out_clip) < 50000:
            print(f"-> Vytvářím {s['name']} ({s['start']} - {s['end']}) | {s['desc']}...")
            cmd = [
                FFMPEG_PATH, "-y",
                "-ss", s["start"],
                "-to", s["end"],
                "-i", TRAILER_2_MASTER,
                "-an",
                "-vf", "crop=w=ih*(9/16):h=ih:x=(iw-ow)/2:y=0,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                out_clip
            ]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode == 0:
                created += 1
        else:
            print(f"-> {s['name']} již existuje v broll knihovně.")

    total_clips = len(glob.glob(os.path.join(BROLL_DIR, "*.mp4")))
    print("\n" + "=" * 65)
    print(f"  HOTOVO! Přidáno {created} nových záběrů z Traileru 2.")
    print(f"  Celková velikost B-Roll knihovny je nyní: {total_clips} klipů.")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    if download_trailer_2():
        slice_trailer_2_clips()
