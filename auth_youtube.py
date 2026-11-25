import os
import sys

_base_dir = os.path.dirname(os.path.abspath(__file__))
_venv_python = os.path.join(_base_dir, "venv", "bin", "python3")
if sys.executable != _venv_python and os.path.exists(_venv_python):
    os.execv(_venv_python, [_venv_python] + sys.argv)

from google_auth_oauthlib.flow import InstalledAppFlow
from uploader import verify_channel

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

def main():
    if not os.path.exists(CLIENT_SECRET_FILE):
        # Zkusit zkopírovat z gta6 bota pokud existuje
        gta6_secret = os.path.join(os.path.dirname(BASE_DIR), "gta6_shorts_bot", "client_secret.json")
        if os.path.exists(gta6_secret):
            import shutil
            shutil.copy(gta6_secret, CLIENT_SECRET_FILE)
            print(f"-> client_secret.json automaticky zkopírován z gta6_shorts_bot.")
        else:
            print(f"Chyba: {CLIENT_SECRET_FILE} nebyl nalezen! Nahraj client_secret.json do této složky.", flush=True)
            return

    print("=" * 65)
    print("  AUTORIZACE YOUTUBE PRO 2. KANAL (MINECRAFT STORIES)")
    print("=" * 65)
    print("Při přihlašování v prohlížeči Google zobrazí seznam tvých kanálů.")
    print("DŮLEŽITÉ: Vyber tvůj DRUHÝ kanál (pro Minecraft Stories)!\n")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(
        port=8080,
        open_browser=True,
        authorization_prompt_message="Klikni na tento odkaz v prohlížeči pro autorizaci 2. kanálu:\n{url}\n"
    )

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print(f"\n[+] ÚSPĚCH! Token pro 2. kanál uložen do: {TOKEN_FILE}\n")
    verify_channel()
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
