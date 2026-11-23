import os, math, wave, struct, random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SFX_DIR = os.path.join(BASE_DIR, "assets", "sfx")

def ensure_sfx_assets(sfx_dir: str = SFX_DIR):
    os.makedirs(sfx_dir, exist_ok=True)
    impact_p = os.path.join(sfx_dir, "impact.wav")
    whoosh_p = os.path.join(sfx_dir, "whoosh.wav")

    if not os.path.exists(impact_p) or os.path.getsize(impact_p) < 1000:
        duration, sample_rate = 1.0, 44100
        num_samples = int(duration * sample_rate)
        with wave.open(impact_p, 'w') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(sample_rate)
            frames = bytearray()
            for i in range(num_samples):
                t = i / sample_rate
                freq = 150.0 * math.exp(-3.5 * t) + 40.0
                sample = int(math.exp(-3.8 * t) * (1.0 - math.exp(-22.0 * t)) * 30000.0 * math.sin(2.0 * math.pi * freq * t))
                frames.extend(struct.pack('<h', max(-32768, min(32767, sample))))
            wav.writeframes(frames)

    if not os.path.exists(whoosh_p) or os.path.getsize(whoosh_p) < 1000:
        duration, sample_rate = 0.45, 44100
        num_samples = int(duration * sample_rate)
        with wave.open(whoosh_p, 'w') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(sample_rate)
            frames = bytearray()
            last_val = 0.0
            for i in range(num_samples):
                t = i / sample_rate
                rel_t = t / duration
                noise = (random.random() * 2.0 - 1.0)
                last_val = 0.85 * last_val + 0.15 * noise
                tone = math.sin(2.0 * math.pi * (200 + 400 * math.sin(math.pi * rel_t)) * t) * 0.3
                sample = int((last_val * 0.7 + tone) * (math.sin(math.pi * rel_t) ** 2.5) * 24000.0)
                frames.extend(struct.pack('<h', max(-32768, min(32767, sample))))
            wav.writeframes(frames)

def build_sfx_track(cut_timestamps: list, total_duration: float, out_path: str, sfx_dir: str = SFX_DIR, sample_rate: int = 44100) -> str:
    ensure_sfx_assets(sfx_dir)
    impact_p, whoosh_p = os.path.join(sfx_dir, "impact.wav"), os.path.join(sfx_dir, "whoosh.wav")
    total_samples = int((total_duration + 1.0) * sample_rate)
    buffer = [0.0] * total_samples

    def overlay(wav_path, start_time, vol=1.0):
        if not os.path.exists(wav_path): return
        with wave.open(wav_path, 'r') as w:
            n = w.getnframes()
            samples = struct.unpack(f"<{n}h", w.readframes(n))
            st = int(start_time * sample_rate)
            for i, smp in enumerate(samples):
                if 0 <= st + i < total_samples: buffer[st + i] += (smp / 32768.0) * vol

    overlay(impact_p, 0.0, vol=0.38)
    for c in cut_timestamps: overlay(whoosh_p, max(0.0, c - 0.20), vol=0.20)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with wave.open(out_path, 'w') as out_w:
        out_w.setnchannels(1); out_w.setsampwidth(2); out_w.setframerate(sample_rate)
        out_frames = bytearray()
        for s in buffer:
            out_frames.extend(struct.pack('<h', int(max(-1.0, min(1.0, s)) * 32767.0)))
        out_w.writeframes(out_frames)
    return out_path
