from __future__ import annotations

from pathlib import Path
from typing import Callable

from platformdirs import user_data_dir

from .exceptions import DependencyError, JobError
from .models import SubtitleSegment


ProgressCallback = Callable[[str, float, str], None]


class FasterWhisperTranscriber:
    def __init__(self) -> None:
        self.model_cache_root = Path(user_data_dir("SubbeX", "SubbeX")) / "models"
        self.model_cache_root.mkdir(parents=True, exist_ok=True)
        self._model_cache: dict[str, object] = {}

    def transcribe(
        self,
        audio_path: Path,
        model_id: str,
        total_duration: float,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[list[SubtitleSegment], str | None]:
        model = self._get_model(model_id)

        try:
            segment_generator, info = model.transcribe(
                str(audio_path),
                beam_size=5 if model_id in {"medium", "large-v3"} else 3,
                best_of=5 if model_id in {"medium", "large-v3"} else 3,
                temperature=0.0,
                condition_on_previous_text=False,
                repetition_penalty=1.15,
                compression_ratio_threshold=2.0,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.72,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 450, "speech_pad_ms": 250},
                word_timestamps=False,
                chunk_length=30,
            )
        except OSError as exc:
            raise JobError(
                "The Whisper model could not be loaded. If this is the first run, "
                "connect once to download the model, then the app can run offline."
            ) from exc
        except Exception as exc:  # pragma: no cover - dependency-specific
            raise JobError(f"Whisper transcription could not start: {exc}") from exc

        subtitles: list[SubtitleSegment] = []
        detected_language = getattr(info, "language", None)

        try:
            for raw_segment in segment_generator:
                segment = SubtitleSegment(
                    start=float(raw_segment.start),
                    end=float(raw_segment.end),
                    text=str(raw_segment.text),
                    avg_logprob=float(raw_segment.avg_logprob) if raw_segment.avg_logprob is not None else None,
                    no_speech_prob=float(raw_segment.no_speech_prob) if raw_segment.no_speech_prob is not None else None,
                )
                subtitles.append(segment)
                if progress_callback and total_duration > 0:
                    progress_callback(
                        "transcribing",
                        min(segment.end / total_duration, 0.995),
                        "Transcribing speech locally...",
                    )
        except Exception as exc:  # pragma: no cover - dependency-specific
            raise JobError(f"Whisper transcription failed: {exc}") from exc

        if progress_callback:
            progress_callback("transcribing", 1.0, "Transcription complete.")
        return subtitles, detected_language

    def _get_model(self, model_id: str):
        if model_id in self._model_cache:
            return self._model_cache[model_id]

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise DependencyError(
                "The Python package 'faster-whisper' is not installed. "
                "Install project dependencies in the virtual environment first."
            ) from exc

        try:
            model = WhisperModel(
                model_id,
                device="cpu",
                compute_type="int8",
                download_root=str(self.model_cache_root),
            )
        except Exception as exc:  # pragma: no cover - dependency-specific
            raise JobError(f"Could not prepare the '{model_id}' Whisper model: {exc}") from exc

        self._model_cache[model_id] = model
        return model

