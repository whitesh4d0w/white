import os
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

CATEGORY_TAGS = {
    "cars": ["GTA 6 Cars", "GTA 6 Vehicles", "GTA 6 Driving"],
    "police": ["GTA 6 Police", "GTA 6 Wanted Level", "GTA 6 Chase"],
    "water": ["GTA 6 Water Physics", "GTA 6 Ocean", "GTA 6 Vice City"],
    "heist": ["GTA 6 Heist", "GTA 6 Robbery", "GTA 6 Combat"],
    "city": ["GTA 6 Vice City", "GTA 6 Map", "GTA 6 Graphics"],
}

def get_authenticated_service():
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError("token.json nebyl nalezen! Ujisti se, ze je token.json ve stejne slozce.")
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def parse_schedule_time(time_str: str) -> str:
    """Prevede '17:00' nebo '21:00' v casove zone Europe/Prague (CET/CEST) na UTC ISO format."""
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

def upload_short(video_path: str, title: str, description: str = None, privacy: str = "public", schedule: str = None, delete_after: bool = True, category: str = None):
    if not os.path.exists(video_path):
        print(f"Chyba: Video {video_path} neexistuje.")
        return None

    youtube = get_authenticated_service()

    full_title = f"{title} #Shorts" if "#Shorts" not in title and "#shorts" not in title else title
    cat_key = (category or "").strip().lower()
    cat_tag_list = CATEGORY_TAGS.get(cat_key, [])
    cat_hashtag = f" #{cat_key.capitalize()}" if cat_key else ""

    teaser = description or "Are you ready for this massive GTA 6 gameplay overhaul? What feature are you most hyped for?"
    full_desc = (
        f"{teaser}\n\n"
        "🔔 Subscribe for daily GTA 6 leaks, secrets, and gameplay details!\n"
        "👍 Drop a LIKE if you are hyped for GTA 6!\n\n"
        f"#GTA6 #GrandTheftAuto #Gaming #RockstarGames{cat_hashtag} #Shorts"
    )

    status_dict = {"selfDeclaredMadeForKids": False}
    if schedule:
        status_dict["privacyStatus"] = "private"
        status_dict["publishAt"] = parse_schedule_time(schedule)
        print(f"Planuji zverejneni videa na: {schedule} Europe/Prague ({status_dict['publishAt']})...")
    else:
        status_dict["privacyStatus"] = privacy

    tags = ["GTA 6", "GTA VI", "Grand Theft Auto", "Gaming", "Shorts", "Rockstar Games"] + cat_tag_list
    body = {
        "snippet": {
            "title": full_title[:100],
            "description": full_desc,
            "tags": tags,
            "categoryId": "20"
        },
        "status": status_dict
    }

    print(f"Nahravam na YouTube: '{full_title}' (Status: {status_dict.get('privacyStatus')})...")
    media = MediaFileUpload(video_path, chunksize=1024*1024*5, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    chunk_retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            chunk_retries = 0
            if status:
                print(f"-> Nahrano: {int(status.progress() * 100)}%")
        except Exception as chunk_err:
            chunk_retries += 1
            if chunk_retries > 3:
                raise
            print(f"⚠️ Docasna chyba uploadu ({chunk_err}), opakuji pokus {chunk_retries}/3...")
            time.sleep(2.0 * chunk_retries)

    vid_id = response.get("id")
    url = f"https://youtu.be/{vid_id}"
    print(f"\n🎉 VIDEO USPESNE NAHRANO!")
    print(f"Odkaz: {url}\n")

    if delete_after and vid_id:
        try:
            os.remove(video_path)
            print(f"Cistim disk: smazano video {os.path.basename(video_path)}.")
        except Exception as e:
            print(f"Varovani: Nepodarilo se smazat video: {e}")

    return url
