from __future__ import annotations

import re
from dataclasses import replace
from datetime import timedelta

from .models import SubtitleSegment


MAX_LINE_WIDTH = 42
MAX_LINES = 2
MAX_BLOCK_CHARS = MAX_LINE_WIDTH * MAX_LINES


def post_process_segments(segments: list[SubtitleSegment], offset_seconds: float) -> list[SubtitleSegment]:
    cleaned = [segment for segment in (_clean_segment(segment) for segment in segments) if segment is not None]
    filtered = [segment for segment in cleaned if _keep_segment(segment)]
    merged = _merge_adjacent_segments(filtered)
    split = _split_long_segments(merged)
    shifted = _apply_offset(split, offset_seconds)
    return [segment for segment in shifted if segment.end > segment.start and segment.text.strip()]


def render_srt(segments: list[SubtitleSegment]) -> str:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(f"{_format_timestamp(segment.start)} --> {_format_timestamp(segment.end)}")
        lines.append(_wrap_subtitle_text(segment.text))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _clean_segment(segment: SubtitleSegment) -> SubtitleSegment | None:
    text = " ".join(segment.text.replace("\n", " ").split())
    if not text:
        return None
    return replace(segment, text=text)


def _keep_segment(segment: SubtitleSegment) -> bool:
    text = segment.text.strip()
    if not text:
        return False
    if _looks_repetitive(text):
        return False
    if segment.avg_logprob is not None and segment.avg_logprob < -1.15:
        return False
    if (
        segment.no_speech_prob is not None
        and segment.no_speech_prob > 0.82
        and len(text) < 20
    ):
        return False
    return True


def _looks_repetitive(text: str) -> bool:
    words = re.findall(r"[A-Za-z0-9']+", text.lower())
    if len(words) < 4:
        return False

    unique_ratio = len(set(words)) / len(words)
    if len(words) >= 8 and unique_ratio < 0.42:
        return True

    for size in range(1, min(5, len(words) // 2) + 1):
        phrase = words[:size]
        repeated = phrase * (len(words) // size)
        if repeated[: len(words)] == words and len(words) >= size * 3:
            return True

    consecutive = 1
    for previous, current in zip(words, words[1:]):
        consecutive = consecutive + 1 if previous == current else 1
        if consecutive >= 4:
            return True
    return False


def _merge_adjacent_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    if not segments:
        return []

    merged: list[SubtitleSegment] = [segments[0]]
    for segment in segments[1:]:
        previous = merged[-1]
        gap = segment.start - previous.end
        combined_text = f"{previous.text} {segment.text}".strip()
        short_pair = (
            len(previous.text) <= 28
            or len(segment.text) <= 28
            or (previous.end - previous.start) <= 1.6
            or (segment.end - segment.start) <= 1.6
        )
        if gap <= 0.45 and short_pair and len(combined_text) <= MAX_BLOCK_CHARS:
            merged[-1] = SubtitleSegment(
                start=previous.start,
                end=segment.end,
                text=combined_text,
                avg_logprob=_min_optional(previous.avg_logprob, segment.avg_logprob),
                no_speech_prob=_max_optional(previous.no_speech_prob, segment.no_speech_prob),
            )
        else:
            merged.append(segment)
    return merged


def _split_long_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    output: list[SubtitleSegment] = []
    for segment in segments:
        if len(segment.text) <= MAX_BLOCK_CHARS:
            output.append(segment)
            continue

        chunks = _chunk_text(segment.text)
        if len(chunks) == 1:
            output.append(segment)
            continue

        total_chars = sum(len(chunk) for chunk in chunks)
        duration = max(segment.end - segment.start, 0.6 * len(chunks))
        current_start = segment.start
        for index, chunk in enumerate(chunks):
            if index == len(chunks) - 1:
                current_end = segment.end
            else:
                ratio = len(chunk) / total_chars
                chunk_duration = max(duration * ratio, 0.6)
                current_end = min(segment.end, current_start + chunk_duration)
            output.append(
                SubtitleSegment(
                    start=current_start,
                    end=current_end,
                    text=chunk,
                    avg_logprob=segment.avg_logprob,
                    no_speech_prob=segment.no_speech_prob,
                )
            )
            current_start = current_end
    return output


def _chunk_text(text: str) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word]).strip()
        if current and len(candidate) > MAX_BLOCK_CHARS:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _apply_offset(segments: list[SubtitleSegment], offset_seconds: float) -> list[SubtitleSegment]:
    shifted: list[SubtitleSegment] = []
    minimum_gap = 0.05
    previous_end = 0.0
    for segment in segments:
        start = max(segment.start + offset_seconds, 0.0)
        end = max(segment.end + offset_seconds, start + 0.2)
        if shifted and start < previous_end:
            delta = previous_end - start + minimum_gap
            start += delta
            end += delta
        shifted.append(replace(segment, start=start, end=end))
        previous_end = end
    return shifted


def _wrap_subtitle_text(text: str) -> str:
    if len(text) <= MAX_LINE_WIDTH:
        return text

    words = text.split()
    best_split = None
    best_score = None
    for index in range(1, len(words)):
        line_one = " ".join(words[:index]).strip()
        line_two = " ".join(words[index:]).strip()
        if not line_one or not line_two:
            continue
        overflow = max(0, len(line_one) - MAX_LINE_WIDTH) + max(0, len(line_two) - MAX_LINE_WIDTH)
        score = (overflow, abs(len(line_one) - len(line_two)), max(len(line_one), len(line_two)))
        if best_score is None or score < best_score:
            best_score = score
            best_split = (line_one, line_two)

    if best_split is None:
        return text
    return "\n".join(best_split)


def _format_timestamp(seconds: float) -> str:
    total_milliseconds = max(0, int(round(seconds * 1000)))
    td = timedelta(milliseconds=total_milliseconds)
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    milliseconds = total_milliseconds % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def _min_optional(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None


def _max_optional(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None
