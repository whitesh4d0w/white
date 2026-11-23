import os, sys, argparse, time
from config import TEMP_DIR, OUTPUT_DIR, DEFAULT_VOICE
from script_engine import get_script, list_topics
from gemini_engine import generate_voiceover_gemini, DEFAULT_GEMINI_VOICE
from video_engine import build_video_short, create_demo_bg

def run_pipeline(topic=None, gemini_key=None, gemini_voice=DEFAULT_GEMINI_VOICE, video=None, demo=False):
    sdata = get_script(topic)
    print(f"\n[1/3] Topic: {sdata['title']}")
    ts = int(time.time())
    aud = os.path.join(TEMP_DIR, f"voice_{ts}.mp3")
    ass = os.path.join(TEMP_DIR, f"subs_{ts}.ass")
    key = gemini_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        print("ERROR: GEMINI_API_KEY is not set! Put it into .env file or pass via --gemini-key")
        return
    dur = generate_voiceover_gemini(sdata['text'], aud, ass, voice=gemini_voice, api_key=key)
    print(f"-> Audio duration: {dur:.1f}s")
    
    in_v = video
    if not in_v or not os.path.exists(in_v):
        in_v = os.path.join(TEMP_DIR, f"demo_{ts}.mp4")
        create_demo_bg(in_v, int(dur+5))
        
    out_v = os.path.join(OUTPUT_DIR, f"Short_{ts}.mp4")
    print("\n[3/3] Rendering video...")
    if build_video_short(in_v, aud, ass, out_v, dur):
        print(f"\nSUCCESS! Video generated at: {out_v}\n")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--topic", default="water_physics")
    p.add_argument("--gemini-key", default=None)
    p.add_argument("--voice", default="Orion")
    p.add_argument("--video", default="downloads/gta6_trailer_slice.mp4")
    p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    run_pipeline(args.topic, args.gemini_key, args.voice, args.video, args.demo)
