import sys
import os

# Automatický přechod do venv, i když uživatel spustí skript přes systémový python3
if sys.prefix == sys.base_prefix:
    for venv_path in ["/root/gta6_shorts_bot/venv/bin/python3", "/root/minecraft_stories_bot/venv/bin/python3"]:
        if os.path.exists(venv_path):
            os.execv(venv_path, [venv_path] + sys.argv)

import warnings
warnings.filterwarnings("ignore")
import glob
import math
import json
import random
import re
import argparse
import subprocess
import time
import asyncio
import urllib.request
from datetime import datetime

from google import genai
from google.genai import types
from whisper_engine import transcribe_and_make_subtitles
from sfx_engine import build_sfx_track
from uploader import upload_short

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
BROLL_DIR = os.path.join(DOWNLOADS_DIR, "broll")
MUSIC_DIR = os.path.join(BASE_DIR, "music")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")

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

import shutil, imageio_ffmpeg
FFMPEG_PATH = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()

SAFE_MUSIC_URL = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Newer%20Wave.mp3"
SAFE_MUSIC_FILE = os.path.join(MUSIC_DIR, "track_01_newer_wave.mp3")

TEXT_MODELS = [
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
    "gemini-2.0-pro-exp-02-05"
]

TTS_MODELS = [
    "gemini-3.8-flash-tts",
    "gemini-3.8-flash-lite-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-pro-preview-tts",
    "gemini-2.5-flash-preview-tts"
]

try:
    from offline_topics import OFFLINE_NEWS_TOPICS
except ImportError:
    OFFLINE_NEWS_TOPICS = []

BREAKDOWN_SCENES = [
    {
        "clip_name": "ext_clip_10_lucia_motel_cutscene.mp4",
        "title": "GTA 6 Lucia Prison Opening Breakdown",
        "category": "city",
        "focus": "Volumetric sunbeams through barred window, facial skin pores, and depth-of-field realism",
        "hooks": ["Look closely at Lucia's face in the very first scene of GTA 6!"],
        "facts": [
            "Notice how the sunlight realistically illuminates individual facial hairs and micro-blemishes on her skin.",
            "The background guard tower blurs out with authentic physical camera depth-of-field, showing off Rockstar's brand new rendering engine."
        ],
        "question": "Is this the most realistic character model in gaming history? Tell me below!",
        "description": "Breaking down the incredible lighting and skin shaders in Lucia's prison scene from GTA 6 Trailer 1. Did you notice this detail? 👇"
    },
    {
        "clip_name": "clip_07_ocean_drive_neon.mp4",
        "title": "GTA 6 Ocean Drive Ray-Tracing Secret",
        "category": "city",
        "focus": "Ray-traced curb puddle reflections and dynamic multi-colored pedestrian shadows",
        "hooks": ["You completely missed this insane lighting detail on Ocean Drive in GTA 6!"],
        "facts": [
            "Look right at the water puddles along the curb: every neon hotel sign is reflecting dynamically with accurate surface ripples.",
            "Every NPC on the sidewalk casts multiple distinct colored shadows depending on how many neon lights illuminate them."
        ],
        "question": "Is GTA 6 visually the biggest generational leap in gaming history? Let me know!",
        "description": "Vice City's neon night lighting shows off Rockstar's brand new ray-tracing engine. Did you spot the puddle reflections? 👇"
    },
    {
        "clip_name": "clip_14_store_robbery.mp4",
        "title": "GTA 6 Store Robbery AI Breakdown",
        "category": "city",
        "focus": "Store clerk panic button reach and dynamic dual-protagonist cover coordination",
        "hooks": ["Stop scrolling and look at what the store clerk does in this GTA 6 clip!"],
        "facts": [
            "Notice how the clerk actively reaches under the register for a silent panic button while raising his hands.",
            "Lucia dynamically covers the door while Jason bags the cash, proving dynamic dual-protagonist AI coordination during crimes."
        ],
        "question": "What is the very first store you are robbing in Vice City? Comment down below!",
        "description": "The dynamic robbery mechanics in GTA 6 are way deeper than GTA 5. Did you notice the clerk reaching? 👇"
    },
    {
        "clip_name": "clip_05_everglades_airboat.mp4",
        "title": "GTA 6 Everglades Wildlife Secret",
        "category": "water",
        "focus": "Stalking alligator ambush reaction and dynamic propeller wake bending swamp reeds",
        "hooks": ["Watch the water on the left side of this GTA 6 swamp clip very carefully!"],
        "facts": [
            "An alligator actually stalks the airboat and ducks beneath the surface right before the propeller wake hits.",
            "Rockstar built independent water wake physics that dynamically bend swamp reeds and displace lily pads as you speed through."
        ],
        "question": "Are you exploring the Everglades or sticking to Vice City streets? Let me know!",
        "description": "Rockstar's swamp simulation and predator AI in GTA 6 is terrifying. Did you spot the gator? 👇"
    },
    {
        "clip_name": "t2_clip_03_sports_car_drift.mp4",
        "title": "GTA 6 Next-Gen Drift Physics",
        "category": "cars",
        "focus": "Volumetric tire smoke density, asphalt rubber marks, and body roll during high-speed drift",
        "hooks": ["Look at the asphalt right under the rear tires in this GTA 6 drift!"],
        "facts": [
            "Rockstar is rendering multi-layered volumetric tire smoke that lingers in the air and reacts to car airflow.",
            "Notice how the car chassis realistically leans outward on its springs during high-speed cornering."
        ],
        "question": "What car are you drifting through Vice City first? Drop a comment below!",
        "description": "GTA 6 car handling and smoke simulation looks insane in Trailer 2. Which car are you taking out first? 👇"
    },
    {
        "clip_name": "t2_clip_07_highway_police_chase.mp4",
        "title": "GTA 6 Highway PIT Maneuver AI",
        "category": "city",
        "focus": "Aggressive police tactical maneuvers, vehicle deformation, and high-speed highway traffic evasion",
        "hooks": ["Watch how aggressively this police cruiser attacks in Trailer 2!"],
        "facts": [
            "Undercover cop cruisers now execute coordinated PIT maneuvers to pin your rear bumper into highway guardrails.",
            "Civilian traffic realistically brakes and swerves to the emergency shoulder instead of ignoring high-speed police pursuits."
        ],
        "question": "Can you escape a 5-star wanted level on these highways? Let me know below!",
        "description": "Highway police chases in GTA 6 are way more aggressive than anything in GTA 5. Will you survive? 👇"
    },
    {
        "clip_name": "t2_clip_14_shootout_gas_station.mp4",
        "title": "GTA 6 Dynamic Destruction Physics",
        "category": "city",
        "focus": "Concrete pillar chipping, dynamic glass shattering, and volumetric particle sparks under gunfire",
        "hooks": ["Stop scrolling and look at the cover destruction in this GTA 6 shootout!"],
        "facts": [
            "Bullet impacts actually chip off volumetric chunks of concrete cover, slowly exposing Lucia to incoming fire.",
            "Gas station safety glass shatters in thousands of independent physics-based shards that litter the ground."
        ],
        "question": "Do you love fully destructible cover in open-world shooters? Comment down below!",
        "description": "Rockstar added procedural destruction to shootout environments in GTA 6. Thoughts on destructible cover? 👇"
    },
    {
        "clip_name": "ext_clip_01_mall_interior.mp4",
        "title": "GTA 6 Enterable Mall Details",
        "category": "city",
        "focus": "Reflective polished marble floors, working escalators, and dozens of fully decorated storefronts",
        "hooks": ["Vice City shopping malls are 100% enterable in GTA 6!"],
        "facts": [
            "Every store window has fully rendered merchandise shelves with physical collision models.",
            "NPCs actively carry shopping bags, ride moving escalators, and react dynamically if a fire alarm gets pulled."
        ],
        "question": "Which store are you looting first in this luxury mall? Let me know below!",
        "description": "GTA 6 enterable interiors look more alive than any open-world game before. Did you spot the working escalators? 👇"
    },
    {
        "clip_name": "ext_clip_02_car_customization.mp4",
        "title": "GTA 6 Interactive Cockpit Secret",
        "category": "cars",
        "focus": "Digital speedometer illumination, steering wheel stitched leather texture, and working rearview mirror reflections",
        "hooks": ["Zoom in on the dashboard of this supercar in GTA 6 right now!"],
        "facts": [
            "Rockstar modeled working LCD telemetry gauges that display actual in-game speed and RPM in real time.",
            "Notice the physical stitching along the steering wheel rim reacting to the outdoor sunlight angle."
        ],
        "question": "Are you playing GTA 6 in first-person cockpit view? Tell me in the comments!",
        "description": "Car cockpit detail in GTA 6 rivals dedicated racing simulators. What car are you driving first? 👇"
    },
    {
        "clip_name": "ext_clip_08_beach_crowd_ai.mp4",
        "title": "GTA 6 Beach NPC Density Leak",
        "category": "water",
        "focus": "Over 100 independent NPCs on screen applying sunscreen, listening to radios, and walking dogs",
        "hooks": ["Count how many unique NPCs are on screen in this GTA 6 beach scene!"],
        "facts": [
            "Rockstar programmed over fifty unique beach micro-animations, from NPCs applying sunscreen to walking unleashed dogs.",
            "Notice how beach towels deform dynamically in the sand beneath walking pedestrians."
        ],
        "question": "Will your console explode trying to render this many NPCs? Comment below!",
        "description": "Vice City Beach shows off the most dense open-world crowd simulation ever created. Are you ready? 👇"
    }
]


CURATED_CLIPS = {
    "ext_clip_05_dynamic_storm_surge.mp4": "water", "ext_clip_08_beach_crowd_ai.mp4": "water",
    "ext_clip_09_airboat_swamp_drift.mp4": "water", "ext_clip_16_yacht_party_water.mp4": "water",
    "ext_clip_19_swamp_wildlife.mp4": "water", "clip_01_ocean_speedboats.mp4": "water",
    "clip_02_beach_drones.mp4": "water", "clip_05_everglades_airboat.mp4": "water",
    "t2_clip_08_swamp_hovercraft.mp4": "water", "clip_09_thrillbilly_mud.mp4": "water",
    "clip_11_police_sirens.mp4": "police", "t2_clip_07_highway_police_chase.mp4": "police",
    "t2_clip_12_helicopter_spotlight.mp4": "police", "t2_clip_15_armored_truck_escape.mp4": "police",
    "ext_clip_06_police_helicopter_search.mp4": "police", "ext_clip_15_police_spike_strip.mp4": "police",
    "clip_08_lowriders_meet.mp4": "cars", "clip_10_dirtbikes_gang.mp4": "cars",
    "clip_13_convertible_cruise.mp4": "cars", "t2_clip_03_sports_car_drift.mp4": "cars",
    "t2_clip_10_dirt_track_buggy.mp4": "cars", "t2_clip_11_motorcycle_escape.mp4": "cars",
    "ext_clip_02_car_customization.mp4": "cars", "ext_clip_11_jason_highway_cruise.mp4": "cars",
    "ext_clip_14_speeding_convertible.mp4": "cars", "ext_clip_20_sunset_bridge_traffic.mp4": "cars",
    "clip_14_store_robbery.mp4": "heist", "t2_clip_05_heist_prep_weapons.mp4": "heist",
    "t2_clip_06_bank_vault_breach.mp4": "heist", "t2_clip_14_shootout_gas_station.mp4": "heist",
    "ext_clip_04_gun_shop_inspection.mp4": "heist", "ext_clip_12_gas_station_clerk.mp4": "heist",
    "ext_clip_18_convenience_store_loot.mp4": "heist", "clip_03_flamingos_highway.mp4": "city",
    "clip_04_bridge_to_city.mp4": "city", "clip_06_rooftop_pool.mp4": "city",
    "clip_07_ocean_drive_neon.mp4": "city", "clip_12_nightclub_party.mp4": "city",
    "t2_clip_01_jason_lucia_intro.mp4": "city", "t2_clip_02_vice_city_skyline.mp4": "city",
    "t2_clip_04_port_gellhorn_docks.mp4": "city", "t2_clip_09_strip_club_neon.mp4": "city",
    "t2_clip_13_luxury_mansion_pool.mp4": "city", "t2_clip_16_lucia_jason_climax.mp4": "city",
    "ext_clip_01_mall_interior.mp4": "city", "ext_clip_03_tennis_physics.mp4": "city",
    "ext_clip_07_night_neon_traffic.mp4": "city", "ext_clip_10_lucia_motel_cutscene.mp4": "city",
    "ext_clip_13_club_volumetric_fog.mp4": "city", "ext_clip_17_pedestrian_reaction.mp4": "city"
}

def classify_clip(filename: str) -> str:
    fn = filename.lower()
    base = os.path.basename(fn)
    if base in CURATED_CLIPS: return CURATED_CLIPS[base]
    if fn.startswith("action_gameplay_"): return 'gameplay'
    if any(k in fn for k in ['police', 'cop', 'pursuit', 'chase', 'spike', 'sirens', 'spotlight', 'search', 'armored', 'pit']): return 'police'
    if any(k in fn for k in ['robbery', 'vault', 'heist', 'weapons', 'shootout', 'loot', 'gun', 'gas_station', 'destruction', 'cover']): return 'heist'
    if any(k in fn for k in ['water', 'boat', 'airboat', 'hovercraft', 'swamp', 'everglades', 'beach', 'wave', 'storm', 'yacht', 'ocean', 'flamingos', 'mud', 'wildlife', 'hurricane', 'flood']): return 'water'
    if any(k in fn for k in ['car', 'drift', 'drive', 'cruise', 'customization', 'speeding', 'convertible', 'dirtbikes', 'motorcycle', 'buggy', 'lowriders', 'cockpit', 'traffic']): return 'cars'
    if any(k in fn for k in ['ocean_drive', 'skyline', 'mall', 'neon', 'club', 'party', 'mansion', 'street', 'pedestrian', 'motel', 'prison', 'rooftop', 'bridge', 'tennis', 'docks', 'intro', 'climax']): return 'city'
    return 'gameplay'

def get_category_clips(category: str, exclude_clip: str = None) -> list:
    all_brolls = sorted(glob.glob(os.path.join(BROLL_DIR, "*.mp4")))
    if not all_brolls: return []
    clean_cat = (category or "city").lower()
    matched = [c for c in all_brolls if classify_clip(os.path.basename(c)) == clean_cat and os.path.getsize(c) > 50000]
    if exclude_clip:
        ex_base = os.path.basename(exclude_clip)
        matched = [c for c in matched if os.path.basename(c) != ex_base]
    if matched: return matched
    print(f"⚠️ VAROVÁNÍ: Pro kategorii '{clean_cat.upper()}' nebyl nalezen žádný specifický klip!")
    cur = [c for c in all_brolls if classify_clip(os.path.basename(c)) == "city" and not os.path.basename(c).startswith("action_gameplay_")]
    return cur if cur else all_brolls

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return []

def save_to_history(title, script):
    hist = load_history()
    hist.append({"time": int(time.time()), "title": title, "script": script[:80]})
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f: json.dump(hist[-50:], f, indent=2)
    except Exception: pass

def get_offline_news_topic(history_titles):
    available = [t for t in OFFLINE_NEWS_TOPICS if t["title"] not in history_titles]
    if not available: available = OFFLINE_NEWS_TOPICS
    choice = random.choice(available)
    if "script" in choice:
        return {"title": choice["title"], "category": choice["category"], "script": choice["script"], "description": choice.get("description"), "mode": "news"}
    cta = random.choice([
        "Drop a like, subscribe for daily GTA 6 leaks, and tell me:",
        "Hit subscribe for more leaks, and let me know below:",
        "Subscribe for daily GTA 6 secrets, and tell me in the comments:"
    ])
    script = f"{random.choice(choice['hooks'])} {' '.join(choice['facts'])} {cta} {choice['question']}"
    return {"title": choice["title"], "category": choice["category"], "script": script, "description": choice.get("description"), "mode": "news"}

def get_offline_breakdown_topic(history_titles):
    # Povolit POUZE scény, jejichž video fyzicky leží na disku!
    available = [
        t for t in BREAKDOWN_SCENES 
        if t["title"] not in history_titles and os.path.exists(os.path.join(BROLL_DIR, t.get("clip_name", "")))
    ]
    if not available: available = BREAKDOWN_SCENES
    choice = random.choice(available)
    cta = random.choice([
        "Drop a like, subscribe for daily GTA 6 breakdowns, and tell me:",
        "Hit subscribe for more hidden details, and let me know below:",
        "Subscribe for daily leaks, and tell me in the comments:"
    ])
    script = f"{random.choice(choice['hooks'])} {' '.join(choice['facts'])} {cta} {choice['question']}"
    return {
        "title": choice["title"],
        "category": choice["category"],
        "script": script,
        "description": choice.get("description"),
        "clip_name": choice.get("clip_name"),
        "mode": "breakdown"
    }

def get_available_text_models(client: genai.Client) -> list:
    discovered = []
    try:
        for m in client.models.list():
            m_id = m.name.replace("models/", "")
            actions = getattr(m, "supported_actions", [])
            if "generateContent" in actions or hasattr(m, "input_token_limit"):
                if "tts" not in m_id.lower() and "embed" not in m_id.lower() and "imagen" not in m_id.lower():
                    discovered.append(m_id)
    except Exception: pass

    priority = [
        "gemini-4-hydrogen",
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro"
    ]
    if not discovered:
        return priority

    sorted_models = [p for p in priority if p in discovered]
    for d in discovered:
        if d not in sorted_models:
            sorted_models.append(d)
    return sorted_models or priority


def get_gen_config(model_name: str, timeout: int = 300000, temp: float = 0.9):
    from google.genai import types
    cfg_args = {
        "response_mime_type": "application/json",
        "temperature": temp,
        "http_options": types.HttpOptions(timeout=timeout)
    }
    # Pro hydrogen a reasoning modely omezíme thinking na LOW (žádný zbytečný HIGH overhead)
    if any(k in model_name.lower() for k in ["hydrogen", "thinking"]):
        cfg_args["thinking_config"] = types.ThinkingConfig(thinking_level="LOW")
    return types.GenerateContentConfig(**cfg_args)


def generate_scene_breakdown_script(client: genai.Client, scene_item: dict) -> dict:
    prompt = f"""You are an elite gaming creator doing an in-depth, viral breakdown of a SPECIFIC scene in GTA 6.
The video shows this exact visual on screen: {scene_item['focus']} (Clip: {scene_item['clip_name']}).

Write an engaging, highly detailed 110-125 word script (target duration: 48-55 seconds) that guides the viewer's eyes directly to what is happening on screen!
Use phrases like: 'Watch this clip very closely...', 'Notice how...', 'Look right at the...', 'If you look at the background...'.

STRICT RULES:
1. Category must be: '{scene_item['category']}'.
2. Length: exactly 110-125 words.
3. Structure: 1 viral opening hook, 3 technical/gameplay observations pointing directly to the on-screen action, and 1 closing question smoothly combined with a quick Call-To-Action (e.g. 'Drop a like, subscribe for daily GTA 6 leaks, and tell me: [question]').
4. No hashtags, no stage directions.

Output ONLY valid JSON:
{{
  "title": "{scene_item['title']}",
  "category": "{scene_item['category']}",
  "script": "The 110-125 word breakdown script...",
  "description": "{scene_item['description']}"
}}"""

    models = get_available_text_models(client)
    MAX_ATTEMPTS = 5
    print(f"🔍 Nalezeno {len(models)} textových modelů pro breakdown. Zahajuji generování (až {MAX_ATTEMPTS} pokusů na model, timeout: 300s (5 min))...")

    for model_name in models:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.time()
            attempt_str = f" (pokus {attempt}/{MAX_ATTEMPTS})" if MAX_ATTEMPTS > 1 else ""
            print(f"Zkouším Gemini model: {model_name}{attempt_str}...")
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=get_gen_config(model_name, timeout=300000, temp=0.9)
                )
                raw = res.text.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
                    raw = re.sub(r"\n?```$", "", raw).strip()
                data = json.loads(raw)
                data["clip_name"] = scene_item["clip_name"]
                data["mode"] = "breakdown"
                print(f"-> Breakdown scénář úspěšně vytvořen ({model_name}) za {time.time() - t0:.1f}s!")
                return data
            except Exception as e:
                err = str(e)
                if "404" in err or "NOT_FOUND" in err:
                    break
                elif "503" in err or "UNAVAILABLE" in err:
                    print(f"   Model {model_name} je dočasně přetížen (503), čekám 4s... (pokus {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(4)
                elif "429" in err or "RESOURCE_EXHAUSTED" in err:
                    print(f"   Model {model_name} vyčerpal limit (429), čekám 5s... (pokus {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(5)
                elif "504" in err or "DEADLINE" in err:
                    print(f"   Model {model_name} nestihl odpovědět včas (timeout 300s (5 min))... (pokus {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(3)
                else:
                    print(f"   Model {model_name} chyba: {err[:60]} (pokus {attempt}/{MAX_ATTEMPTS})")
                    if attempt < MAX_ATTEMPTS: time.sleep(2)

    print(f"-> Všechny textové modely vyčerpány, aktivuji offline breakdown scénář...")
    return get_offline_breakdown_topic(load_history())


def generate_100pct_unique_script(client: genai.Client) -> dict:
    history = load_history()
    past_titles = [h.get("title", "") for h in history[-15:]]
    past_str = ", ".join(f'"{t}"' for t in past_titles) if past_titles else "None"

    prompt = f"""You are an elite, viral gaming creator covering undiscovered secrets in GTA 6.
Write an in-depth 48-55 second script (115-130 words) AND a punchy YouTube teaser description for a YouTube Short.

STRICT RULES:
1. Do NOT cover or repeat any of these topics: [{past_str}].
2. Choose a fresh angle: Lucia's ankle monitor, hurricane physics, car interiors, weapon wheel, wildlife AI, enterable malls, or night lighting.
3. Every sentence must use fresh, punchy gaming vocabulary.
4. Category must be: "water", "cars", or "city".
5. Uniqueness random seed: {random.randint(100000, 999999)}

Output ONLY valid JSON with keys:
{{
  "title": "Ultra-catchy unique title under 55 chars",
  "category": "water" or "cars" or "city",
  "script": "A 115-130 word engaging script (approx 50 seconds): 1 shocking viral hook, 3 fascinating gameplay/technical facts with deep detail, and 1 closing question smoothly combined with a quick Call-To-Action (e.g., 'Drop a like, subscribe for daily leaks, and tell me: [question]'). No hashtags, no stage directions.",
  "description": "Short, punchy 1-2 sentence YouTube teaser with an engaging question for the audience. DO NOT repeat the voiceover script!"
}}"""

    models = get_available_text_models(client)
    MAX_ATTEMPTS = 5
    print(f"🔍 Nalezeno {len(models)} textových modelů. Zahajuji generování (až {MAX_ATTEMPTS} pokusů na model, timeout: 300s (5 min))...")

    for model_name in models:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.time()
            attempt_str = f" (pokus {attempt}/{MAX_ATTEMPTS})" if MAX_ATTEMPTS > 1 else ""
            print(f"Zkouším Gemini textový model: {model_name}{attempt_str}...")
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=get_gen_config(model_name, timeout=300000, temp=0.9)
                )
                raw_text = res.text.strip()
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
                    raw_text = re.sub(r"\n?```$", "", raw_text).strip()
                data = json.loads(raw_text)
                data["mode"] = "news"
                print(f"-> Scénář úspěšně vytvořen modelem {model_name} za {time.time() - t0:.1f}s!")
                return data
            except Exception as e:
                err = str(e)
                if "404" in err or "NOT_FOUND" in err:
                    break
                elif "503" in err or "UNAVAILABLE" in err:
                    print(f"   Model {model_name} je dočasně přetížen (503), čekám 4s... (pokus {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(4)
                elif "429" in err or "RESOURCE_EXHAUSTED" in err:
                    print(f"   Model {model_name} vyčerpal limit (429), čekám 5s... (pokus {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(5)
                elif "504" in err or "DEADLINE" in err:
                    print(f"   Model {model_name} nestihl odpovědět včas (timeout 300s (5 min))... (pokus {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(3)
                else:
                    print(f"   Model {model_name} chyba: {err[:60]} (pokus {attempt}/{MAX_ATTEMPTS})")
                    if attempt < MAX_ATTEMPTS: time.sleep(2)

    print(f"-> Všechny textové modely vyčerpány, aktivuji offline generátor...")
    return get_offline_news_topic(past_titles)


def generate_voiceover_edge_fallback(text: str, output_audio_path: str):
    try:
        import edge_tts
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "edge-tts", "-q"])
        import edge_tts

    async def _run():
        communicate = edge_tts.Communicate(text, "en-US-AndrewNeural", rate="+3%")
        await communicate.save(output_audio_path)

    try:
        asyncio.run(_run())
    except Exception:
        cmd = ["edge-tts", "--voice", "en-US-AndrewNeural", "--text", text, "--write-media", output_audio_path]
        subprocess.run(cmd, check=True)

def generate_voiceover(text: str, output_audio: str, output_ass: str, voice: str = "Orion", api_key: str = None, header_title: str = None) -> float:
    key = api_key or os.environ.get("GEMINI_API_KEY")
    audio_bytes = None
    used_model = None

    if key:
        client = genai.Client(api_key=key, http_options=types.HttpOptions(api_version="v1alpha", timeout=180000))
        MAX_TTS_ATTEMPTS = 5
        for model_name in TTS_MODELS:
            for attempt in range(1, MAX_TTS_ATTEMPTS + 1):
                attempt_str = f" (pokus {attempt}/{MAX_TTS_ATTEMPTS})" if MAX_TTS_ATTEMPTS > 1 else ""
                print(f"Zkouším Gemini TTS: {model_name}{attempt_str} (Hlas: {voice}, timeout: 180s)...")
                t0 = time.time()
                try:
                    res = client.models.generate_content(
                        model=model_name,
                        contents=text,
                        config=types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=types.SpeechConfig(
                                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))
                            ),
                            http_options=types.HttpOptions(timeout=180000)
                        )
                    )
                    if res and res.candidates:
                        for candidate in res.candidates:
                            for part in candidate.content.parts:
                                if part.inline_data and part.inline_data.data:
                                    audio_bytes = part.inline_data.data
                                    used_model = model_name
                                    break
                    if audio_bytes:
                        print(f"-> Hlas {voice} úspěšně vygenerován přes {model_name} za {time.time() - t0:.1f}s!")
                        break
                except Exception as e:
                    err = str(e)
                    if "404" in err or "NOT_FOUND" in err:
                        break
                    elif "503" in err or "UNAVAILABLE" in err:
                        print(f"   Model {model_name} dočasně přetížen (503), čekám 4s... (pokus {attempt}/{MAX_TTS_ATTEMPTS})")
                        time.sleep(4)
                    elif "429" in err or "RESOURCE_EXHAUSTED" in err:
                        print(f"   Model {model_name} vyčerpal limit (429), čekám 5s... (pokus {attempt}/{MAX_TTS_ATTEMPTS})")
                        time.sleep(5)
                    elif "504" in err or "DEADLINE" in err:
                        print(f"   Model {model_name} nestihl odpovědět včas (timeout 180s)... (pokus {attempt}/{MAX_TTS_ATTEMPTS})")
                        time.sleep(3)
                    else:
                        print(f"   Model {model_name} nedostupný ({err[:70]}).")
                        if attempt < MAX_TTS_ATTEMPTS: time.sleep(2)
            if audio_bytes:
                break

    if not audio_bytes:
        print("-> Všechny Gemini TTS modely vyčerpány, přepínám na přirozený Edge-TTS (Andrew)...")
        generate_voiceover_edge_fallback(text, output_audio)
    else:
        temp_raw = os.path.join(TEMP_DIR, "raw_audio_temp.dat")
        with open(temp_raw, "wb") as f: f.write(audio_bytes)
        conv_cmd = [FFMPEG_PATH, "-y", "-i", temp_raw, "-c:a", "libmp3lame", "-b:a", "192k", output_audio]
        if subprocess.run(conv_cmd, capture_output=True).returncode != 0:
            subprocess.run([FFMPEG_PATH, "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", temp_raw, "-c:a", "libmp3lame", "-b:a", "192k", output_audio], check=True)
        if os.path.exists(temp_raw): os.remove(temp_raw)

    print("-> Generuji kinetické karaoke titulky a horní badge...")
    dur = transcribe_and_make_subtitles(output_audio, output_ass, header_title=header_title)
    return dur


def ensure_safe_bg_music() -> str:
    music_dir = os.path.join(BASE_DIR, "music")
    os.makedirs(music_dir, exist_ok=True)
    safe_file = os.path.join(music_dir, "track_01_newer_wave.mp3")
    if os.path.exists(safe_file) and os.path.getsize(safe_file) > 50000:
        return safe_file
    url = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Newer%20Wave.mp3"
    print("Stahuji bezpečnou ambientní hudbu (Kevin MacLeod - Newer Wave)...")
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp, open(safe_file, "wb") as f:
            f.write(resp.read())
        return safe_file
    except Exception as e:
        print(f"Varování: Hudbu se nepodařilo stáhnout ({e}).")
        return None


def render_multicut_video(audio_path: str, ass_path: str, output_path: str, target_dur: float, category: str = "city") -> bool:
    category_clips = get_category_clips(category)
    if not category_clips:
        print(f"CHYBA: Ve složce {BROLL_DIR} nejsou žádné B-Roll klipy!")
        return False

    print(f"-> MULTICUT: Vybráno {len(category_clips)} tematických klipů pro kategorii '{category.upper()}'.")
    bg_music = ensure_safe_bg_music()

    clip_len = 2.8
    num_clips_needed = math.ceil(target_dur / clip_len)
    shuffled = list(category_clips)
    random.shuffle(shuffled)
    chosen_clips = []
    while len(chosen_clips) < num_clips_needed:
        chosen_clips.extend(shuffled)
    chosen_clips = chosen_clips[:num_clips_needed]

    cut_timestamps = [clip_len * i for i in range(1, num_clips_needed)]
    sfx_path = os.path.join(TEMP_DIR, f"sfx_{int(time.time())}.wav")
    build_sfx_track(cut_timestamps, target_dur, sfx_path)

    inputs = []
    for c in chosen_clips:
        inputs.extend(["-i", c])
    inputs.extend(["-i", audio_path])
    voice_idx = len(chosen_clips)

    inputs.extend(["-i", sfx_path])
    sfx_idx = voice_idx + 1

    music_idx = None
    if bg_music and os.path.exists(bg_music):
        inputs.extend(["-stream_loop", "-1", "-i", bg_music])
        music_idx = sfx_idx + 1

    filter_chains = []
    concat_video_inputs = []

    for i, c in enumerate(chosen_clips):
        if i % 2 == 0:
            scale_crop = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
        else:
            scale_crop = "scale=1252:2226:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
        occ = chosen_clips[:i].count(c)
        start_trim = (occ * 1.5) % 2.5
        filter_chains.append(
            f"[{i}:v]trim=start={start_trim:.2f}:duration={clip_len},setpts=PTS-STARTPTS,{scale_crop}[v{i}]"
        )
        concat_video_inputs.append(f"[v{i}]")

    concat_chain = f"{''.join(concat_video_inputs)}concat=n={len(chosen_clips)}:v=1:a=0[vbase]"
    filter_chains.append(concat_chain)

    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:")
    sub_filter = f"subtitles=filename='{ass_esc}'" if os.name == 'nt' else f"subtitles='{ass_esc}'"
    filter_chains.append(f"[vbase]{sub_filter}[vout]")

    if music_idx is not None:
        filter_chains.append(
            f"[{music_idx}:a]volume=0.07[bg];"
            f"[{voice_idx}:a]volume=1.0[voice];"
            f"[{sfx_idx}:a]volume=0.85[sfx];"
            f"[voice][bg][sfx]amix=inputs=3:duration=first:dropout_transition=2[aout]"
        )
    else:
        filter_chains.append(
            f"[{voice_idx}:a]volume=1.0[voice];"
            f"[{sfx_idx}:a]volume=0.85[sfx];"
            f"[voice][sfx]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

    full_filter = ";".join(filter_chains)

    cmd = [
        FFMPEG_PATH, "-y",
        *inputs,
        "-filter_complex", full_filter,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(target_dur + 0.3),
        output_path
    ]

    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FFmpeg selhal! Stderr:\n{res.stderr[-600:]}")
        return False
    print(f"-> Top-Tier multicut video ({len(chosen_clips)} střihů z kategorie {category.upper()}, punch-in, SFX) vyrenderováno za {time.time() - t0:.1f}s.")
    return True

def render_breakdown_video(target_clip_name: str, audio_path: str, ass_path: str, output_path: str, target_dur: float, category: str = None) -> bool:
    clip_path = os.path.join(BROLL_DIR, target_clip_name) if target_clip_name else None
    if not clip_path or not os.path.exists(clip_path) or os.path.getsize(clip_path) < 50000:
        all_brolls = sorted(glob.glob(os.path.join(BROLL_DIR, "*.mp4")))
        if not all_brolls:
            print(f"CHYBA: Cílový klip {target_clip_name} ani žádný jiný klip nebyl nalezen!")
            return False
        clip_path = all_brolls[0]
        target_clip_name = os.path.basename(clip_path)

    eff_category = category or classify_clip(target_clip_name)
    print(f"-> BREAKDOWN: Cílová scéna: '{target_clip_name}', Sémantická kategorie: '{eff_category.upper()}'.")

    bg_music = ensure_safe_bg_music()

    inputs = ["-i", clip_path]

    p1_dur = 3.5
    p2_native_start = 0.5
    p2_native_dur = 3.0
    p2_dur = 4.0

    filter_segments = [
        f"[0:v]trim=0:{p1_dur:.2f},setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v0];",
        f"[0:v]trim={p2_native_start:.2f}:{p2_native_start + p2_native_dur:.2f},setpts=1.33333*(PTS-STARTPTS),scale=1458:2592,crop=1080:1920:(in_w-out_w)/2:(in_h-out_h)/2,setsar=1[v1];"
    ]
    concat_parts = ["[v0]", "[v1]"]
    cut_timestamps = [p1_dur, p1_dur + p2_dur]
    next_input_idx = 1

    rem_dur = target_dur - (p1_dur + p2_dur)
    if rem_dur > 0.5:
        cat_clips = get_category_clips(eff_category, exclude_clip=target_clip_name)
        supp_pool = cat_clips + [clip_path]

        num_supp = max(1, math.ceil(rem_dur / 2.8))
        supp_dur = rem_dur / num_supp

        chosen_supp = []
        while len(chosen_supp) < num_supp:
            shuffled = list(supp_pool)
            random.shuffle(shuffled)
            chosen_supp.extend(shuffled)
        chosen_supp = chosen_supp[:num_supp]

        for i, supp_file in enumerate(chosen_supp):
            inputs.extend(["-i", supp_file])
            idx = next_input_idx
            next_input_idx += 1
            if i % 2 == 0:
                scale_crop = "scale=1252:2226:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
            else:
                scale_crop = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"

            filter_segments.append(
                f"[{idx}:v]trim=0:{supp_dur:.2f},setpts=PTS-STARTPTS,{scale_crop}[v_supp_{i}];"
            )
            concat_parts.append(f"[v_supp_{i}]")
            cut_timestamps.append(p1_dur + p2_dur + (i + 1) * supp_dur)

    num_concat = len(concat_parts)
    concat_str = "".join(concat_parts)

    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:")
    sub_filter = f"subtitles=filename='{ass_esc}'" if os.name == 'nt' else f"subtitles='{ass_esc}'"

    v_chain = "".join(filter_segments) + f"{concat_str}concat=n={num_concat}:v=1:a=0[vcat];[vcat]eq=contrast=1.06:saturation=1.08:brightness=0.01,{sub_filter}[vout]"

    inputs.extend(["-i", audio_path])
    voice_idx = next_input_idx
    next_input_idx += 1

    sfx_path = os.path.join(TEMP_DIR, f"sfx_bd_{int(time.time())}.wav")
    build_sfx_track(cut_timestamps, target_dur, sfx_path)
    inputs.extend(["-i", sfx_path])
    sfx_idx = next_input_idx
    next_input_idx += 1

    if bg_music and os.path.exists(bg_music):
        inputs.extend(["-stream_loop", "-1", "-i", bg_music])
        music_idx = next_input_idx
        next_input_idx += 1
        filter_complex = f"{v_chain};[{music_idx}:a]volume=0.07[bg];[{voice_idx}:a]volume=1.0[voice];[{sfx_idx}:a]volume=0.85[sfx];[voice][bg][sfx]amix=inputs=3:duration=first:dropout_transition=2[aout]"
    else:
        filter_complex = f"{v_chain};[{voice_idx}:a]volume=1.0[voice];[{sfx_idx}:a]volume=0.85[sfx];[voice][sfx]amix=inputs=2:duration=first:dropout_transition=2[aout]"

    cmd = [
        FFMPEG_PATH, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(target_dur + 0.3),
        output_path
    ]

    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FFmpeg breakdown render selhal! Stderr:\n{res.stderr[-600:]}")
        return False
    print(f"-> Top-Tier Breakdown video ({eff_category.upper()}) se slow-mo zoomem, punch-in a SFX ({num_concat} segmentů) vyrenderováno za {time.time() - t0:.1f}s.")
    return True

def run_cycle(schedule: str = None, privacy: str = "public", dry_run: bool = False, mode: str = "auto"):
    print("\n" + "=" * 60)
    print("  ZAHÁJENÍ AUTOMATICKÉHO CYKLU GTA 6 SHORTS")
    print("=" * 60)

    key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=key) if key else None

    # Rozhodnutí o režimu videa
    chosen_mode = mode
    if mode == "auto":
        chosen_mode = random.choice(["news", "breakdown"])

    print(f"Režim generování: {chosen_mode.upper()}")

    # 1. Scénář podle režimu
    if chosen_mode == "breakdown":
        hist = load_history()
        past_titles = [h.get("title", "") for h in hist[-15:]]
        avail_scenes = [s for s in BREAKDOWN_SCENES if s["title"] not in past_titles]
        if not avail_scenes:
            avail_scenes = BREAKDOWN_SCENES
        scene_item = random.choice(avail_scenes)

        if client:
            data = generate_scene_breakdown_script(client, scene_item)
        else:
            data = get_offline_breakdown_topic(past_titles)
    else:
        if client:
            data = generate_100pct_unique_script(client)
        else:
            data = get_offline_news_topic([h.get("title", "") for h in load_history()[-15:]])

    title = data.get("title", "Insane GTA 6 Secret You Missed")
    category = data.get("category", "city")
    script = data.get("script", "")
    description = data.get("description", "Insane GTA 6 details and leaks you missed! What do you think? 👇")
    clip_name = data.get("clip_name")

    print(f"\n[1/4] Vybrano téma: '{title}' (Kategorie: {category})")
    if clip_name:
        print(f"      Cílová scéna: {clip_name}")
    print(f"Scénář: \"{script}\"")
    print(f"Popisek: \"{description}\"\n")

    # 2. Generování přirozeného hlasu Orion + titulky
    voice = "Orion"
    ts = int(time.time())
    aud = os.path.join(TEMP_DIR, f"voice_{ts}.mp3")
    ass = os.path.join(TEMP_DIR, f"subs_{ts}.ass")
    print(f"[2/4] Generuji hlas a synchronizované titulky...")
    dur = generate_voiceover(script, aud, ass, voice=voice, api_key=key)

    # 3. Render videa podle zvoleného režimu
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).replace(" ", "_")
    out_path = os.path.join(OUTPUT_DIR, f"Short_{safe_title}_{ts}.mp4")
    print("[3/4] Sestavuji video bez původního zvuku traileru...")

    if chosen_mode == "breakdown":
        success = render_breakdown_video(clip_name, aud, ass, out_path, dur, category=category)
        if not success:
            print("⚠️ Render breakdown videa selhal! Spouštím záchranný fallback: render_multicut_video...")
            success = render_multicut_video(aud, ass, out_path, dur, category=category)
    else:
        success = render_multicut_video(aud, ass, out_path, dur, category=category)

    if not success:
        print("Chyba při renderování videa!")
        return

    print(f"\nUSPECH! Video vyrenderováno: {os.path.basename(out_path)}")

    # 4. Upload & Uložení do historie
    if not dry_run:
        print("\n[4/5] Nahrávám na YouTube (100% bezpečné pro monetizaci)...")
        vid_url = upload_short(out_path, title=title, description=description, privacy=privacy, schedule=schedule, delete_after=False)
        if vid_url:
            save_to_history(title, script)
            print(f"-> Téma '{title}' úspěšně uloženo do historie kanálu.")

        # 5. Cross-post na TikTok přes Buffer (pokud je nastaven klíč)
        if os.getenv("BUFFER_API_KEY"):
            try:
                from tiktok_buffer import post_video_to_buffer_queue
                print("\n[5/5] Přidávám video do Buffer fronty pro TikTok...")
                caption = f"{title} #GTA6 #Gaming #Shorts #Viral"
                post_video_to_buffer_queue(out_path, caption=caption, channel_filter="GTA")
            except Exception as e:
                print(f"⚠️ Varování: Upload na TikTok přes Buffer selhal: {e}")

        # Úklid lokálního vyrenderovaného videa
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
                print(f"Čistím disk: smazáno vyrenderované video {os.path.basename(out_path)}.")
        except Exception:
            pass
    else:
        print("[DRY RUN] Nahrávání přeskočeno, video zachováno.")

    print("\n" + "=" * 60)
    print("  CYKLUS DOKONCEN! VIDEO VYTVORENO BEZ COPYRIGHT CLAIMS.")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--schedule", default=None, help="Čas publikace v CET (např. 17:00)")
    p.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    p.add_argument("--dry-run", action="store_true", help="Vyrenderovat video lokálně bez uploadu")
    p.add_argument("--mode", default="auto", choices=["auto", "news", "breakdown"], help="Režim videa: news (multicut faktů), breakdown (rozbor konkrétní scény se slow-mo zoomem), nebo auto")
    args = p.parse_args()
    run_cycle(schedule=args.schedule, privacy=args.privacy, dry_run=args.dry_run, mode=args.mode)
