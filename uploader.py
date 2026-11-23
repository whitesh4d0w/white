import os
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")

def get_authenticated_service():
    if not os.path.exists(TOKEN_FILE): raise FileNotFoundError("token.json nebyl nalezen!")
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f: f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def parse_schedule_time(time_str: str) -> str:
    now = datetime.now()
    h, m = map(int, time_str.split(":"))
    sched_local = now.replace(hour=h, minute=m, second=0, microsecond=0)
    sched_utc = sched_local - timedelta(hours=1)
    return sched_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

def upload_short(video_path: str, title: str, description: str = None, privacy: str = "public", schedule: str = None, delete_after: bool = True):
    if not os.path.exists(video_path): return None
    youtube = get_authenticated_service()

    full_title = f"{title} #Shorts" if "#Shorts" not in title and "#shorts" not in title else title
    teaser = description or "Insane GTA 6 leaks and gameplay details you completely missed!"
    full_desc = (
        f"{teaser}\n\n"
        "🔔 Subscribe for daily GTA 6 leaks, secrets, and gameplay details!\n\n"
        "#GTA6 #GrandTheftAuto #Gaming #RockstarGames #Shorts"
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
            "title": full_title[:100], "description": full_desc,
            "tags": ["GTA 6", "GTA VI", "Grand Theft Auto", "Gaming", "Shorts"], "categoryId": "20"
        },
        "status": status_dict
    }

    print(f"Nahrávám na YouTube: '{full_title}' (Status: {status_dict.get('privacyStatus')})...")
    media = MediaFileUpload(video_path, chunksize=1024*1024*5, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status: print(f"-> Nahráno: {int(status.progress() * 100)}%")

    vid_id = response.get("id")
    url = f"https://youtu.be/{vid_id}"
    print(f"\n🎉 VIDEO ÚSPĚŠNĚ NAHRÁNO!\nOdkaz: {url}\n")

    if delete_after and vid_id:
        try: os.remove(video_path); print("Disk uklizen!")
        except Exception: pass
    return url
