"""
video_narrator.py - Video-First (Watch-Then-Narrate) engine for GTA 6 Shorts.

Workflow:
1. Select a cohesive/varied sequence of B-roll clips from `broll_dir` (avoiding
   recent repeats via `history`) and render a silent raw montage (`montage_raw.mp4`).
2. Have Gemini Vision actually watch the assembled montage via `client.files.upload`
   (waiting for ACTIVE state and always deleting the remote file in `finally`),
   with inline video bytes and timestamped frame-strip fallbacks plus active
   Gemini 3.x model failover.
3. Produce a 1:1 clip-segmented GTA 6 Shorts commentary script tied directly to
   what appears on screen in each clip's timestamp window.
4. Synthesize TTS per segment (Gemini TTS with Edge-TTS fallback), normalize each
   segment to frame-aligned 44.1 kHz WAV, concatenate the voiceover track, and
   render `synced_video_path` with each clip locked frame-accurately to its
   spoken segment duration.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import time
import uuid
import wave
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

try:
    from config import (
        BASE_DIR as CONFIG_BASE_DIR,
        FFMPEG_PATH as CONFIG_FFMPEG_PATH,
        FPS as CONFIG_FPS,
        TARGET_HEIGHT as CONFIG_TARGET_HEIGHT,
        TARGET_WIDTH as CONFIG_TARGET_WIDTH,
    )
except ImportError:
    import imageio_ffmpeg

    CONFIG_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_FFMPEG_PATH = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
    CONFIG_TARGET_WIDTH = 1080
    CONFIG_TARGET_HEIGHT = 1920
    CONFIG_FPS = 30

try:
    from semantic_engine import classify_clip as _semantic_classify_clip
except ImportError:
    _semantic_classify_clip = None


FFMPEG_BIN = CONFIG_FFMPEG_PATH
TARGET_WIDTH = CONFIG_TARGET_WIDTH
TARGET_HEIGHT = CONFIG_TARGET_HEIGHT
FPS = CONFIG_FPS

SAMPLE_RATE = 44100
SAMPLES_PER_FRAME = SAMPLE_RATE // FPS  # 1470 samples per 30fps video frame

MIN_CLIP_BYTES = 50_000
MAX_INLINE_VIDEO_BYTES = 18 * 1024 * 1024
VALID_CATEGORIES = ("cars", "police", "water", "heist", "city")
VALID_MODES = ("auto", "news", "breakdown")

# Active Gemini 4 Hydrogen & 3.x Vision models (avoid deprecated 2.0-flash / 2.5-flash)
VISION_MODELS = [
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]

TTS_MODELS = [
    "gemini-3.8-flash-tts",
    "gemini-3.8-flash-lite-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-3.8-flash",
]

EDGE_FALLBACK_VOICE = "en-US-AndrewNeural"
EDGE_FALLBACK_RATE = "+3%"


class VideoNarratorError(RuntimeError):
    """Raised when Video-First assembly or Vision narration fails."""


def _load_api_key(api_key: str | None = None, broll_dir: str | None = None) -> str:
    """Resolve GEMINI_API_KEY from argument, environment, or .env files."""
    if api_key and api_key.strip():
        return api_key.strip()

    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key

    candidate_envs = [Path(CONFIG_BASE_DIR) / ".env"]
    if broll_dir:
        broll_path = Path(broll_dir).resolve()
        candidate_envs.extend([
            broll_path.parent / ".env",
            broll_path.parent.parent / ".env",
        ])

    for env_path in candidate_envs:
        if not env_path.is_file():
            continue
        try:
            with open(env_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    k, v = stripped.split("=", 1)
                    if k.strip() == "GEMINI_API_KEY":
                        val = v.strip().strip('"').strip("'")
                        if val:
                            os.environ.setdefault("GEMINI_API_KEY", val)
                            return val
        except OSError:
            continue

    raise VideoNarratorError("GEMINI_API_KEY not found in argument, environment, or .env.")


def _classify_clip(filename: str) -> str:
    """Classify a B-roll clip filename into a semantic GTA 6 category."""
    if _semantic_classify_clip is not None:
        return _semantic_classify_clip(filename)

    base = os.path.basename(filename).lower()
    for cat in VALID_CATEGORIES:
        if base.startswith(f"{cat}_"):
            return cat
    if any(k in base for k in ("police", "cop", "pursuit", "chase", "spike", "sirens", "spotlight", "armored")):
        return "police"
    if any(k in base for k in ("robbery", "vault", "heist", "weapons", "shootout", "loot", "gun", "gas_station")):
        return "heist"
    if any(k in base for k in ("water", "boat", "airboat", "hovercraft", "swamp", "everglades", "beach", "storm", "yacht", "ocean")):
        return "water"
    if any(k in base for k in ("car", "drift", "drive", "cruise", "customization", "speeding", "convertible", "motorcycle", "buggy")):
        return "cars"
    return "city"


def _find_ffprobe() -> str | None:
    """Locate ffprobe if installed on the system."""
    probe = shutil.which("ffprobe")
    if probe:
        return probe
    if FFMPEG_BIN:
        sibling = Path(FFMPEG_BIN).with_name("ffprobe" + Path(FFMPEG_BIN).suffix)
        if sibling.is_file():
            return str(sibling)
    return None


def probe_media_duration(file_path: str) -> float:
    """Return media duration in seconds using wave, ffprobe, or ffmpeg -i fallback."""
    if file_path.lower().endswith(".wav") and os.path.isfile(file_path):
        try:
            with wave.open(file_path, "rb") as w:
                rate = w.getframerate()
                if rate > 0:
                    return w.getnframes() / float(rate)
        except Exception:
            pass

    ffprobe = _find_ffprobe()
    if ffprobe:
        try:
            res = subprocess.run(
                [
                    ffprobe,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            dur = float(res.stdout.strip())
            if dur > 0:
                return dur
        except Exception:
            pass

    try:
        res = subprocess.run(
            [FFMPEG_BIN, "-nostdin", "-i", file_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr or "")
        if m:
            hrs, mins, secs = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return hrs * 3600.0 + mins * 60.0 + secs
    except Exception:
        pass

    return 0.0


def _extract_recent_history(history: list[dict] | None) -> tuple[dict[str, int], list[str], list[str]]:
    """
    Extract clip recency/usage counts, recent titles, and recent categories from history.
    Returns (clip_last_age_or_score, recent_titles, recent_categories) where
    clip_recency maps clip basename -> recency rank (higher = used more recently).
    """
    clip_recency: dict[str, int] = {}
    recent_titles: list[str] = []
    recent_categories: list[str] = []

    if not history:
        return clip_recency, recent_titles, recent_categories

    for entry in history[-15:]:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title")
        if isinstance(title, str) and title.strip():
            recent_titles.append(title.strip())
        cat = entry.get("category")
        if isinstance(cat, str) and cat.strip().lower() in VALID_CATEGORIES:
            recent_categories.append(cat.strip().lower())

    # Scan full history (newest has highest recency score) so all 150+ clips rotate before repeating
    for age_idx, entry in enumerate(history, start=1):
        if not isinstance(entry, dict):
            continue
        clip_name = entry.get("clip_name")
        if isinstance(clip_name, str) and clip_name.strip():
            clip_recency[os.path.basename(clip_name.strip())] = age_idx
        used = entry.get("used_clips")
        if isinstance(used, list):
            for name in used:
                if isinstance(name, str) and name.strip():
                    clip_recency[os.path.basename(name.strip())] = age_idx

    return clip_recency, recent_titles, recent_categories


def discover_broll_clips(broll_dir: str, probe_all: bool = False) -> list[dict[str, Any]]:
    """Discover valid MP4 B-roll clips in `broll_dir` with classification and durations."""
    if not broll_dir or not os.path.isdir(broll_dir):
        raise VideoNarratorError(f"B-roll directory does not exist: {broll_dir}")

    clips: list[dict[str, Any]] = []
    for entry in sorted(Path(broll_dir).glob("*.mp4")):
        if not entry.is_file():
            continue
        try:
            if entry.stat().st_size <= MIN_CLIP_BYTES:
                continue
        except OSError:
            continue

        dur = probe_media_duration(str(entry)) if probe_all else 4.5
        if dur < 0.8:
            continue

        clips.append({
            "clip_path": str(entry),
            "clip_name": entry.name,
            "category": _classify_clip(entry.name),
            "src_dur": dur,
        })

    if not clips:
        raise VideoNarratorError(f"No valid B-roll MP4 clips (> {MIN_CLIP_BYTES} bytes) found in {broll_dir}")

    return clips


def _order_by_freshness(pool: list[dict[str, Any]], clip_recency: dict[str, int]) -> list[dict[str, Any]]:
    """Order clips so never-seen clips come first (shuffled), then oldest-used clips."""
    shuffled = list(pool)
    random.shuffle(shuffled)
    return sorted(shuffled, key=lambda c: clip_recency.get(c["clip_name"], 0))


def select_clip_sequence(
    clips: list[dict[str, Any]],
    mode: str = "auto",
    category: str | None = None,
    target_clips: int = 7,
    history: list[dict] | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Select a cohesive sequence of clips for raw montage assembly.
    Returns (effective_mode, selected_category, clip_plan).
    """
    if mode not in VALID_MODES:
        raise VideoNarratorError(f"Unsupported mode '{mode}'. Expected one of {VALID_MODES}.")

    count = max(1, int(target_clips))
    clip_recency, _, recent_categories = _extract_recent_history(history)

    # Group clips by semantic category
    by_cat: dict[str, list[dict[str, Any]]] = {c: [] for c in VALID_CATEGORIES}
    for clip in clips:
        cat = clip["category"]
        if cat in by_cat:
            by_cat[cat].append(clip)

    # Choose category
    req_cat = category.strip().lower() if isinstance(category, str) and category.strip() else None
    if req_cat and req_cat in VALID_CATEGORIES and by_cat[req_cat]:
        selected_category = req_cat
    else:
        non_empty = [c for c in VALID_CATEGORIES if by_cat[c]]
        if not non_empty:
            selected_category = "city"
        else:
            # Prefer categories with richer clip pools and not just used
            rich_cats = [c for c in non_empty if len(by_cat[c]) >= min(3, count)]
            candidate_cats = rich_cats or non_empty
            fresh_cats = [c for c in candidate_cats if c not in recent_categories[-2:]]
            selected_category = random.choice(fresh_cats or candidate_cats)

    # Resolve auto mode
    if mode == "auto":
        effective_mode = random.choice(["news", "breakdown"])
    else:
        effective_mode = mode

    cat_pool = by_cat.get(selected_category) or clips
    ordered_cat = _order_by_freshness(cat_pool, clip_recency)
    ordered_all = _order_by_freshness(clips, clip_recency)

    # Build a combined freshness-ordered pool:
    # 1) Unseen clips in the chosen category
    # 2) Unseen clips from the rest of the library (prevents repeating used clips while fresh ones remain!)
    # 3) Previously used clips in the chosen category (oldest first)
    # 4) Previously used clips from the rest of the library (oldest first)
    seen_names: set[str] = set()
    unique_pool: list[dict[str, Any]] = []
    unseen_cat = [c for c in ordered_cat if clip_recency.get(c["clip_name"], 0) == 0]
    unseen_all = [c for c in ordered_all if clip_recency.get(c["clip_name"], 0) == 0]
    for c in unseen_cat + unseen_all + ordered_cat + ordered_all:
        if c["clip_name"] not in seen_names:
            seen_names.add(c["clip_name"])
            unique_pool.append(c)

    plan: list[dict[str, Any]] = []

    if effective_mode == "breakdown":
        hero_candidates = [c for c in ordered_cat if c["src_dur"] >= 2.2] or ordered_cat
        hero = hero_candidates[0]
        selected_category = hero["category"] if hero["category"] in VALID_CATEGORIES else selected_category

        # Segment 0: Hero clip establishing shot
        plan.append({**hero, "start_trim": 0.0, "effect": "normal"})

        # Segment 1: Hero clip detail zoom / slow-mo replay
        if count >= 2:
            detail_trim = min(0.6, max(0.0, hero["src_dur"] - 2.2))
            plan.append({**hero, "start_trim": round(detail_trim, 2), "effect": "breakdown_slowmo"})

        # Remaining supporting clips: same-category fresh clips first, then fresh clips from ordered_all
        supp_source = [c for c in unique_pool if c["clip_name"] != hero["clip_name"]] or ordered_cat

        for idx in range(len(plan), count):
            chosen = supp_source[(idx - len(plan)) % len(supp_source)]
            occ = sum(1 for p in plan if p["clip_name"] == chosen["clip_name"])
            max_trim = max(0.0, chosen["src_dur"] - 2.2)
            trim_start = round((occ * 1.4) % max_trim, 2) if max_trim > 0.2 else 0.0
            plan.append({
                **chosen,
                "start_trim": trim_start,
                "effect": "zoom" if idx % 2 == 1 else "normal",
            })
    else:
        # "news" multicut: use distinct clips across the entire library (same-category fresh first,
        # topped up with fresh clips from other categories if category has < count unique clips).
        pool = unique_pool
        used_in_plan: set[str] = set()

        for idx in range(count):
            unused = [c for c in pool if c["clip_name"] not in used_in_plan]
            if unused:
                chosen = unused[0]
            else:
                non_adjacent = [c for c in pool if not plan or c["clip_name"] != plan[-1]["clip_name"]]
                chosen = (non_adjacent or pool)[idx % len(non_adjacent or pool)]

            used_in_plan.add(chosen["clip_name"])
            occ = sum(1 for p in plan if p["clip_name"] == chosen["clip_name"])
            max_trim = max(0.0, chosen["src_dur"] - 2.2)
            trim_start = round((occ * 1.5) % max_trim, 2) if max_trim > 0.2 else 0.0
            plan.append({
                **chosen,
                "start_trim": trim_start,
                "effect": "zoom" if idx % 2 == 1 else "normal",
            })

    # Assign raw montage preview durations (2.8s-3.2s per clip so Gemini sees crisp action)
    cursor = 0.0
    for idx, item in enumerate(plan):
        avail = max(1.0, item["src_dur"] - item["start_trim"])
        preview_dur = round(min(3.0, avail), 3)
        item["index"] = idx
        item["preview_dur"] = preview_dur
        item["raw_start"] = round(cursor, 3)
        cursor += preview_dur
        item["raw_end"] = round(cursor, 3)

    return effective_mode, selected_category, plan


def render_raw_montage(plan: list[dict[str, Any]], montage_raw_path: str) -> str:
    """Assemble the silent raw B-roll montage video (`montage_raw.mp4`) before Vision watching."""
    os.makedirs(os.path.dirname(os.path.abspath(montage_raw_path)), exist_ok=True)

    inputs: list[str] = []
    filters: list[str] = []
    concat_labels: list[str] = []

    for idx, item in enumerate(plan):
        inputs.extend(["-i", item["clip_path"]])
        start_trim = item["start_trim"]
        preview_dur = item["preview_dur"]
        filters.append(
            f"[{idx}:v]trim=start={start_trim:.3f}:duration={preview_dur:.3f},"
            f"setpts=PTS-STARTPTS,fps={FPS},"
            f"scale=720:1280:force_original_aspect_ratio=increase,"
            f"crop=720:1280,setsar=1,format=yuv420p[v{idx}]"
        )
        concat_labels.append(f"[v{idx}]")

    filters.append(f"{''.join(concat_labels)}concat=n={len(plan)}:v=1:a=0[vout]")

    cmd = [
        FFMPEG_BIN, "-y", "-nostdin",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        montage_raw_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if res.returncode != 0 or not os.path.isfile(montage_raw_path) or os.path.getsize(montage_raw_path) < 10_000:
        raise VideoNarratorError(f"FFmpeg raw montage assembly failed: {(res.stderr or '')[-500:]}")

    return montage_raw_path


def _extract_frame_strip(montage_raw_path: str, plan: list[dict[str, Any]], temp_dir: str, run_id: str) -> list[tuple[int, str, float]]:
    """Extract 2 timestamped JPEG frames per segment window as a Vision fallback."""
    frames: list[tuple[int, str, float]] = []
    for item in plan:
        idx = item["index"]
        seg_len = max(0.4, item["raw_end"] - item["raw_start"])
        for f_idx, frac in enumerate((0.25, 0.75)):
            ts = round(item["raw_start"] + seg_len * frac, 3)
            out_jpg = os.path.join(temp_dir, f"{run_id}_frame_{idx:02d}_{f_idx}.jpg")
            cmd = [
                FFMPEG_BIN, "-y", "-nostdin",
                "-ss", f"{ts:.3f}",
                "-i", montage_raw_path,
                "-vframes", "1", "-q:v", "3",
                out_jpg,
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if os.path.isfile(out_jpg) and os.path.getsize(out_jpg) > 1000:
                frames.append((idx, out_jpg, ts))
    return frames


def _build_vision_prompt(
    plan: list[dict[str, Any]],
    mode: str,
    category: str,
    recent_titles: list[str],
) -> str:
    """Build the Watch-Then-Narrate prompt forcing 1:1 visual-to-commentary alignment."""
    windows_desc = "\n".join(
        f"- Segment {item['index']}: {item['raw_start']:.2f}s to {item['raw_end']:.2f}s"
        for item in plan
    )
    past_str = ", ".join(f'"{t}"' for t in recent_titles[-12:]) if recent_titles else "None"
    n = len(plan)

    mode_guidance = (
        "This is a scene breakdown video: treat Segment 0 as the main reveal, Segment 1 as a closer zoomed-in detail observation, and the remaining clips as supporting visual evidence."
        if mode == "breakdown"
        else "This is a fast-paced GTA 6 secrets/details multicut: connect each clip smoothly into one cohesive story while directly reacting to what is on screen in every window."
    )

    return f"""You are an elite viral GTA 6 YouTube Shorts creator watching an assembled silent gameplay montage ({plan[-1]['raw_end']:.2f}s total).

VIDEO CLIP TIMESTAMP WINDOWS (YOU MUST WATCH EVERY WINDOW):
{windows_desc}

MODE: {mode.upper()} | PRIMARY THEME HINT: {category.upper()}
{mode_guidance}

CRITICAL WATCH-THEN-NARRATE RULES:
1. Watch the actual video footage carefully. Describe ONLY what you literally see on screen in each timestamp window. Never invent off-screen events or contradict the visuals.
2. Output EXACTLY {n} segments with "index" 0 through {n - 1}, matching the timestamp windows 1:1.
3. For each segment:
   - "visual_summary": 1 concise factual sentence describing what literally happens on screen in that window.
   - "narration": 14-22 words (approx. 5-7 seconds spoken) of high-retention voiceover directly referencing the on-screen action in that window.
     * Segment 0 MUST open with an immediate scroll-stopping hook referencing what appears right away in Segment 0.
     * Segments 1 to {max(1, n - 2)} MUST use visual callouts ("Notice how...", "Look right at...", "Watch this...") tied to each clip's actual visuals.
     * Segment {n - 1} MUST wrap up the visual on screen plus a quick CTA & question (e.g. "Subscribe for daily GTA 6 details, and tell me: ...").
4. Do NOT reuse any of these recent titles: [{past_str}].
5. "title" must be punchy and <= 55 characters.
6. "description" must be 1-2 engaging teaser sentences + a question for comments (NO hashtags, NO repeating the script).
7. "category" must be one of: "cars", "police", "water", "heist", "city".
8. No stage directions, no timestamps in narration, no brackets, no markdown, no hashtags in narration.

Return ONLY valid JSON:
{{
  "title": "Catchy title <= 55 chars",
  "description": "1-2 sentence teaser + comment question",
  "category": "{category}",
  "segments": [
    {{"index": 0, "visual_summary": "...", "narration": "..."}},
    ...
  ]
}}"""


def _clean_narration_text(text: str) -> str:
    """Strip stage directions, timestamps, hashtags, and normalize whitespace."""
    cleaned = re.sub(r"\[[^\]]*\]", "", text or "")
    cleaned = re.sub(r"\*[^*]*\*", "", cleaned)
    cleaned = re.sub(r"#\w+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _clamp_title(title: str, max_len: int = 55) -> str:
    """Ensure title is non-empty and at most `max_len` characters."""
    clean = re.sub(r"\s+", " ", (title or "").strip()).strip('"\'')
    if not clean:
        return "Insane GTA 6 Details You Missed"
    if len(clean) <= max_len:
        return clean
    truncated = clean[:max_len].rsplit(" ", 1)[0].strip()
    return truncated if len(truncated) >= 15 else clean[:max_len].strip()


def _parse_and_validate_vision_json(
    raw_text: str,
    expected_count: int,
    fallback_category: str,
) -> dict[str, Any]:
    """Parse Gemini Vision JSON output and strictly verify 1:1 segment parity."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Vision response JSON is not an object.")

    raw_segments = data.get("segments")
    if not isinstance(raw_segments, list) or len(raw_segments) != expected_count:
        got = len(raw_segments) if isinstance(raw_segments, list) else type(raw_segments).__name__
        raise ValueError(f"Expected {expected_count} segments, got {got}.")

    by_index: dict[int, dict[str, str]] = {}
    for pos, seg in enumerate(raw_segments):
        if not isinstance(seg, dict):
            raise ValueError(f"Segment at position {pos} is not an object.")
        idx = seg.get("index", pos)
        try:
            idx_int = int(idx)
        except (TypeError, ValueError):
            idx_int = pos

        visual_summary = re.sub(r"\s+", " ", str(seg.get("visual_summary", "")).strip())
        narration = _clean_narration_text(str(seg.get("narration", "")))
        if not visual_summary or not narration:
            raise ValueError(f"Segment {idx_int} missing visual_summary or narration.")
        by_index[idx_int] = {
            "visual_summary": visual_summary,
            "narration": narration,
        }

    if set(by_index.keys()) != set(range(expected_count)):
        if len(raw_segments) == expected_count:
            ordered_segments = [
                {
                    "index": i,
                    "visual_summary": re.sub(r"\s+", " ", str(raw_segments[i].get("visual_summary", "")).strip()),
                    "narration": _clean_narration_text(str(raw_segments[i].get("narration", ""))),
                }
                for i in range(expected_count)
            ]
        else:
            raise ValueError(f"Segment indices mismatch: {sorted(by_index.keys())}")
    else:
        ordered_segments = [
            {"index": i, **by_index[i]} for i in range(expected_count)
        ]

    cat = str(data.get("category", fallback_category)).strip().lower()
    if cat not in VALID_CATEGORIES:
        cat = fallback_category if fallback_category in VALID_CATEGORIES else "city"

    title = _clamp_title(str(data.get("title", "")), max_len=55)
    description = re.sub(r"\s+", " ", str(data.get("description", "")).strip())
    if not description:
        description = "Look closely at every GTA 6 detail in this clip! What caught your eye first?"

    return {
        "title": title,
        "description": description,
        "category": cat,
        "segments": ordered_segments,
    }


def _discover_vision_models(client: genai.Client) -> list[str]:
    """Discover active Vision-capable models on the API key, prioritizing Hydrogen & Flash 3.x."""
    discovered: list[str] = []
    try:
        for m in client.models.list():
            m_id = (getattr(m, "name", "") or "").replace("models/", "")
            low = m_id.lower()
            if not m_id:
                continue
            if any(skip in low for skip in ("tts", "embed", "imagen", "image", "audio", "veo")):
                continue
            if "hydrogen" in low or "flash" in low or "omni" in low:
                discovered.append(m_id)
    except Exception:
        return list(VISION_MODELS)

    if not discovered:
        return list(VISION_MODELS)

    ordered: list[str] = [p for p in VISION_MODELS if p in discovered]
    for d in discovered:
        if "hydrogen" in d.lower() and d not in ordered:
            ordered.insert(0, d)
    return ordered or list(VISION_MODELS)


def _call_vision_with_failover(
    client: genai.Client,
    contents_builder,
    expected_count: int,
    fallback_category: str,
    models: list[str] | None = None,
) -> tuple[dict[str, Any], str]:
    """Execute Gemini Vision generation with model failover, retries, and timeout handling."""
    candidate_models = models or _discover_vision_models(client)
    last_error: Exception | None = None

    for model_name in candidate_models:
        is_hydrogen = "hydrogen" in model_name.lower()
        for attempt in range(1, 4):
            try:
                print(f"      -> Vision analýza přes {model_name} (pokus {attempt}/3)...", flush=True)
                t_cfg = (
                    types.ThinkingConfig(thinking_level="LOW")
                    if is_hydrogen
                    else types.ThinkingConfig(thinking_budget=0)
                )
                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                    thinking_config=t_cfg,
                    http_options=types.HttpOptions(timeout=35000),
                )
                try:
                    res = client.models.generate_content(
                        model=model_name,
                        contents=contents_builder(),
                        config=config,
                    )
                except Exception as inner_exc:
                    inner_msg = str(inner_exc).lower()
                    if "thinking" in inner_msg or "unsupported" in inner_msg:
                        fallback_cfg = types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.7,
                            http_options=types.HttpOptions(timeout=35000),
                        )
                        res = client.models.generate_content(
                            model=model_name,
                            contents=contents_builder(),
                            config=fallback_cfg,
                        )
                    else:
                        raise

                parsed = _parse_and_validate_vision_json(
                    getattr(res, "text", "") or "",
                    expected_count=expected_count,
                    fallback_category=fallback_category,
                )
                return parsed, model_name

            except Exception as exc:
                last_error = exc
                print(f"      ⚠️ {model_name} selhal: {str(exc)[:140]}", flush=True)
                err = str(exc).lower()
                if "404" in err or "not_found" in err or ("invalid_argument" in err and "model" in err):
                    break
                if "429" in err or "resource_exhausted" in err or "quota" in err:
                    time.sleep(min(4.0 * attempt, 8.0))
                elif "503" in err or "unavailable" in err or "high demand" in err:
                    time.sleep(1.5)
                elif "504" in err or "deadline" in err or "timeout" in err or "timed out" in err:
                    time.sleep(1.5)
                else:
                    # JSON validation error or transient failure: brief pause and retry
                    time.sleep(1.0)

    raise VideoNarratorError(f"Vision generation failed across models {candidate_models}: {last_error}")


def _upload_and_wait_active(client: genai.Client, video_path: str, timeout_sec: float = 60.0):
    """Upload video via Gemini Files API and poll until ACTIVE state."""
    uploaded = client.files.upload(file=video_path)
    deadline = time.time() + timeout_sec
    current = uploaded

    while time.time() < deadline:
        state_obj = getattr(current, "state", None)
        state_name = getattr(state_obj, "name", str(state_obj or "")).upper()
        if state_name == "ACTIVE" or state_name == "":
            return current
        if state_name == "FAILED":
            raise VideoNarratorError(f"Gemini file processing failed for {video_path}")
        time.sleep(1.5)
        current = client.files.get(name=uploaded.name)

    raise VideoNarratorError(f"Timed out waiting for Gemini file {uploaded.name} to become ACTIVE.")


def analyze_video_with_gemini(
    client: genai.Client,
    montage_raw_path: str,
    plan: list[dict[str, Any]],
    mode: str,
    category: str,
    recent_titles: list[str],
    temp_dir: str,
    run_id: str,
) -> tuple[dict[str, Any], str]:
    """
    Have Gemini Vision watch `montage_raw_path` using:
      1) Files API upload (with guaranteed cleanup in `finally`),
      2) Inline video bytes fallback,
      3) Timestamped JPEG frame-strip fallback.
    """
    prompt = _build_vision_prompt(plan, mode, category, recent_titles)
    expected_count = len(plan)
    errors: list[str] = []

    # Tier 1: Gemini Files API upload
    uploaded_file = None
    try:
        uploaded_file = _upload_and_wait_active(client, montage_raw_path, timeout_sec=60.0)
        return _call_vision_with_failover(
            client,
            contents_builder=lambda: [uploaded_file, prompt],
            expected_count=expected_count,
            fallback_category=category,
        )
    except Exception as exc:
        errors.append(f"files_upload: {exc}")
    finally:
        if uploaded_file is not None and getattr(uploaded_file, "name", None):
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass

    # Tier 2: Inline video bytes (if under size limit)
    try:
        file_size = os.path.getsize(montage_raw_path)
        if file_size <= MAX_INLINE_VIDEO_BYTES:
            with open(montage_raw_path, "rb") as fh:
                video_bytes = fh.read()
            return _call_vision_with_failover(
                client,
                contents_builder=lambda: [
                    types.Part.from_bytes(data=video_bytes, mime_type="video/mp4"),
                    prompt,
                ],
                expected_count=expected_count,
                fallback_category=category,
            )
        errors.append(f"inline_video: skipped ({file_size} bytes > {MAX_INLINE_VIDEO_BYTES})")
    except Exception as exc:
        errors.append(f"inline_video: {exc}")

    # Tier 3: Timestamped frame-strip fallback
    frame_records: list[tuple[int, str, float]] = []
    try:
        frame_records = _extract_frame_strip(montage_raw_path, plan, temp_dir, run_id)
        if not frame_records:
            raise VideoNarratorError("No frames extracted for frame-strip fallback.")

        frame_parts: list[Any] = []
        for seg_idx, jpg_path, ts in frame_records:
            with open(jpg_path, "rb") as fh:
                img_bytes = fh.read()
            frame_parts.append(f"[Clip {seg_idx} @ {ts:.2f}s]")
            frame_parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
        frame_parts.append(prompt)

        return _call_vision_with_failover(
            client,
            contents_builder=lambda: frame_parts,
            expected_count=expected_count,
            fallback_category=category,
        )
    except Exception as exc:
        errors.append(f"frame_strip: {exc}")
    finally:
        for _, jpg_path, _ in frame_records:
            try:
                if os.path.exists(jpg_path):
                    os.remove(jpg_path)
            except OSError:
                pass

    raise VideoNarratorError("All Gemini Vision watch/fallback paths failed: " + " | ".join(errors))


def _synthesize_edge_tts(text: str, out_path: str) -> None:
    """Synthesize speech using Edge-TTS safely from sync or async caller contexts."""
    import edge_tts

    async def _run():
        communicate = edge_tts.Communicate(text, EDGE_FALLBACK_VOICE, rate=EDGE_FALLBACK_RATE)
        await communicate.save(out_path)

    try:
        asyncio.get_running_loop()
        # Running inside an active event loop: run in a dedicated worker thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(_run())).result(timeout=45)
    except RuntimeError:
        asyncio.run(_run())


def _normalize_audio_to_frame_aligned_wav(raw_audio_path: str, wav_out_path: str) -> float:
    """
    Convert encoded audio or raw Gemini PCM (s16le 24kHz mono) into 44.1 kHz
    mono 16-bit WAV padded to an exact multiple of SAMPLES_PER_FRAME (1470).
    Returns exact duration in seconds.
    """
    conv_cmd = [
        FFMPEG_BIN, "-y", "-nostdin",
        "-i", raw_audio_path,
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le",
        wav_out_path,
    ]
    res = subprocess.run(conv_cmd, capture_output=True, text=True, timeout=30)
    if res.returncode != 0:
        pcm_cmd = [
            FFMPEG_BIN, "-y", "-nostdin",
            "-f", "s16le", "-ar", "24000", "-ac", "1",
            "-i", raw_audio_path,
            "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le",
            wav_out_path,
        ]
        res_pcm = subprocess.run(pcm_cmd, capture_output=True, text=True, timeout=30)
        if res_pcm.returncode != 0:
            raise VideoNarratorError(f"FFmpeg audio normalization failed: {(res_pcm.stderr or '')[-400:]}")

    with wave.open(wav_out_path, "rb") as w_in:
        params = w_in.getparams()
        frames = w_in.readframes(params.nframes)

    if params.nframes <= 0:
        raise VideoNarratorError(f"Normalized segment audio is empty: {wav_out_path}")

    rem = params.nframes % SAMPLES_PER_FRAME
    if rem != 0:
        pad_samples = SAMPLES_PER_FRAME - rem
        frames = frames + (b"\x00\x00" * pad_samples)
        with wave.open(wav_out_path, "wb") as w_out:
            w_out.setnchannels(1)
            w_out.setsampwidth(2)
            w_out.setframerate(SAMPLE_RATE)
            w_out.writeframes(frames)

    total_samples = len(frames) // 2
    return total_samples / float(SAMPLE_RATE)


def synthesize_segment_audio(
    client: genai.Client | None,
    text: str,
    raw_out_path: str,
    wav_out_path: str,
    voice: str = "Orion",
) -> float:
    """Synthesize TTS for one segment (Gemini TTS with Edge-TTS fallback) and normalize to WAV."""
    audio_bytes: bytes | None = None

    if client is not None:
        tts_client = genai.Client(
            api_key=client._api_client.api_key if hasattr(client, "_api_client") else os.environ.get("GEMINI_API_KEY"),
            http_options=types.HttpOptions(api_version="v1alpha", timeout=30000),
        )
        for model_name in TTS_MODELS:
            for attempt in range(1, 3):
                try:
                    res = tts_client.models.generate_content(
                        model=model_name,
                        contents=text,
                        config=types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=types.SpeechConfig(
                                voice_config=types.VoiceConfig(
                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                                )
                            ),
                            http_options=types.HttpOptions(timeout=30000),
                        ),
                    )
                    if res and res.candidates:
                        for cand in res.candidates:
                            if not cand.content or not cand.content.parts:
                                continue
                            for part in cand.content.parts:
                                if part.inline_data and part.inline_data.data:
                                    audio_bytes = part.inline_data.data
                                    break
                            if audio_bytes:
                                break
                    if audio_bytes:
                        break
                except Exception as exc:
                    err = str(exc).lower()
                    if "404" in err or "not_found" in err:
                        break
                    if "429" in err or "resource_exhausted" in err:
                        time.sleep(2.0 * attempt)
                    elif "503" in err or "unavailable" in err:
                        time.sleep(1.0)
                        break
                    else:
                        break
            if audio_bytes:
                break

    if audio_bytes:
        with open(raw_out_path, "wb") as fh:
            fh.write(audio_bytes)
    else:
        _synthesize_edge_tts(text, raw_out_path)

    try:
        return _normalize_audio_to_frame_aligned_wav(raw_out_path, wav_out_path)
    finally:
        if os.path.exists(raw_out_path):
            try:
                os.remove(raw_out_path)
            except OSError:
                pass


def concatenate_wav_segments(segment_wavs: list[str], combined_wav_path: str) -> float:
    """Losslessly concatenate normalized 44.1 kHz mono WAV segments into one track."""
    if not segment_wavs:
        raise VideoNarratorError("No audio segments provided for concatenation.")

    all_frames = bytearray()
    for wav_p in segment_wavs:
        with wave.open(wav_p, "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != SAMPLE_RATE:
                raise VideoNarratorError(f"Unexpected WAV format in {wav_p}")
            all_frames.extend(w.readframes(w.getnframes()))

    with wave.open(combined_wav_path, "wb") as w_out:
        w_out.setnchannels(1)
        w_out.setsampwidth(2)
        w_out.setframerate(SAMPLE_RATE)
        w_out.writeframes(bytes(all_frames))

    total_samples = len(all_frames) // 2
    return total_samples / float(SAMPLE_RATE)


def render_synced_video(segments: list[dict[str, Any]], synced_video_path: str) -> str:
    """
    Render silent 1080x1920 @ 30fps yuv420p video where each clip i is locked
    frame-accurately to `segments[i]["duration"]`.
    """
    if not segments:
        raise VideoNarratorError("No segments provided to render synced video.")

    inputs: list[str] = []
    filters: list[str] = []
    concat_labels: list[str] = []

    for idx, seg in enumerate(segments):
        target_dur = float(seg["duration"])
        target_frames = max(1, round(target_dur * FPS))
        src_dur = float(seg["src_dur"])
        start_trim = float(seg.get("start_trim", 0.0))
        effect = seg.get("effect", "normal")

        # Determine speed / looping so clip cleanly covers `target_dur`
        use_loop = False
        if effect == "breakdown_slowmo":
            speed_factor = 1.25
            needed_src = target_dur / speed_factor
            if src_dur < needed_src + 0.05:
                use_loop = True
                speed_factor = 1.0
        elif src_dur >= target_dur:
            speed_factor = 1.0
            needed_src = target_dur
        elif (target_dur / max(0.1, src_dur)) <= 1.35:
            speed_factor = target_dur / src_dur
            needed_src = src_dur
        else:
            use_loop = True
            speed_factor = 1.0
            needed_src = target_dur

        if use_loop:
            inputs.extend(["-stream_loop", "-1", "-i", seg["clip_path"]])
            eff_trim = 0.0
        else:
            inputs.extend(["-i", seg["clip_path"]])
            if src_dur - start_trim >= needed_src + 0.05:
                eff_trim = start_trim
            else:
                eff_trim = max(0.0, src_dur - needed_src - 0.02)

        if effect == "breakdown_slowmo":
            scale_crop = (
                f"scale=1404:2496:force_original_aspect_ratio=increase,"
                f"crop={TARGET_WIDTH}:{TARGET_HEIGHT}:(in_w-out_w)/2:(in_h-out_h)/2,setsar=1"
            )
        elif effect == "zoom":
            scale_crop = (
                f"scale=1242:2208:force_original_aspect_ratio=increase,"
                f"crop={TARGET_WIDTH}:{TARGET_HEIGHT},setsar=1"
            )
        else:
            scale_crop = (
                f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={TARGET_WIDTH}:{TARGET_HEIGHT},setsar=1"
            )

        filters.append(
            f"[{idx}:v]trim=start={eff_trim:.4f},setpts={speed_factor:.6f}*(PTS-STARTPTS),"
            f"fps={FPS},tpad=stop_mode=clone:stop_duration=0.35,"
            f"trim=start_frame=0:end_frame={target_frames},setpts=PTS-STARTPTS,"
            f"{scale_crop},format=yuv420p[v{idx}]"
        )
        concat_labels.append(f"[v{idx}]")

    filters.append(f"{''.join(concat_labels)}concat=n={len(segments)}:v=1:a=0[vout]")

    cmd = [
        FFMPEG_BIN, "-y", "-nostdin",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        synced_video_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0 or not os.path.isfile(synced_video_path) or os.path.getsize(synced_video_path) < 10_000:
        raise VideoNarratorError(f"FFmpeg synced video render failed: {(res.stderr or '')[-600:]}")

    return synced_video_path


def create_narrated_video_sequence(
    broll_dir: str,
    temp_dir: str,
    mode: str = "auto",
    history: list[dict] | None = None,
    category: str | None = None,
    voice: str = "Orion",
    api_key: str | None = None,
    target_clips: int = 7,
) -> dict[str, Any]:
    """
    Execute the full Video-First (Watch-Then-Narrate) pipeline:
    1) Select B-roll clips avoiding history repeats and assemble silent `montage_raw.mp4`.
    2) Have Gemini Vision watch `montage_raw.mp4` and generate 1:1 segmented commentary.
    3) Synthesize per-segment TTS voiceover and frame-lock each clip to its segment audio.
    """
    os.makedirs(temp_dir, exist_ok=True)
    resolved_key = _load_api_key(api_key=api_key, broll_dir=broll_dir)
    client = genai.Client(api_key=resolved_key)

    run_id = f"vn_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    montage_raw_path = os.path.join(temp_dir, f"{run_id}_montage_raw.mp4")
    combined_audio_path = os.path.join(temp_dir, f"{run_id}_voice.wav")
    synced_video_path = os.path.join(temp_dir, f"{run_id}_synced.mp4")

    # 1. Discover clips & build raw silent montage
    print("   [VN 1/5] 📂 Skenuji knihovnu B-roll a vybírám neokoukané klipy...", flush=True)
    clips = discover_broll_clips(broll_dir, probe_all=False)
    effective_mode, selected_category, plan = select_clip_sequence(
        clips=clips,
        mode=mode,
        category=category,
        target_clips=target_clips,
        history=history,
    )

    # Probe exact durations only for the selected clips in `plan` (0.2s vs 25s for 350 clips)
    probed_cache: dict[str, float] = {}
    cursor = 0.0
    for item in plan:
        cp = item["clip_path"]
        if cp not in probed_cache:
            probed_cache[cp] = probe_media_duration(cp)
        real_dur = max(1.0, probed_cache[cp])
        item["src_dur"] = real_dur
        if item["start_trim"] >= real_dur - 1.0:
            item["start_trim"] = max(0.0, round(real_dur - 2.2, 2))
        avail = max(1.0, real_dur - item["start_trim"])
        preview_dur = round(min(3.0, avail), 3)
        item["preview_start"] = round(cursor, 3)
        item["preview_dur"] = preview_dur
        cursor += preview_dur
        item["preview_end"] = round(cursor, 3)

    print(
        f"   [VN 2/5] 🎞️ Renderuji tichou montáž ({len(plan)} klipů z {len(clips)} dostupných, režim {effective_mode.upper()}, kategorie {selected_category.upper()})...",
        flush=True,
    )
    render_raw_montage(plan, montage_raw_path)

    # 2. Gemini Vision watches the assembled montage & writes 1:1 segmented script
    print("   [VN 3/5] 👁️ Nahrávám tiché video na Gemini Vision, AI ho sleduje a píše komentář...", flush=True)
    _, recent_titles, _ = _extract_recent_history(history)
    vision_data, model_used = analyze_video_with_gemini(
        client=client,
        montage_raw_path=montage_raw_path,
        plan=plan,
        mode=effective_mode,
        category=selected_category,
        recent_titles=recent_titles,
        temp_dir=temp_dir,
        run_id=run_id,
    )

    # 3. Synthesize TTS per segment and build frame-accurate timelines
    segments: list[dict[str, Any]] = []
    segment_wavs: list[str] = []
    timeline_cursor = 0.0

    for idx, plan_item in enumerate(plan):
        v_seg = vision_data["segments"][idx]
        print(f"   [VN 4/5] 🗣️ Generuji dabing pro segment {idx + 1}/{len(plan)}...", flush=True)
        raw_seg_path = os.path.join(temp_dir, f"{run_id}_seg_{idx:02d}_raw.dat")
        wav_seg_path = os.path.join(temp_dir, f"{run_id}_seg_{idx:02d}.wav")

        seg_dur = synthesize_segment_audio(
            client=client,
            text=v_seg["narration"],
            raw_out_path=raw_seg_path,
            wav_out_path=wav_seg_path,
            voice=voice,
        )
        start_t = round(timeline_cursor, 6)
        end_t = round(timeline_cursor + seg_dur, 6)
        timeline_cursor = end_t

        segment_wavs.append(wav_seg_path)
        segments.append({
            "index": idx,
            "clip_path": plan_item["clip_path"],
            "clip_name": plan_item["clip_name"],
            "src_dur": plan_item["src_dur"],
            "start_trim": plan_item["start_trim"],
            "effect": plan_item["effect"],
            "visual_summary": v_seg["visual_summary"],
            "narration": v_seg["narration"],
            "start_time": start_t,
            "end_time": end_t,
            "duration": round(seg_dur, 6),
            "audio_path": wav_seg_path,
        })

    total_duration = round(concatenate_wav_segments(segment_wavs, combined_audio_path), 6)

    # 4. Render frame-locked silent video matching every segment duration
    print(f"   [VN 5/5] 🔒 Skládám finální frame-locked video ({total_duration:.1f}s)...", flush=True)
    render_synced_video(segments, synced_video_path)

    cut_timestamps = [round(seg["end_time"], 4) for seg in segments[:-1]]
    used_clips = list(dict.fromkeys(seg["clip_name"] for seg in segments))
    full_script = " ".join(seg["narration"] for seg in segments).strip()

    return {
        "title": vision_data["title"],
        "description": vision_data["description"],
        "category": vision_data["category"],
        "mode": effective_mode,
        "script": full_script,
        "synced_video_path": synced_video_path,
        "audio_path": combined_audio_path,
        "montage_raw_path": montage_raw_path,
        "total_duration": total_duration,
        "cut_timestamps": cut_timestamps,
        "used_clips": used_clips,
        "model_used": model_used,
        "segments": segments,
    }
