# SubbeX

SubbeX is a macOS menu bar app that turns local video or audio files into `.srt`
subtitle files using a local Whisper model. It is designed for fully offline
work after the first model download and avoids any cloud transcription calls.

## Why this stack

This implementation uses Python plus native AppKit via PyObjC:

- AppKit gives us a real macOS menu bar app, temporary panels, Finder reveal,
  and a Dock-free accessory app mode.
- `faster-whisper` gives us strong local Whisper transcription, model choice,
  and practical long-file handling on CPU-only Macs.
- `py2app` provides a straightforward path to a standard `.app` bundle while the
  same code can also run directly from a virtual environment.

I did not choose Electron because it adds packaging weight for a tiny menu bar
utility, and I did not choose a Core ML-only path because it complicates model
support across Intel and Apple Silicon machines.

## Features

- Menu bar only: no Dock icon and no persistent window
- Click the menu bar item or drop media directly onto it
- Local Whisper transcription with selectable models
- ffmpeg-based audio extraction with an enhanced speech-friendly filter pass and
  a safe fallback extraction mode
- Subtitle cleanup tuned for noisy or non-standard production audio:
  - low-confidence segment suppression
  - repeated-text artifact filtering
  - short adjacent segment merging
  - line wrapping near 42 characters
  - max 2 lines per subtitle block
- Positive or negative timestamp offset
- Dedicated export folders with optional original-file move
- Finder reveal on completion and readable alerts on failure

## Install

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,app]"
```

2. Install `ffmpeg` if it is not already available:

```bash
brew install ffmpeg
```

3. Run the app from the virtualenv:

```bash
subbex
```

The first time you use a given model, `faster-whisper` will download it into the
app data directory. After that, the app can run offline.

## Package as a `.app`

From the active virtual environment:

```bash
python setup.py py2app
```

The application bundle will be created in `dist/SubbeX.app`.

## ffmpeg lookup

SubbeX checks:

- `$FFMPEG_PATH`
- `$FFPROBE_PATH`
- the current `PATH`
- Homebrew defaults such as `/opt/homebrew/bin/ffmpeg`
- common Intel Homebrew paths such as `/usr/local/bin/ffmpeg`

If `ffmpeg` or `ffprobe` cannot be found, the app shows a readable setup error.

## Verification

The included tests focus on subtitle post-processing because that logic is easy
to verify in isolation without a GUI session:

```bash
PYTHONPATH=src pytest
```

