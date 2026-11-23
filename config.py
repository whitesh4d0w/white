import os, shutil, imageio_ffmpeg
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
BROLL_DIR = os.path.join(DOWNLOADS_DIR, "broll")
MUSIC_DIR = os.path.join(BASE_DIR, "music")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
for folder in [DOWNLOADS_DIR, BROLL_DIR, MUSIC_DIR, TEMP_DIR, OUTPUT_DIR]:
    os.makedirs(folder, exist_ok=True)
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and v: os.environ.setdefault(k, v)
    except Exception: pass
FFMPEG_PATH = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
FONT_NAME, FONT_SIZE = "Impact", 64
PRIMARY_COLOR, SECONDARY_COLOR = "&H0000FFFF", "&H00FFFFFF"
OUTLINE_COLOR, OUTLINE_WIDTH, MARGIN_VERTICAL = "&H00000000", 5, 450
TARGET_WIDTH, TARGET_HEIGHT, FPS = 1080, 1920, 30
MUSIC_VOLUME = 0.08
GAMEPLAY_VOLUME = 0.15
