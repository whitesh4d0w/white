import os
from faster_whisper import WhisperModel
from config import FONT_NAME, TARGET_WIDTH, TARGET_HEIGHT

_model_cache = None

def get_whisper_model():
    global _model_cache
    if _model_cache is None:
        print("Načítám Whisper model (base.en)...")
        _model_cache = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _model_cache

def format_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h, m, s = int(sec // 3600), int((sec % 3600) // 60), int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100: s += 1; cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def transcribe_and_make_subtitles(audio_path: str, ass_path: str, max_words_per_chunk: int = 3, header_title: str = "{\\c&H0000F5FF&}🔥 GTA 6{\\c&H00FFFFFF&} • SECRET DETAILS 🔍") -> float:
    model = get_whisper_model()
    segments, info = model.transcribe(audio_path, word_timestamps=True, language="en")
    words_list = []
    for s in segments:
        if s.words:
            for w in s.words:
                clean = w.word.strip().upper()
                if clean: words_list.append({"start": float(w.start), "end": float(w.end), "word": clean})

    ass_header = f"""[Script Info]
Title: GTA 6 Shorts Dynamic Kinetic Subtitles
ScriptType: v4.00+
PlayResX: {TARGET_WIDTH}
PlayResY: {TARGET_HEIGHT}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},72,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,7,3,2,40,40,440,1
Style: Header,{FONT_NAME},42,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,5,3,8,40,40,130,1
Style: CTA,{FONT_NAME},52,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,6,3,2,40,40,280,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogue_lines = []
    total_dur = float(info.duration)
    if header_title:
        dialogue_lines.append(f"Dialogue: 2,0:00:00.00,{format_ass_time(total_dur + 0.3)},Header,,0,0,0,,{{\\fad(250,200)}}{header_title}")

    chunks = [words_list[i:i+max_words_per_chunk] for i in range(0, len(words_list), max_words_per_chunk)]
    last_end = 0.0
    for c_idx, chk in enumerate(chunks):
        for w_idx, w in enumerate(chk):
            w_start = max(last_end, w["start"])
            if w_idx < len(chk) - 1:
                w_end = max(w_start + 0.12, chk[w_idx + 1]["start"])
            else:
                w_end = chunks[c_idx + 1][0]["start"] if (c_idx < len(chunks) - 1 and (chunks[c_idx + 1][0]["start"] - w["end"]) < 0.28) else max(w_start + 0.20, w["end"])
            last_end = w_end
            parts = [f"{{\\c&H0000F5FF&\\fscx112\\fscy112}}{ow['word']}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}" if j == w_idx else ow["word"] for j, ow in enumerate(chk)]
            dialogue_lines.append(f"Dialogue: 0,{format_ass_time(w_start)},{format_ass_time(w_end)},Default,,0,0,0,,{' '.join(parts)}")

    if total_dur > 3.0:
        dialogue_lines.append(f"Dialogue: 1,{format_ass_time(max(0.0, total_dur - 3.2))},{format_ass_time(total_dur + 0.3)},CTA,,0,0,0,,{{\\fad(250,200)}}{{\\c&H000022FF&}}🔴{{\\c&H00FFFFFF&}} SUBSCRIBE FOR DAILY GTA 6 {{\\c&H0000F5FF&}}🔔{{\\c&H00FFFFFF&}}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(dialogue_lines) + "\n")
    return total_dur
