#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
FFPROBE = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
YTDLP  = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")

SAMPLE_RATE = "44100"  # Consumer-grade CD sample rate

def run(cmd, cwd=None):
    print(">>", " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        raise SystemExit(f"Command failed with exit code {proc.returncode}")
    return proc.stdout

def require_tools():
    missing = []
    if not YTDLP: missing.append("yt-dlp")
    if not FFMPEG: missing.append("ffmpeg")
    if missing:
        raise SystemExit(f"Missing required tool(s): {', '.join(missing)}.\n"
                         f"Install: pip install yt-dlp  and  ffmpeg (brew/choco/apt).")

def make_10s_music_segment(music_path: Path, out_wav: Path):
    run([FFMPEG, "-y", "-stream_loop", "-1", "-t", "10",
         "-i", str(music_path),
         "-ar", SAMPLE_RATE, "-ac", "2", "-c:a", "pcm_s16le", str(out_wav)])

def make_10s_silence(out_wav: Path):
    run([FFMPEG, "-y",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-t", "10", "-ar", SAMPLE_RATE, "-ac", "2", "-c:a", "pcm_s16le", str(out_wav)])

def make_silence(duration_seconds: float, out_wav: Path):
    """Create a stereo silence file with the given duration (seconds)."""
    run([FFMPEG, "-y",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-t", f"{duration_seconds}", "-ar", SAMPLE_RATE, "-ac", "2", "-c:a", "pcm_s16le", str(out_wav)])

def download_audio(url: str, slot_name: str, work: Path) -> Path:
    """Download consumer-grade audio (~160 kbps) and convert to PCM WAV.

    Downloads the best available audio up to ~160 kbps to keep size reasonable,
    then converts to 44.1 kHz, 16-bit stereo WAV for processing.
    """
    target_base = work / f"{slot_name}.%(ext)s"
    # Prefer <=160 kbps when available; fallback to bestaudio.
    run([YTDLP, "-f", "bestaudio[abr<=160]/bestaudio",
         "--no-playlist", "-o", str(target_base), url])
    candidates = list(work.glob(f"{slot_name}.*"))
    if not candidates:
        raise SystemExit(f"Could not find downloaded audio for {slot_name}.")
    dl_src = candidates[0]
    fixed = work / f"{slot_name}.fixed.wav"
    run([FFMPEG, "-y", "-i", str(dl_src),
         "-ar", SAMPLE_RATE, "-ac", "2", "-c:a", "pcm_s16le", str(fixed)])
    return fixed

def tempo_adjust(in_wav: Path, out_wav: Path, speed: float):
    if speed <= 0:
        raise SystemExit("--speed must be > 0")
    # atempo supports 0.5–2.0 per filter; chain if outside (future-proofing)
    filters = []
    s = speed
    while s > 2.0:
        filters.append("atempo=2.0"); s /= 2.0
    while s < 0.5:
        filters.append("atempo=0.5"); s /= 0.5
    filters.append(f"atempo={s:.6f}")
    run([FFMPEG, "-y", "-i", str(in_wav),
         "-filter:a", ",".join(filters),
         "-ar", SAMPLE_RATE, "-ac", "2", "-c:a", "pcm_s16le", str(out_wav)])

def reencode_to_pcm(in_path: Path, out_wav: Path) -> None:
    """Re-encode any audio to 44.1kHz 16-bit stereo PCM WAV."""
    run([
        FFMPEG,
        "-y",
        "-i", str(in_path),
        "-ar", SAMPLE_RATE, "-ac", "2", "-c:a", "pcm_s16le",
        str(out_wav),
    ])

def build_concat_list(order_paths, list_file: Path):
    with list_file.open("w", encoding="utf-8") as f:
        for p in order_paths:
            f.write(f"file '{p.as_posix()}'\n")

def concat_with_ffmpeg(list_file: Path, output_path: Path):
    cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file)]
    ext = output_path.suffix.lower()
    if ext == ".mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", "192k"]
    elif ext in (".m4a", ".aac"):
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "pcm_s16le"]
    cmd += [str(output_path)]
    run(cmd)

def main():
    parser = argparse.ArgumentParser(description="Download YouTube audio (yt-dlp), speed-adjust, overlay with background tracks, and stitch per pattern.")
    parser.add_argument("urls", nargs="+", help="YouTube URLs (1..4; extras ignored).")
    parser.add_argument("--out", default="final_output.wav", help="Output file (e.g., .wav/.mp3/.m4a).")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Tempo factor for YouTube audio (e.g., 1.25 speeds up 25%%).")
    parser.add_argument("--silence", type=float, default=5.0, help="Silence duration in seconds between repeats of each audio.")
    parser.add_argument("--bg-volume-db", type=float, default=-6.0, help="Background gain in dB (negative is quieter).")
    parser.add_argument("--bg-dir", default=".", help="Directory containing background_audiofile_01..04.*")
    parser.add_argument("--keep-work", action="store_true", help="Keep intermediate files.")
    args = parser.parse_args()

    # Filter out any stray slash-only args (Windows copy/paste mishaps)
    clean_urls = [u for u in (args.urls[:4]) if u.strip() not in {"\\", "/", "|", ""}]

    require_tools()

    if len(clean_urls) == 0:
        raise SystemExit("Provide at least one YouTube URL (up to four).")
    if len(clean_urls) < 4:
        print(f"Note: only {len(clean_urls)} URL(s) provided; will use the first {len(clean_urls)} background file(s).")
    # Resolve background files
    bg_dir = Path(args.bg_dir).expanduser().resolve()
    background_paths = []
    for i in range(1, 5):
        # Accept any common extension
        candidates = []
        base = f"background_audiofile_{i:02d}"
        for ext in (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"):
            p = bg_dir / f"{base}{ext}"
            if p.exists():
                candidates.append(p)
        if candidates:
            background_paths.append(candidates[0])
    if len(background_paths) == 0:
        raise SystemExit("No background_audiofile_0N found in --bg-dir.")

    out_path = Path(args.out).expanduser().resolve()
    work = Path(tempfile.mkdtemp(prefix="yt_audio_mix_")).resolve()
    print(f"Working directory: {work}")

    try:
        # Prepare silence resource
        silenceN = work / "silence.wav"
        make_silence(args.silence, silenceN)

        # Download & normalize video audio tracks
        fixed_tracks = []
        for i, url in enumerate(clean_urls, start=1):
            fixed = download_audio(url, f"video{i}", work)
            fixed_tracks.append(fixed)

        # Tempo-adjust ONLY the video tracks
        if abs(args.speed - 1.0) > 1e-9:
            sped_tracks = []
            for i, t in enumerate(fixed_tracks, start=1):
                out = work / f"video{i}_x{args.speed}.wav"
                tempo_adjust(t, out, args.speed)
                sped_tracks.append(out)
        else:
            sped_tracks = fixed_tracks

        # Prepare background segments (PCM-wav) and build order as:
        # background_i, audio_i, silence, audio_i
        order = []
        for idx, track in enumerate(sped_tracks, start=1):
            bg_idx = min(idx, len(background_paths)) - 1
            bg_src = background_paths[bg_idx]
            bg_pcm = work / f"background_{idx}.wav"
            reencode_to_pcm(bg_src, bg_pcm)

            order.append(bg_pcm)
            order.append(track)
            order.append(silenceN)
            order.append(track)

        # Concat
        list_file = work / "concat_list.txt"
        build_concat_list(order, list_file)
        concat_with_ffmpeg(list_file, out_path)

        print(f"\n✅ Done. Output: {out_path}")
        if not args.keep_work:
            print(f"(Working files kept at: {work})")
    except Exception as e:
        print(f"Error: {e}")
        if not args.keep_work:
            print(f"Leaving work dir for inspection: {work}")
        sys.exit(1)

if __name__ == "__main__":
    main()
