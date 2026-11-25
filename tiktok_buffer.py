#!/usr/bin/env python3
"""
tiktok_buffer.py - Automated TikTok Posting via Buffer GraphQL API.
100% Standard Library & System Curl - ZERO PIP DEPENDENCIES NEEDED!
"""

import os
import sys
import json
import urllib.request
import urllib.error
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Načtení .env čistě pomocí standardní knihovny bez nutnosti balíčku 'dotenv'
def load_env_file():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and v:
                            os.environ[k] = v
        except Exception as e:
            print(f"Varování: Nepodařilo se přečíst .env: {e}")

load_env_file()

BUFFER_API_URL = "https://api.buffer.com"


def get_headers():
    load_env_file()
    key = os.getenv("BUFFER_API_KEY", "").strip()
    if not key:
        raise ValueError(f"BUFFER_API_KEY chybí v {BASE_DIR / '.env'}! Přidej ho tam (https://publish.buffer.com/settings/api).")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }


def query_graphql(query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BUFFER_API_URL, data=data_bytes, headers=get_headers(), method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            res_body = resp.read().decode("utf-8")
            data = json.loads(res_body)
            if "errors" in data:
                raise RuntimeError(f"Buffer GraphQL Error: {json.dumps(data['errors'], indent=2)}")
            return data.get("data", {})
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        raise RuntimeError(f"Buffer API HTTP {e.code}: {err_body}")
    except Exception as e:
        raise RuntimeError(f"Chyba spojení s Buffer API: {e}")


def list_buffer_channels():
    """Vrátí všechny připojené sociální kanály v Bufferu."""
    org_query = """
    query GetOrganizations {
      account {
        organizations {
          id
          name
        }
      }
    }
    """
    org_data = query_graphql(org_query)
    organizations = org_data.get("account", {}).get("organizations", [])
    if not organizations:
        raise RuntimeError("V Buffer účtu nebyla nalezena žádná organizace.")

    all_channels = []
    channels_query = """
    query GetChannels($input: ChannelsInput!) {
      channels(input: $input) {
        id
        name
        displayName
        service
        isQueuePaused
      }
    }
    """
    for org in organizations:
        org_id = org["id"]
        ch_data = query_graphql(channels_query, {"input": {"organizationId": org_id}})
        channels = ch_data.get("channels", [])
        for ch in channels:
            ch["organizationId"] = org_id
            all_channels.append(ch)

    return all_channels


def get_tiktok_channel_id(channel_filter: str = None) -> str:
    """Najde správný TikTok kanál."""
    env_ch_id = os.getenv("BUFFER_TIKTOK_CHANNEL_ID", "").strip()
    if env_ch_id and not channel_filter:
        return env_ch_id

    channels = list_buffer_channels()
    tiktok_channels = [ch for ch in channels if ch.get("service") == "tiktok"]

    if not tiktok_channels:
        available = ", ".join([f"{c.get('service')}:{c.get('displayName') or c.get('name')}" for c in channels])
        raise RuntimeError(f"V Bufferu nebyl nalezen žádný TikTok kanál! Dostupné kanály: {available}")

    if channel_filter:
        for ch in tiktok_channels:
            name = (ch.get("displayName") or ch.get("name") or "").lower()
            if channel_filter.lower() in name:
                return ch["id"]

    return tiktok_channels[0]["id"]


def upload_temp_video(video_path: Path) -> str:
    """Nahraje video pomocí spolehlivého multi-hosting řetězce (Catbox -> Litterbox 72h -> tmpfiles -> Uguu)."""
    video_p = Path(video_path).resolve()
    if not video_p.exists():
        raise FileNotFoundError(f"Video neexistuje: {video_p}")

    file_size_mb = video_p.stat().st_size / (1024 * 1024)
    print(f"📦 Nahrávám video ({file_size_mb:.1f} MB) pro veřejný odkaz pro Buffer...")

    # 1. Primární poskytovatel: Catbox.moe (max 200 MB, permanentní přímý MP4 link - nevyprší ve frontě Bufferu)
    try:
        print("  [1/4] Zkouším Catbox.moe...")
        cmd_cat = ["curl", "-s", "--max-time", "120", "-A", "Mozilla/5.0", "-F", "reqtype=fileupload", "-F", f"fileToUpload=@{str(video_p)}", "https://catbox.moe/user/api.php"]
        res = subprocess.run(cmd_cat, capture_output=True, text=True)
        url = res.stdout.strip()
        if res.returncode == 0 and url.startswith("http"):
            print(f"  -> Catbox.moe úspěch: {url}")
            return url
    except Exception as e:
        print(f"  ⚠️ Catbox.moe selhalo: {e}")

    # 2. Záložní poskytovatel 1: Litterbox (max 1 GB, dočasný 72h hosting od Catboxu)
    try:
        print("  [2/4] Zkouším Litterbox (72h)...")
        cmd_lit = ["curl", "-s", "--max-time", "120", "-A", "Mozilla/5.0", "-F", "reqtype=fileupload", "-F", "time=72h", "-F", f"fileToUpload=@{str(video_p)}", "https://litterbox.catbox.moe/resources/internals/api.php"]
        res = subprocess.run(cmd_lit, capture_output=True, text=True)
        url = res.stdout.strip()
        if res.returncode == 0 and url.startswith("http"):
            print(f"  -> Litterbox úspěch: {url}")
            return url
    except Exception as e:
        print(f"  ⚠️ Litterbox selhalo: {e}")

    # 3. Záložní poskytovatel 2: Tmpfiles.org
    try:
        print("  [3/4] Zkouším tmpfiles.org...")
        cmd_tmp = ["curl", "-s", "--max-time", "120", "-F", f"file=@{str(video_p)}", "https://tmpfiles.org/api/v1/upload"]
        res = subprocess.run(cmd_tmp, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout:
            res_json = json.loads(res.stdout)
            if res_json.get("status") == "success":
                direct_url = res_json["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")
                print(f"  -> Tmpfiles.org úspěch: {direct_url}")
                return direct_url
    except Exception as e:
        print(f"  ⚠️ Tmpfiles.org selhalo: {e}")

    # 4. Záložní poskytovatel 3: Uguu.se (max 128 MB, retence jen 3 hodiny - nouzovka)
    try:
        print("  [4/4] Zkouším Uguu.se...")
        cmd_uguu = ["curl", "-s", "--max-time", "90", "-F", f"files[]=@{str(video_p)}", "https://uguu.se/upload.php"]
        res = subprocess.run(cmd_uguu, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip().startswith("{"):
            data = json.loads(res.stdout)
            if data.get("success") and data.get("files"):
                url = data["files"][0]["url"]
                print(f"  -> Uguu.se úspěch: {url}")
                return url
    except Exception as e:
        print(f"  ⚠️ Uguu.se selhalo: {e}")

    raise RuntimeError("Všichni 4 hostingoví poskytovatelé pro Buffer selhali! Zkontroluj internetové připojení.")


def post_video_to_buffer_queue(video_path: str, caption: str, channel_filter: str = None) -> dict:
    """Zařadí video do Buffer fronty pro TikTok."""
    video_p = Path(video_path).resolve()
    channel_id = get_tiktok_channel_id(channel_filter)
    video_url = upload_temp_video(video_p)

    mutation = """
    mutation CreateVideoPost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post {
            id
            dueAt
            status
          }
        }
        ... on MutationError {
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "text": caption,
            "channelId": channel_id,
            "schedulingType": "automatic",
            "mode": "addToQueue",
            "assets": [
                {
                    "video": {
                        "url": video_url,
                    }
                }
            ],
        }
    }

    print(f"🚀 Odesílám video do fronty Bufferu pro kanál {channel_id}...")
    result = query_graphql(mutation, variables)
    create_post = result.get("createPost", {})

    if "message" in create_post:
        raise RuntimeError(f"Buffer odmítl video: {create_post['message']}")

    post_info = create_post.get("post", {})
    post_id = post_info.get("id")
    due_at = post_info.get("dueAt")
    print(f"✅ Video úspěšně zařazeno do Buffer fronty!")
    print(f"   Post ID: {post_id}")
    print(f"   Naplánovaný čas (UTC): {due_at}")
    return post_info


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Buffer TikTok Uploader CLI")
    parser.add_argument("--list-channels", action="store_true", help="Vypíše všechny připojené kanály a jejich ID")
    parser.add_argument("--video", help="Cesta k video souboru")
    parser.add_argument("--caption", default="#Shorts #Viral", help="Popisek videa")
    parser.add_argument("--channel", help="Filtr názvu kanálu (např. 'GTA' nebo 'Minecraft')")

    args = parser.parse_args()

    if args.list_channels:
        print("🔍 Načítám připojené kanály z Bufferu...")
        channels = list_buffer_channels()
        print(f"\nNalezeno {len(channels)} kanálů:")
        for ch in channels:
            print(f"- ID: {ch['id']} | Služba: {ch['service']} | Název: {ch.get('displayName') or ch.get('name')}")
    elif args.video:
        post_video_to_buffer_queue(args.video, args.caption, args.channel)
    else:
        parser.print_help()
