from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .exceptions import DependencyError, JobError


ProgressCallback = Callable[[str, float, str], None]


@dataclass(frozen=True)
class FFMpegTools:
    ffmpeg: Path
    ffprobe: Path


COMMON_FFMPEG_PATHS = [
    Path("/opt/homebrew/bin/ffmpeg"),
    Path("/opt/homebrew/bin/ffprobe"),
    Path("/usr/local/bin/ffmpeg"),
    Path("/usr/local/bin/ffprobe"),
]


def _candidate_paths(env_name: str, command_name: str) -> list[Path]:
    candidates: list[Path] = []
    env_value = os.environ.get(env_name)
    if env_value:
        candidates.append(Path(env_value))

    which_value = shutil.which(command_name)
    if which_value:
        candidates.append(Path(which_value))

    for candidate in COMMON_FFMPEG_PATHS:
        if candidate.name == command_name:
            candidates.append(candidate)
    return candidates


def find_ffmpeg_tools() -> FFMpegTools:
    ffmpeg_path = next((path for path in _candidate_paths("FFMPEG_PATH", "ffmpeg") if path.exists()), None)
    ffprobe_path = next((path for path in _candidate_paths("FFPROBE_PATH", "ffprobe") if path.exists()), None)

    if ffmpeg_path and not ffprobe_path:
        sibling = ffmpeg_path.with_name("ffprobe")
        if sibling.exists():
            ffprobe_path = sibling

    if ffprobe_path and not ffmpeg_path:
        sibling = ffprobe_path.with_name("ffmpeg")
        if sibling.exists():
            ffmpeg_path = sibling

    if not ffmpeg_path or not ffprobe_path:
        raise DependencyError(
            "ffmpeg and ffprobe are required. Install them with Homebrew "
            "(`brew install ffmpeg`) or set FFMPEG_PATH and FFPROBE_PATH."
        )

    return FFMpegTools(ffmpeg=ffmpeg_path, ffprobe=ffprobe_path)


def probe_duration(input_path: Path, tools: FFMpegTools) -> float:
    command = [
        str(tools.ffprobe),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise JobError(
            f"ffprobe could not read duration for '{input_path.name}': "
            f"{completed.stderr.strip() or completed.stdout.strip() or 'unknown ffprobe error'}"
        )

    try:
        return float((completed.stdout or "0").strip())
    except ValueError as exc:
        raise JobError(f"ffprobe returned an invalid duration for '{input_path.name}'.") from exc


def extract_normalized_audio(
    input_path: Path,
    output_path: Path,
    tools: FFMpegTools,
    total_duration: float,
    progress_callback: ProgressCallback | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    enhanced_filters = "highpass=f=80,lowpass=f=8000,dynaudnorm=f=150:g=15,afftdn=nf=-25"
    last_error = _run_extract_command(
        input_path=input_path,
        output_path=output_path,
        tools=tools,
        total_duration=total_duration,
        filters=enhanced_filters,
        progress_callback=progress_callback,
    )
    if last_error is None:
        return

    if progress_callback:
        progress_callback("preparing", 0.0, "Falling back to safe audio extraction...")

    fallback_error = _run_extract_command(
        input_path=input_path,
        output_path=output_path,
        tools=tools,
        total_duration=total_duration,
        filters=None,
        progress_callback=progress_callback,
    )
    if fallback_error is None:
        return

    raise JobError(
        f"ffmpeg could not extract usable audio from '{input_path.name}'. "
        f"Enhanced pass: {last_error}. Fallback pass: {fallback_error}."
    )


def _run_extract_command(
    input_path: Path,
    output_path: Path,
    tools: FFMpegTools,
    total_duration: float,
    filters: str | None,
    progress_callback: ProgressCallback | None,
) -> str | None:
    command = [
        str(tools.ffmpeg),
        "-nostdin",
        "-y",
        "-v",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
    ]
    if filters:
        command.extend(["-af", filters])
    command.extend(["-c:a", "flac", str(output_path)])

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None

    try:
        for line in process.stdout:
            line = line.strip()
            if line.startswith("out_time_ms=") and total_duration > 0 and progress_callback:
                raw_value = line.split("=", 1)[1] or "0"
                if not raw_value.isdigit():
                    continue
                out_time_ms = int(raw_value)
                progress_callback(
                    "preparing",
                    min((out_time_ms / 1_000_000.0) / total_duration, 0.995),
                    "Extracting and enhancing speech audio...",
                )
        stderr_output = process.stderr.read() if process.stderr is not None else ""
        return_code = process.wait()
    finally:
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

    if return_code == 0:
        if progress_callback:
            progress_callback("preparing", 1.0, "Audio prepared.")
        return None

    error_text = stderr_output.strip() if stderr_output else "unknown ffmpeg error"
    if output_path.exists():
        output_path.unlink(missing_ok=True)
    return error_text
