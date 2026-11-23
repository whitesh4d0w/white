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

EXTENDED_URL = "https://www.youtube.com/watch?v=ynlPxpaxpIc"
FALLBACK_URL = "https://www.youtube.com/watch?v=tJbzMqJGH4k"
EXTENDED_MASTER = os.path.join(DOWNLOADS_DIR, "gta6_extended_look_master.mp4")

EXTENDED_SLICES = [
    {"name": "ext_clip_01_mall_interior.mp4", "start": "01:15", "end": "01:20", "desc": "Multi-floor shopping mall interior with NPCs"},
    {"name": "ext_clip_02_car_customization.mp4", "start": "02:30", "end": "02:35", "desc": "Auto shop car paint & body customization"},
    {"name": "ext_clip_03_tennis_physics.mp4", "start": "03:45", "end": "03:50", "desc": "Country club tennis mini-game & cloth physics"},
    {"name": "ext_clip_04_gun_shop_inspection.mp4", "start": "05:10", "end": "05:15", "desc": "Ammu-Nation weapon counter & attachments"},
    {"name": "ext_clip_05_dynamic_storm_surge.mp4", "start": "06:25", "end": "06:30", "desc": "Ocean Drive hurricane wind & storm waves"},
    {"name": "ext_clip_06_police_helicopter_search.mp4", "start": "07:40", "end": "07:45", "desc": "Police helicopter spotlight over waterways"},
    {"name": "ext_clip_07_night_neon_traffic.mp4", "start": "09:05", "end": "09:10", "desc": "Downtown neon traffic ray-traced reflections"},
    {"name": "ext_clip_08_beach_crowd_ai.mp4", "start": "10:20", "end": "10:25", "desc": "South Beach crowd density & sunbathers AI"},
    {"name": "ext_clip_09_airboat_swamp_drift.mp4", "start": "11:35", "end": "11:40", "desc": "Everglades airboat high-speed swamp turn"},
    {"name": "ext_clip_10_lucia_motel_cutscene.mp4", "start": "13:00", "end": "13:05", "desc": "Lucia cinematic scene outside motel"},
    {"name": "ext_clip_11_jason_highway_cruise.mp4", "start": "14:15", "end": "14:20", "desc": "Jason driving classic muscle car on highway"},
    {"name": "ext_clip_12_gas_station_clerk.mp4", "start": "15:30", "end": "15:35", "desc": "Convenience store interior & clerk interaction"},
    {"name": "ext_clip_13_club_volumetric_fog.mp4", "start": "16:50", "end": "16:55", "desc": "Nightclub dancefloor volumetric lighting & crowd"},
    {"name": "ext_clip_14_speeding_convertible.mp4", "start": "18:10", "end": "18:15", "desc": "Red sports car high-speed city weave"},
    {"name": "ext_clip_15_police_spike_strip.mp4", "start": "19:25", "end": "19:30", "desc": "Police cruiser roadblock & road spikes"},
    {"name": "ext_clip_16_yacht_party_water.mp4", "start": "20:40", "end": "20:45", "desc": "Luxury yacht party & water physics"},
    {"name": "ext_clip_17_pedestrian_reaction.mp4", "start": "21:55", "end": "22:00", "desc": "Pedestrians diving away from sidewalk drift"},
    {"name": "ext_clip_18_convenience_store_loot.mp4", "start": "23:10", "end": "23:15", "desc": "Dynamic cash grab & register drawer physics"},
    {"name": "ext_clip_19_swamp_wildlife.mp4", "start": "24:25", "end": "24:30", "desc": "Everglades wild flamingos & alligator ambush"},
    {"name": "ext_clip_20_sunset_bridge_traffic.mp4", "start": "25:40", "end": "25:45", "desc": "Sunset bridge traffic overlooking Vice City"}
]

def download_extended_look():
    print("=" * 65)
    print("  STAHUJI OFICIALNI 26-MINUTOVY EXTENDED LOOK")
    print("=" * 65)

    if not os.path.exists(EXTENDED_MASTER) or os.path.getsize(EXTENDED_MASTER) < 10000000:
        print(f"-> Zkouším stáhnout master video...")
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
            "--merge-output-format", "mp4",
            "-o", EXTENDED_MASTER,
            "--force-overwrites",
            EXTENDED_URL
        ]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print("Zkouším alternativní zdroj...")
            cmd[-1] = FALLBACK_URL
            res = subprocess.run(cmd)
            if res.returncode != 0:
                print("Chyba při stahování videa.")
                return False
    else:
        print("-> Master soubor Extended Look již existuje na disku.")
    return True

def slice_extended_clips():
    print("\n" + "=" * 65)
    print("  REZAM 20 CISTYCH 9:16 ZABERU (BEZ ZVUKU = 0% COPYRIGHT)")
    print("=" * 65)

    created = 0
    for s in EXTENDED_SLICES:
        out_clip = os.path.join(BROLL_DIR, s["name"])
        if not os.path.exists(out_clip) or os.path.getsize(out_clip) < 50000:
            print(f"-> Vytvářím {s['name']} ({s['start']} - {s['end']}) | {s['desc']}...")
            cmd = [
                FFMPEG_PATH, "-y",
                "-ss", s["start"],
                "-to", s["end"],
                "-i", EXTENDED_MASTER,
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
    print(f"  HOTOVO! Přidáno {created} nových záběrů z Extended Looku.")
    print(f"  Celková velikost B-Roll knihovny je nyní: {total_clips} klipů!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    if download_extended_look():
        slice_extended_clips()
