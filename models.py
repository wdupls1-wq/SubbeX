from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelOption:
    model_id: str
    menu_title: str
    description: str


MODEL_OPTIONS = [
    ModelOption("tiny", "Tiny", "Fastest, lowest accuracy"),
    ModelOption("base", "Base", "Fast with better dialog capture"),
    ModelOption("small", "Small", "Balanced speed and accuracy"),
    ModelOption("medium", "Medium", "Slower, stronger on messy audio"),
    ModelOption("large-v3", "Large v3", "Best accuracy, slowest"),
]

MODEL_BY_ID = {option.model_id: option for option in MODEL_OPTIONS}
DEFAULT_MODEL_ID = "small"


@dataclass(frozen=True)
class Preferences:
    model_id: str
    offset_seconds: float
    output_root: Path
    move_original: bool


@dataclass(frozen=True)
class SubtitleSegment:
    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


@dataclass(frozen=True)
class JobRequest:
    input_path: Path
    preferences: Preferences


@dataclass(frozen=True)
class JobProgress:
    phase: str
    fraction: float
    detail: str
    input_path: Path
    queue_depth: int


@dataclass(frozen=True)
class JobResult:
    input_path: Path
    output_folder: Path
    srt_path: Path
    moved_input_path: Path | None
    detected_language: str | None
    subtitle_count: int

