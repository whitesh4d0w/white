import os, time, subprocess, asyncio
from google import genai
from google.genai import types
from config import FFMPEG_PATH, TEMP_DIR
from whisper_engine import transcribe_and_make_subtitles

DEFAULT_GEMINI_VOICE = "Orion"

def generate_voiceover_edge_fallback(text: str, output_audio_path: str):
    import edge_tts
    async def _run():
        communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="+5%")
        await communicate.save(output_audio_path)
    asyncio.run(_run())

def generate_voiceover_gemini(text: str, output_audio_path: str, output_ass_path: str, voice: str = DEFAULT_GEMINI_VOICE, api_key: str = None) -> float:
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key: raise ValueError("GEMINI_API_KEY not found!")

    # Striktní timeout 6 sekund
    client = genai.Client(api_key=key, http_options=types.HttpOptions(api_version="v1alpha", timeout=12000))

    print(f"Calling Gemini Flash TTS (Voice: {voice}, max 6s)...")
    audio_bytes = None

    try:
        res = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))
                ),
                http_options=types.HttpOptions(timeout=12000)
            )
        )
        if res and res.candidates:
            for candidate in res.candidates:
                for part in candidate.content.parts:
                    if part.inline_data:
                        audio_bytes = part.inline_data.data
                        break
    except Exception as e:
        print(f"Upozornění: Gemini TTS špička/timeout ({e}).")

    if not audio_bytes:
        print("-> Okamžitě aktivuji bleskový Edge-TTS (0.8s)...")
        generate_voiceover_edge_fallback(text, output_audio_path)
    else:
        temp_raw = os.path.join(TEMP_DIR, "raw_audio.dat")
        with open(temp_raw, "wb") as f: f.write(audio_bytes)

        conv_cmd = [FFMPEG_PATH, "-y", "-i", temp_raw, "-c:a", "libmp3lame", "-b:a", "192k", output_audio_path]
        if subprocess.run(conv_cmd, capture_output=True).returncode != 0:
            subprocess.run([FFMPEG_PATH, "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", temp_raw, "-c:a", "libmp3lame", "-b:a", "192k", output_audio_path], check=True)
        if os.path.exists(temp_raw): os.remove(temp_raw)

    print("Generating synchronized subtitles via faster-whisper...")
    return transcribe_and_make_subtitles(output_audio_path, output_ass_path)
