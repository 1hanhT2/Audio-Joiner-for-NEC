## Audio Mixer (Streamlit + ffmpeg + yt-dlp)

Create a simple, consumer‑grade audio sequence from up to four audio sources (YouTube URLs and/or uploaded files) and up to four local background tracks. No overlay/mixing: each background plays independently before its corresponding audio.

### What it does
- Downloads audio tracks from YouTube URLs and/or processes uploaded audio files
- Optionally changes playback speed for all audio tracks (single slider applied to all)
- Builds this sequence for each i in 1..N (N ≤ 4):
  - background_i → audio_i → silence (default 5s) → audio_i
- Concatenates all segments into one file

### Play order illustrated
For each i:
background_i, then audio_i, then a short silence, then audio_i again. Background tracks are not mixed under the YouTube audio; they are standalone segments.

### Requirements
- Python 3.9+
- ffmpeg on PATH
- yt-dlp on PATH

Install Python packages:
```bash
pip install streamlit yt-dlp
```

On Windows (PowerShell), you can install ffmpeg via `choco install ffmpeg` if you use Chocolatey, or download from the ffmpeg site and add it to PATH.

### Project files
- `streamlit_app.py` – Streamlit UI
- `yt_audio_mix.py` – CLI and core helpers

### Background audio files
Place your background tracks in the project folder, named as follows (any of the listed extensions):
- `background_audiofile_01.(wav|mp3|m4a|aac|flac|ogg|opus)`
- `background_audiofile_02.(...)`
- `background_audiofile_03.(...)`
- `background_audiofile_04.(...)`

Only the first N that exist will be used. Each background_i plays before its corresponding YouTube audio_i.

### Quality defaults (optimized for small files)
- Download: request best audio up to ~160 kbps (`bestaudio[abr<=160]/bestaudio`)
- Processing: 44.1 kHz, 16‑bit stereo PCM (internal)
- Output:
  - MP3 192 kbps (default)
  - WAV (lossless) and M4A/AAC 192 kbps are available

### Run the Streamlit app
```bash
streamlit run streamlit_app.py
```
UI controls:
- **Input Sources**: Choose up to 4 audio sources, each can be:
  - YouTube URL (paste a YouTube link)
  - Upload File (upload MP3, WAV, M4A, AAC, FLAC, OGG, or OPUS files)
  - Skip (leave this slot empty)
- Speed (applies to all audio tracks)
- Silence length between repeats (seconds)
- Background volume (dB) when re-encoding backgrounds for consistency
- Output format (MP3/WAV/M4A)

### Hybrid Input Support
You can now mix different input types:
- Use all YouTube URLs
- Use all uploaded files
- Mix YouTube URLs with uploaded files
- Skip slots you don't need

Example combinations:
- Slot 1: YouTube URL, Slot 2: Upload File, Slot 3: Skip, Slot 4: YouTube URL
- All 4 slots: Upload Files
- All 4 slots: YouTube URLs (original behavior)

### Run via CLI
```bash
python yt_audio_mix.py <url1> <url2> <url3> <url4> \
  --speed 1.0 \
  --silence 5 \
  --bg-dir . \
  --out final_output.mp3
```

Flags:
- `--speed` – playback speed for all YouTube audio (e.g., 1.25)
- `--silence` – seconds of silence between the two repeats of each audio_i
- `--bg-dir` – directory containing `background_audiofile_0N.*`
- `--out` – output file; extension controls encoder (.mp3/.wav/.m4a)

### Notes & tips
- If you provide fewer than 4 audio sources, only the available background files are used (1..N)
- Background segments are re-encoded to PCM WAV to ensure safe concatenation
- Uploaded files are automatically converted to PCM WAV format for processing
- To reduce size further, export MP3 at 128 kbps by changing the encoder settings in `yt_audio_mix.py`
- Supported upload formats: MP3, WAV, M4A, AAC, FLAC, OGG, OPUS

### Troubleshooting
- "Missing required tool(s)": Ensure `ffmpeg` and `yt-dlp` are installed and on PATH
- Audio too loud/quiet: adjust the YouTube speed/level externally before download or trim backgrounds to the desired loudness
- PATH issues on Windows: close/reopen your terminal after installing ffmpeg/yt-dlp


