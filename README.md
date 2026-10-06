# Reaction Highlight Cutter

## Requirements
- Python 3.10+
- FFmpeg + ffprobe installed

## Run
```bash
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000

The server downloads the supplied video link with `yt-dlp`, detects scene boundaries with FFmpeg, chooses complete highlight windows targeting roughly 1–3 minutes, combines them, and provides an MP4 preview/download.

For stronger semantic highlight selection (e.g. cricket wickets/sixes or funniest dialogue), add a transcript/vision model and rank candidate windows before `choose_highlights()` returns them.
