import os, glob, math, random, subprocess
from config import FFMPEG_PATH, TARGET_WIDTH, TARGET_HEIGHT, BROLL_DIR, MUSIC_DIR, MUSIC_VOLUME, DOWNLOADS_DIR

def get_random_broll_clips(dur: float, b_dir: str = BROLL_DIR):
    target_dir = b_dir or BROLL_DIR
    clips = glob.glob(os.path.join(target_dir, "*.mp4")) if os.path.exists(target_dir) else []
    if not clips:
        clips = glob.glob(os.path.join(DOWNLOADS_DIR, "*.mp4"))
    if not clips: return []
    num_cuts = max(3, math.ceil(dur / 4.5))
    random.shuffle(clips)
    sel = clips[:num_cuts]
    while len(sel) < num_cuts: sel.append(random.choice(clips))
    return sel

def build_multicut_video_short(voice_audio: str, ass_sub: str, out_p: str, dur: float, broll_dir: str = None, music_dir: str = None, *args, **kwargs):
    b_dir = broll_dir or kwargs.get("b_dir") or BROLL_DIR
    m_dir = music_dir or kwargs.get("m_dir") or MUSIC_DIR

    clips = get_random_broll_clips(dur, b_dir)
    tracks = glob.glob(os.path.join(m_dir, "*.mp3")) if os.path.exists(m_dir) else []
    music = random.choice(tracks) if tracks else None
    ass_esc = os.path.abspath(ass_sub).replace(":", "\\:")

    if len(clips) >= 2:
        n = len(clips)
        c_dur = dur / n
        inputs, trims, concat_in = [], [], ""
        for i, c in enumerate(clips):
            inputs.extend(["-i", c])
            trims.append(f"[{i}:v]trim=0:{c_dur:.2f},setpts=PTS-STARTPTS[v{i}];")
            concat_in += f"[v{i}]"
        v_chain = "".join(trims) + f"{concat_in}concat=n={n}:v=1:a=0[vcat];[vcat]setpts=0.98*PTS,scale=1.05*iw:1.05*ih,crop={TARGET_WIDTH}:{TARGET_HEIGHT},eq=contrast=1.06:saturation=1.08:brightness=0.01,subtitles='{ass_esc}'[v]"
        v_idx, m_idx = n, n + 1
    else:
        fallback = clips[0] if clips else os.path.join(DOWNLOADS_DIR, "gta6_clean_gameplay.mp4")
        inputs = ["-stream_loop", "-1", "-i", fallback]
        v_chain = f"[0:v]setpts=0.98*PTS,scale=1.05*iw:1.05*ih,crop=w=ih*(9/16):h=ih:x=(iw-ow)/2:y=(ih-oh)/2,scale={TARGET_WIDTH}:{TARGET_HEIGHT},eq=contrast=1.06:saturation=1.08:brightness=0.01,subtitles='{ass_esc}'[v]"
        v_idx, m_idx = 1, 2

    inputs.extend(["-i", voice_audio])
    if music and os.path.exists(music):
        inputs.extend(["-stream_loop", "-1", "-i", music])
        fade_st = max(1.0, dur - 1.5)
        filter_complex = f"{v_chain};[{m_idx}:a]volume={MUSIC_VOLUME},afade=t=out:st={fade_st:.1f}:d=1.5[bg];[{v_idx}:a]volume=1.0[voice];[voice][bg]amix=inputs=2:duration=first:dropout_transition=2[a]"
        audio_map = ["-map", "[a]"]
    else:
        filter_complex = v_chain
        audio_map = ["-map", f"[{v_idx}:a]"]

    cmd = [FFMPEG_PATH, "-y", *inputs, "-filter_complex", filter_complex, "-map", "[v]", *audio_map, "-t", str(dur + 0.3), "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", out_p]
    tname = os.path.basename(music) if music else "None"
    print(f"Renderuji multicut ({dur:.1f}s, {len(clips)} strihu, hudba: {tname})...")
    return subprocess.run(cmd, capture_output=True).returncode == 0
