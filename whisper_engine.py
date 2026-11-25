import os
import re
from datetime import timedelta

# Fix pro PyAV >= 14.0 (odstranění nepodporovaného argumentu metadata_errors ve faster-whisper)
try:
    import av
    _orig_av_open = av.open
    def _safe_av_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return _orig_av_open(*args, **kwargs)
    av.open = _safe_av_open
except Exception:
    pass

from faster_whisper import WhisperModel
from config import (
    FONT_NAME, FONT_SIZE, PRIMARY_COLOR, SECONDARY_COLOR,
    OUTLINE_COLOR, OUTLINE_WIDTH, MARGIN_VERTICAL,
    TARGET_WIDTH, TARGET_HEIGHT
)

_model_cache = None

def get_whisper_model():
    global _model_cache
    if _model_cache is None:
        print("Loading Whisper model (base.en)...")
        _model_cache = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _model_cache

def format_ass_time(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{hours}:{minutes:02d}:{s:02d}.{cs:02d}"

def transcribe_and_make_subtitles(
    audio_path: str,
    ass_path: str,
    max_words_per_chunk: int = 3,
    header_title: str = "{\\c&H0000F5FF&}🔥 GTA 6{\\c&H00FFFFFF&} • SECRET DETAILS 🔍"
) -> float:
    """
    Transcribes audio using faster-whisper and generates TOP-TIER kinetic karaoke ASS subtitles.
    - 2-3 words per phrase for ultra-fast retention pacing
    - Active spoken word highlighted in bright neon yellow (&H0000F5FF&) with 112% pop scale
    - Thick 7px black outline and deep drop shadow for 100% legibility on any background
    - Top context badge anchored at top of screen
    - Ending CTA badge for subscription retention
    """
    model = get_whisper_model()
    segments, info = model.transcribe(audio_path, word_timestamps=True, language="en")

    words_list = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                clean_w = w.word.strip().upper()
                if clean_w:
                    words_list.append({
                        "start": float(w.start),
                        "end": float(w.end),
                        "word": clean_w
                    })

    # Header style, Default (karaoke text), and CTA style
    ass_header = f"""[Script Info]
Title: GTA 6 Shorts Dynamic Kinetic Subtitles
ScriptType: v4.00+
PlayResX: {TARGET_WIDTH}
PlayResY: {TARGET_HEIGHT}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},72,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,7,3,2,40,40,680,1
Style: Header,{FONT_NAME},42,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,5,3,8,40,40,130,1
Style: CTA,{FONT_NAME},52,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,6,3,2,40,40,470,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogue_lines = []
    total_duration = float(info.duration)

    # 1. Top Context Badge (shown during opening hook, fades out cleanly after 3.5s)
    if header_title:
        h_end = format_ass_time(min(3.5, total_duration + 0.2))
        dialogue_lines.append(
            f"Dialogue: 2,0:00:00.00,{h_end},Header,,0,0,0,,{{\\fad(250,400)}}{header_title}"
        )

    # 2. Chunk words cleanly by punctuation, natural speech pauses (>= 0.25s), and max length
    chunks = []
    current_chk = []
    for idx, w_item in enumerate(words_list):
        current_chk.append(w_item)
        ends_clause = w_item["word"].endswith((".", "!", "?", ",", ";", ":"))
        has_pause = (
            idx + 1 < len(words_list)
            and (words_list[idx + 1]["start"] - w_item["end"]) >= 0.25
        )
        if len(current_chk) >= max_words_per_chunk or ends_clause or has_pause:
            chunks.append(current_chk)
            current_chk = []
    if current_chk:
        chunks.append(current_chk)

    # 3. Generate active word highlights
    last_end = 0.0
    for c_idx, chk in enumerate(chunks):
        for w_idx, w in enumerate(chk):
            w_start = max(last_end, w["start"])

            # Calculate word end
            if w_idx < len(chk) - 1:
                next_w = chk[w_idx + 1]
                w_end = max(w_start + 0.12, next_w["start"])
            else:
                if c_idx < len(chunks) - 1:
                    next_chk_start = chunks[c_idx + 1][0]["start"]
                    if next_chk_start > w_start and (next_chk_start - w["end"]) < 0.28:
                        w_end = next_chk_start
                    else:
                        w_end = max(w_start + 0.18, w["end"])
                else:
                    w_end = max(w_start + 0.25, w["end"])

            last_end = w_end
            st_str = format_ass_time(w_start)
            et_str = format_ass_time(w_end)

            # Build line: active word has neon yellow + pop scale
            parts = []
            for j, ow in enumerate(chk):
                txt = ow["word"]
                if j == w_idx:
                    parts.append(f"{{\\c&H0000F5FF&\\fscx112\\fscy112}}{txt}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}")
                else:
                    parts.append(txt)

            line_text = " ".join(parts)
            dialogue_lines.append(f"Dialogue: 0,{st_str},{et_str},Default,,0,0,0,,{line_text}")

    # 4. Closing CTA badge on last 3.2 seconds
    if total_duration > 3.0:
        cta_start = max(0.0, total_duration - 3.2)
        cta_end = total_duration + 0.3
        start_str = format_ass_time(cta_start)
        end_str = format_ass_time(cta_end)
        cta_line = f"Dialogue: 1,{start_str},{end_str},CTA,,0,0,0,,{{\\fad(250,200)}}{{\\c&H000022FF&}}🔴{{\\c&H00FFFFFF&}} SUBSCRIBE FOR DAILY GTA 6 {{\\c&H0000F5FF&}}🔔{{\\c&H00FFFFFF&}}"
        dialogue_lines.append(cta_line)

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(dialogue_lines) + "\n")

    return total_duration
