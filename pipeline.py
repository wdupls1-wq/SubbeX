from __future__ import annotations

import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .exceptions import JobError
from .ffmpeg import extract_normalized_audio, find_ffmpeg_tools, probe_duration
from .models import JobRequest, JobResult
from .subtitles import post_process_segments, render_srt
from .transcription import FasterWhisperTranscriber


ProgressCallback = Callable[[str, float, str], None]


class SubtitlePipeline:
    def __init__(self) -> None:
        self.transcriber = FasterWhisperTranscriber()

    def process_job(self, request: JobRequest, progress_callback: ProgressCallback | None = None) -> JobResult:
        input_path = request.input_path.expanduser().resolve()
        preferences = request.preferences

        tools = find_ffmpeg_tools()
        total_duration = probe_duration(input_path, tools)

        with tempfile.TemporaryDirectory(prefix="subbex-") as temp_dir:
            temp_audio = Path(temp_dir) / f"{input_path.stem}.flac"
            if progress_callback:
                progress_callback("preparing", 0.0, "Preparing audio...")
            extract_normalized_audio(
                input_path=input_path,
                output_path=temp_audio,
                tools=tools,
                total_duration=total_duration,
                progress_callback=progress_callback,
            )

            segments, language = self.transcriber.transcribe(
                audio_path=temp_audio,
                model_id=preferences.model_id,
                total_duration=total_duration,
                progress_callback=progress_callback,
            )

        processed_segments = post_process_segments(segments, preferences.offset_seconds)
        if not processed_segments:
            raise JobError(
                "No reliable speech was detected after cleanup. Try a larger model, "
                "a smaller negative or positive timing offset, or a cleaner source track."
            )
        output_folder = self._prepare_output_folder(input_path, preferences.output_root)
        srt_path = output_folder / f"{input_path.stem}.srt"
        srt_path.write_text(render_srt(processed_segments), encoding="utf-8")

        moved_input_path = None
        if preferences.move_original:
            destination = output_folder / input_path.name
            if input_path.resolve() != destination.resolve():
                moved_input_path = Path(shutil.move(str(input_path), str(destination)))

        return JobResult(
            input_path=input_path,
            output_folder=output_folder,
            srt_path=srt_path,
            moved_input_path=moved_input_path,
            detected_language=language,
            subtitle_count=len(processed_segments),
        )

    def _prepare_output_folder(self, input_path: Path, output_root: Path) -> Path:
        root = output_root.expanduser()
        root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_stem = "".join(character if character.isalnum() or character in {" ", "-", "_"} else "_" for character in input_path.stem).strip()
        safe_stem = safe_stem or "export"
        output_folder = root / f"{safe_stem}-{timestamp}"
        counter = 1
        while output_folder.exists():
            counter += 1
            output_folder = root / f"{safe_stem}-{timestamp}-{counter}"
        output_folder.mkdir(parents=True, exist_ok=False)
        return output_folder
