#!/usr/bin/env python3
import os, sys, json, urllib.request, urllib.error, subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def load_env_file():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and v: os.environ[k] = v
        except Exception as e:
            print(f"Varování .env: {e}")

load_env_file()
BUFFER_API_URL = "https://api.buffer.com"

def get_headers():
    load_env_file()
    key = os.getenv("BUFFER_API_KEY", "").strip()
    if not key:
        raise ValueError("BUFFER_API_KEY chybí v .env!")
    return {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}

def query_graphql(query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables: payload["variables"] = variables
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BUFFER_API_URL, data=data_bytes, headers=get_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "errors" in data:
                raise RuntimeError(f"Buffer GraphQL Error: {json.dumps(data['errors'], indent=2)}")
            return data.get("data", {})
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Buffer HTTP {e.code}: {e.read().decode('utf-8')}")
    except Exception as e:
        raise RuntimeError(f"Chyba spojení s Bufferem: {e}")

def list_buffer_channels():
    org_query = "query { account { organizations { id name } } }"
    orgs = query_graphql(org_query).get("account", {}).get("organizations", [])
    if not orgs: raise RuntimeError("V Buffer účtu nebyla nalezena organizace.")
    channels_query = "query($input: ChannelsInput!) { channels(input: $input) { id name displayName service isQueuePaused } }"
    all_ch = []
    for org in orgs:
        ch_data = query_graphql(channels_query, {"input": {"organizationId": org["id"]}})
        for ch in ch_data.get("channels", []):
            ch["organizationId"] = org["id"]
            all_ch.append(ch)
    return all_ch

def get_tiktok_channel_id(channel_filter: str = None) -> str:
    env_id = os.getenv("BUFFER_TIKTOK_CHANNEL_ID", "").strip()
    if env_id and not channel_filter: return env_id
    channels = list_buffer_channels()
    tt = [c for c in channels if c.get("service") == "tiktok"]
    if not tt: raise RuntimeError("V Bufferu nebyl nalezen žádný TikTok kanál!")
    if channel_filter:
        for c in tt:
            if channel_filter.lower() in (c.get("displayName") or c.get("name") or "").lower():
                return c["id"]
    return tt[0]["id"]

def upload_temp_video(video_path: Path) -> str:
    video_p = Path(video_path).resolve()
    if not video_p.exists(): raise FileNotFoundError(f"Video neexistuje: {video_p}")
    size_mb = video_p.stat().st_size / (1024 * 1024)
    print(f"📦 Nahrávám video ({size_mb:.1f} MB) pro Buffer...")

    # 1. Primární: Uguu.se (rychlý, přímý MP4 stream, max 128 MB, retence 3h)
    try:
        print("  [1/4] Zkouším Uguu.se...")
        cmd = ["curl", "-s", "--max-time", "90", "-F", f"files[]=@{str(video_p)}", "https://uguu.se/upload.php"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip().startswith("{"):
            d = json.loads(res.stdout)
            if d.get("success") and d.get("files"):
                url = d["files"][0]["url"]
                print(f"  -> Uguu.se úspěch: {url}")
                return url
    except Exception as e:
        print(f"  ⚠️ Uguu.se selhalo: {e}")

    # 2. Záloha 1: Catbox.moe (max 200 MB, trvalý přímý link)
    try:
        print("  [2/4] Zkouším Catbox.moe...")
        cmd = ["curl", "-s", "--max-time", "120", "-A", "Mozilla/5.0", "-F", "reqtype=fileupload", "-F", f"fileToUpload=@{str(video_p)}", "https://catbox.moe/user/api.php"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        url = res.stdout.strip()
        if res.returncode == 0 and url.startswith("http"):
            print(f"  -> Catbox.moe úspěch: {url}")
            return url
    except Exception as e:
        print(f"  ⚠️ Catbox.moe selhalo: {e}")

    # 3. Záloha 2: Litterbox (dočasný Catbox fallback)
    try:
        print("  [3/4] Zkouším Litterbox...")
        cmd = ["curl", "-s", "--max-time", "120", "-A", "Mozilla/5.0", "-F", "reqtype=fileupload", "-F", "time=1h", "-F", f"fileToUpload=@{str(video_p)}", "https://litterbox.catbox.moe/resources/internals/api.php"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        url = res.stdout.strip()
        if res.returncode == 0 and url.startswith("http"):
            print(f"  -> Litterbox úspěch: {url}")
            return url
    except Exception as e:
        print(f"  ⚠️ Litterbox selhalo: {e}")

    # 4. Záloha 3: Tmpfiles.org
    try:
        print("  [4/4] Zkouším tmpfiles.org...")
        cmd = ["curl", "-s", "--max-time", "120", "-F", f"file=@{str(video_p)}", "https://tmpfiles.org/api/v1/upload"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout:
            d = json.loads(res.stdout)
            if d.get("status") == "success":
                url = d["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")
                print(f"  -> Tmpfiles.org úspěch: {url}")
                return url
    except Exception as e:
        print(f"  ⚠️ Tmpfiles.org selhalo: {e}")

    raise RuntimeError("Všichni 4 hostingoví poskytovatelé selhali!")

def post_video_to_buffer_queue(video_path: str, caption: str, channel_filter: str = None) -> dict:
    video_p = Path(video_path).resolve()
    channel_id = get_tiktok_channel_id(channel_filter)
    video_url = upload_temp_video(video_p)

    mutation = """
    mutation CreateVideoPost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post { id dueAt status }
        }
        ... on MutationError { message }
      }
    }
    """
    variables = {
        "input": {
            "text": caption,
            "channelId": channel_id,
            "schedulingType": "automatic",
            "mode": "addToQueue",
            "assets": [{"video": {"url": video_url}}]
        }
    }
    print(f"🚀 Zařazuji video do Buffer fronty pro kanál {channel_id}...")
    result = query_graphql(mutation, variables)
    create_post = result.get("createPost", {})
    if "message" in create_post:
        raise RuntimeError(f"Buffer odmítl video: {create_post['message']}")
    post_info = create_post.get("post", {})
    print(f"✅ Video úspěšně zařazeno do Buffer fronty! Post ID: {post_info.get('id')}")
    return post_info

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--list-channels", action="store_true")
    p.add_argument("--video")
    p.add_argument("--caption", default="#Shorts #Viral")
    p.add_argument("--channel")
    args = p.parse_args()
    if args.list_channels:
        chs = list_buffer_channels()
        print(f"Nalezeno {len(chs)} kanálů:")
        for c in chs: print(f"- ID: {c['id']} | Služba: {c['service']} | Název: {c.get('displayName') or c.get('name')}")
    elif args.video:
        post_video_to_buffer_queue(args.video, args.caption, args.channel)
    else:
        p.print_help()
