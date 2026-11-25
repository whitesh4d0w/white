import os
import sys

# Automatické přepnutí do virtualenvu pokud jsme v systémovém Pythonu
if sys.prefix == sys.base_prefix:
    for venv_path in ["/root/gta6_shorts_bot/venv/bin/python3", "/root/minecraft_stories_bot/venv/bin/python3"]:
        if os.path.exists(venv_path):
            os.execv(venv_path, [venv_path] + sys.argv)

import time
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

def get_authenticated_service():
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(f"token.json pro Story kanál nebyl nalezen v {BASE_DIR}! Spusť nejdříve: python3 auth_youtube.py")
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def verify_channel():
    """Vypíše název kanálu, ke kterému je token autorizován."""
    try:
        yt = get_authenticated_service()
        res = yt.channels().list(mine=True, part="snippet").execute()
        items = res.get("items", [])
        if items:
            title = items[0]["snippet"]["title"]
            cid = items[0]["id"]
            print(f"-> AUTORIZOVÁNO PRO KANÁL: '{title}' (ID: {cid})")
            return title
    except Exception as e:
        print(f"Varování: Nelze ověřit název kanálu ({e})")
    return None

def parse_schedule_time(time_str: str) -> str:
    h, m = map(int, time_str.split(":"))
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo("Europe/Prague")
            now_local = datetime.now(tz)
            sched_local = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
            if sched_local <= now_local:
                sched_local += timedelta(days=1)
            sched_utc = sched_local.astimezone(timezone.utc)
            return sched_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    now = datetime.now()
    sched_local = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if sched_local <= now:
        sched_local += timedelta(days=1)
    sched_utc = sched_local - timedelta(hours=1)
    return sched_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

def upload_short(video_path: str, title: str, description: str = None, privacy: str = "public", schedule: str = None, delete_after: bool = False):
    if not os.path.exists(video_path):
        print(f"Chyba: Video {video_path} neexistuje.")
        return None

    youtube = get_authenticated_service()

    full_title = f"{title} #Shorts" if "#Shorts" not in title and "#shorts" not in title else title
    
    teaser = description or "Insane true story you will not believe!"
    full_desc = (
        f"{teaser}\n\n"
        "🔔 Subscribe for daily insane stories, confessions, and mysteries!\n\n"
        "#StoryTime #RedditStories #MinecraftParkour #ViralStories #Shorts"
    )

    status_dict = {"selfDeclaredMadeForKids": False}
    if schedule:
        status_dict["privacyStatus"] = "private"
        status_dict["publishAt"] = parse_schedule_time(schedule)
        print(f"Plánuji zveřejnění videa na: {schedule} CET ({status_dict['publishAt']})...")
    else:
        status_dict["privacyStatus"] = privacy

    body = {
        "snippet": {
            "title": full_title[:100],
            "description": full_desc,
            "tags": ["StoryTime", "RedditStories", "MinecraftParkour", "Stories", "ViralShorts", "TrueStory", "Shorts"],
            "categoryId": "24"  # Entertainment
        },
        "status": status_dict
    }

    media = MediaFileUpload(video_path, chunksize=1024*1024*4, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"Nahrávám '{full_title}' na YouTube kanál...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"-> Nahráno: {int(status.progress() * 100)}%")

    vid_id = response.get("id")
    vid_url = f"https://youtube.com/shorts/{vid_id}"
    print(f"\nUSPECH! Story video nahráno na 2. kanál: {vid_url}\n")

    if delete_after and os.path.exists(video_path):
        try: os.remove(video_path)
        except Exception: pass

    return vid_url

if __name__ == "__main__":
    verify_channel()
