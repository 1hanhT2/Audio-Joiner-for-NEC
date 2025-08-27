"""
Streamlit UI for yt_audio_mix

This app provides a simple interface to:
- Upload a local music file
- Enter up to four YouTube URLs
- Optionally adjust playback speed for the YouTube audio segments
- Produce a stitched audio file following the original script's pattern

It reuses the core functions from yt_audio_mix.py by overriding its `run`
function to stream logs into the UI.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Tuple

import streamlit as st

# Import the original module and reuse its functions
import yt_audio_mix as ym


def _make_ui_runner(log_callback: Callable[[str], None]) -> Callable[..., str]:
    """Create a subprocess runner that streams output lines to the UI.

    Replaces `ym.run` so all called helpers stream their logs here.
    """

    def run_ui(cmd, cwd=None):
        log_callback(">> " + " ".join(str(c) for c in cmd))
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log_callback(line.rstrip("\n"))
        process.wait()
        if process.returncode != 0:
            raise RuntimeError(f"Command failed with exit code {process.returncode}")
        return ""

    return run_ui


def _validate_and_clean_urls(raw_text: str) -> List[str]:
    lines = [l.strip() for l in (raw_text or "").splitlines()]
    urls = [l for l in lines if l and l not in {"/", "\\", "|"}]
    return urls[:4]


def _validate_uploaded_files(uploaded_files: List) -> List:
    """Validate uploaded audio files and return valid ones."""
    valid_files = []
    for file in uploaded_files:
        if file is not None:
            # Check file extension
            file_ext = Path(file.name).suffix.lower()
            if file_ext in ['.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.opus']:
                valid_files.append(file)
            else:
                st.warning(f"Unsupported file format: {file.name}. Supported formats: mp3, wav, m4a, aac, flac, ogg, opus")
    return valid_files[:4]  # Limit to 4 files


def _write_uploaded_file_to_temp(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".bin"
    tmp_dir = Path(tempfile.mkdtemp(prefix="yt_audio_mix_music_"))
    tmp_path = tmp_dir / f"music_input{suffix}"
    with tmp_path.open("wb") as f:
        f.write(uploaded_file.getbuffer())
    return tmp_path


def _run_pipeline(
    urls: List[str],
    uploaded_files: List,
    speed: float,
    silence_seconds: float,
    bg_volume_db: float,
    bg_dir: Path,
    output_ext: str,
    log_callback: Callable[[str], None],
) -> Tuple[Path, Path]:
    """Execute the mixing pipeline using functions from yt_audio_mix.

    Returns (output_file, work_dir)
    """
    if speed <= 0:
        raise ValueError("Speed must be greater than 0")

    # Use the UI-aware runner for logging
    ym.run = _make_ui_runner(log_callback)

    ym.require_tools()

    work = Path(tempfile.mkdtemp(prefix="yt_audio_mix_ui_")).resolve()
    output_path = work / f"final_output{output_ext}"

    log_callback(f"Working directory: {work}")

    # Prepare silence segment according to user choice
    silenceN = work / "silence.wav"
    ym.make_silence(silence_seconds, silenceN)

    # Download and normalize
    fixed_tracks: List[Path] = []
    for i, url in enumerate(urls, start=1):
        fixed = ym.download_audio(url, f"video{i}", work)
        fixed_tracks.append(fixed)

    # Tempo-adjust videos only
    if abs(speed - 1.0) > 1e-9:
        sped_tracks: List[Path] = []
        for i, t in enumerate(fixed_tracks, start=1):
            out = work / f"video{i}_x{speed}.wav"
            ym.tempo_adjust(t, out, speed)
            sped_tracks.append(out)
    else:
        sped_tracks = fixed_tracks

    # Resolve background files
    bg_paths: List[Path] = []
    for i in range(1, 5):
        base = f"background_audiofile_{i:02d}"
        found: Path | None = None
        for ext in (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"):
            candidate = bg_dir / f"{base}{ext}"
            if candidate.exists():
                found = candidate
                break
        if found:
            bg_paths.append(found)

    # Build order per diagram: for each i -> background_i, audio_i, silence, audio_i
    order: List[Path] = []
    for idx, t in enumerate(sped_tracks, start=1):
        bg_idx = min(idx, len(bg_paths)) - 1
        bg = bg_paths[bg_idx]
        # Ensure background is PCM WAV for concat safety
        bg_pcm = work / f"background_{idx}.wav"
        ym.reencode_to_pcm(bg, bg_pcm)

        order.append(bg_pcm)
        order.append(t)
        order.append(silenceN)
        order.append(t)

    # Concat
    list_file = work / "concat_list.txt"
    ym.build_concat_list(order, list_file)
    ym.concat_with_ffmpeg(list_file, output_path)

    return output_path, work


def _init_session_state():
    if "logs" not in st.session_state:
        st.session_state["logs"] = ""
    if "output_data" not in st.session_state:
        st.session_state["output_data"] = None
    if "output_filename" not in st.session_state:
        st.session_state["output_filename"] = None
    if "output_mime" not in st.session_state:
        st.session_state["output_mime"] = None


def _append_log(line: str, log_area):
    st.session_state["logs"] += (line + "\n")
    log_area.code(st.session_state["logs"], language="bash")


def main():
    st.set_page_config(page_title="Audio Mixer", page_icon="🎵", layout="centered")
    _init_session_state()

    st.title("🎵 Audio Mixer")
    st.caption("Mix YouTube audio tracks and/or uploaded files with background music.")

    with st.expander("Requirements", expanded=False):
        st.markdown(
            "- ffmpeg and yt-dlp must be installed and available in PATH.\n"
            "- Install Python deps: `pip install streamlit yt-dlp`"
        )

    # Input Sources Section
    st.header("🎤 Input Sources")
    st.caption("Choose up to 4 audio sources. Mix YouTube URLs and uploaded files as needed.")
    
    # Initialize session state for input types
    if "input_types" not in st.session_state:
        st.session_state["input_types"] = ["YouTube URL"] * 4
    
    # Create input slots
    urls = []
    uploaded_files = []
    
    for i in range(4):
        with st.expander(f"Audio Source {i+1}", expanded=(i == 0)):
            col1, col2 = st.columns([1, 2])
            
            with col1:
                input_type = st.selectbox(
                    f"Input Type {i+1}",
                    options=["YouTube URL", "Upload File", "Skip"],
                    index=["YouTube URL", "Upload File", "Skip"].index(st.session_state["input_types"][i]),
                    key=f"input_type_{i}"
                )
                st.session_state["input_types"][i] = input_type
            
            with col2:
                if input_type == "YouTube URL":
                    url = st.text_input(
                        f"YouTube URL {i+1}",
                        placeholder="https://www.youtube.com/watch?v=...",
                        key=f"url_{i}"
                    )
                    if url.strip():
                        urls.append(url.strip())
                    else:
                        urls.append("")
                        
                elif input_type == "Upload File":
                    uploaded_file = st.file_uploader(
                        f"Upload Audio File {i+1}",
                        type=['mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'opus'],
                        key=f"file_{i}"
                    )
                    uploaded_files.append(uploaded_file)
                else:  # Skip
                    st.info("This slot will be skipped")
                    uploaded_files.append(None)

    # Processing Options
    st.header("⚙️ Processing Options")
    
    col1, col2 = st.columns(2)
    with col1:
        speed = st.slider("Speed (applies to all audio tracks)", min_value=0.25, max_value=4.0, value=1.0, step=0.05)
    with col2:
        silence_seconds = st.slider("Silence between repeats (s)", min_value=1.0, max_value=15.0, value=5.0, step=0.5)

    col3, col4 = st.columns(2)
    with col3:
        bg_volume_db = st.slider("Background volume (dB)", min_value=-40, max_value=0, value=-6, step=1)
    with col4:
        output_ext = st.selectbox("Output format", options=[".mp3", ".wav", ".m4a"], index=0)

    bg_dir = Path(".").resolve()

    start = st.button("Mix Audio", type="primary")
    log_area = st.empty()
    if st.session_state["logs"]:
        log_area.code(st.session_state["logs"], language="bash")

    if start:
        st.session_state["logs"] = ""
        log_area.code(st.session_state["logs"], language="bash")

        # Validate inputs
        valid_urls = [url for url in urls if url.strip()]
        valid_files = [f for f in uploaded_files if f is not None]
        
        if not valid_urls and not valid_files:
            st.error("Please provide at least one audio source (YouTube URL or uploaded file).")
            return

        try:
            def cb(line: str):
                _append_log(line, log_area)

            with st.spinner("Processing..."):
                out_file, work_dir = _run_pipeline(
                    urls=urls,
                    uploaded_files=uploaded_files,
                    speed=float(speed),
                    silence_seconds=float(silence_seconds),
                    bg_volume_db=float(bg_volume_db),
                    bg_dir=bg_dir,
                    output_ext=str(output_ext),
                    log_callback=cb,
                )

            st.success("Done")
            data = out_file.read_bytes()
            
            # Store output data in session state for persistent download
            st.session_state["output_data"] = data
            st.session_state["output_filename"] = f"mixed_audio{output_ext}"
            st.session_state["output_mime"] = "audio/wav" if output_ext == ".wav" else ("audio/mpeg" if output_ext == ".mp3" else "audio/mp4")
            
            st.caption(f"Working directory: {work_dir}")
        except Exception as e:
            st.error(f"Error: {e}")

    # Persistent Download Section
    if st.session_state["output_data"] is not None:
        st.header("📥 Download Your Audio")
        st.success("✅ Your mixed audio is ready for download!")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.download_button(
                label="📥 Download Mixed Audio",
                data=st.session_state["output_data"],
                file_name=st.session_state["output_filename"],
                mime=st.session_state["output_mime"],
                type="primary",
                use_container_width=True
            )
        with col2:
            if st.button("🗑️ Clear Output", help="Clear the current output to start fresh"):
                st.session_state["output_data"] = None
                st.session_state["output_filename"] = None
                st.session_state["output_mime"] = None
                st.rerun()
        
        st.caption("💡 Tip: You can download this file multiple times. Click 'Clear Output' when you're done.")


if __name__ == "__main__":
    main()


