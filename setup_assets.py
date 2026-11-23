import os, glob, urllib.request, subprocess
from config import DOWNLOADS_DIR, BROLL_DIR, MUSIC_DIR, FFMPEG_PATH

MUSIC_TRACKS = [
    {"filename": "track_01_newer_wave.mp3", "url": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Newer%20Wave.mp3", "name": "Newer Wave (80s Synthwave)"},
    {"filename": "track_02_equatorial.mp3", "url": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Equatorial%20Complex.mp3", "name": "Equatorial Complex (Dark Synth)"},
    {"filename": "track_03_kick_shock.mp3", "url": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Kick%20Shock.mp3", "name": "Kick Shock (Action Drive)"}
]

BROLL_SLICES = [
    {"name": "clip_01_ocean_speedboats.mp4", "start": "00:04", "end": "00:09"},
    {"name": "clip_02_beach_drones.mp4", "start": "00:09", "end": "00:14"},
    {"name": "clip_03_flamingos_highway.mp4", "start": "00:14", "end": "00:18"},
    {"name": "clip_04_bridge_to_city.mp4", "start": "00:18", "end": "00:22"},
    {"name": "clip_05_everglades_airboat.mp4", "start": "00:22", "end": "00:26"},
    {"name": "clip_06_rooftop_pool.mp4", "start": "00:26", "end": "00:30"},
    {"name": "clip_07_ocean_drive_neon.mp4", "start": "00:48", "end": "00:52"},
    {"name": "clip_08_lowriders_meet.mp4", "start": "00:52", "end": "00:56"},
    {"name": "clip_09_thrillbilly_mud.mp4", "start": "01:04", "end": "01:08"},
    {"name": "clip_10_dirtbikes_gang.mp4", "start": "01:08", "end": "01:12"},
    {"name": "clip_11_police_sirens.mp4", "start": "01:12", "end": "01:16"},
    {"name": "clip_12_nightclub_party.mp4", "start": "01:16", "end": "01:20"},
    {"name": "clip_13_convertible_cruise.mp4", "start": "01:20", "end": "01:24"},
    {"name": "clip_14_store_robbery.mp4", "start": "01:24", "end": "01:28"}
]

print("\n[1/2] Stahuji 3 bezpecne royalty-free skladby...")
for t in MUSIC_TRACKS:
    target = os.path.join(MUSIC_DIR, t["filename"])
    if not os.path.exists(target):
        print(f"-> {t['name']}...")
        urllib.request.urlretrieve(t["url"], target)

print("\n[2/2] Pripravuji knihovnu 14 zaberu bez zvuku...")
master_trailer = os.path.join(DOWNLOADS_DIR, "gta6_master_trailer.mp4")
if not os.path.exists(master_trailer) or os.path.getsize(master_trailer) < 5000000:
    clean_exist = os.path.join(DOWNLOADS_DIR, "gta6_clean_gameplay.mp4")
    if os.path.exists(clean_exist) and os.path.getsize(clean_exist) > 10000000:
        master_trailer = clean_exist
    else:
        print("-> Stahuji jednou oficialni 4K Trailer 1...")
        cmd = ["python3", "-m", "yt_dlp", "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best", "--merge-output-format", "mp4", "-o", master_trailer, "--force-overwrites", "https://www.youtube.com/watch?v=QdBZY2fkU-0"]
        subprocess.run(cmd)

for s in BROLL_SLICES:
    out_clip = os.path.join(BROLL_DIR, s["name"])
    if not os.path.exists(out_clip) or os.path.getsize(out_clip) < 50000:
        print(f"-> Vyrezavam {s['name']} (bez zvuku)...")
        cmd = [FFMPEG_PATH, "-y", "-ss", s["start"], "-to", s["end"], "-i", master_trailer, "-an", "-vf", "crop=w=ih*(9/16):h=ih:x=(iw-ow)/2:y=0,scale=1080:1920", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", out_clip]
        subprocess.run(cmd, capture_output=True)

print(f"\nHOTOVO! Knihovna ma {len(glob.glob(os.path.join(BROLL_DIR, '*.mp4')))} zaberu a 3 bezpecne hudebni podkresy.\n")
