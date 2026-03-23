from subbex.models import SubtitleSegment
from subbex.subtitles import post_process_segments, render_srt


def test_merges_short_adjacent_segments():
    segments = [
        SubtitleSegment(0.0, 1.0, "Hello there"),
        SubtitleSegment(1.2, 2.0, "general Kenobi"),
    ]

    processed = post_process_segments(segments, offset_seconds=0.0)

    assert len(processed) == 1
    assert processed[0].text == "Hello there general Kenobi"


def test_filters_low_confidence_and_repetition():
    segments = [
        SubtitleSegment(0.0, 1.0, "noise noise noise noise", avg_logprob=-0.5),
        SubtitleSegment(1.2, 2.2, "clear dialogue", avg_logprob=-0.2),
        SubtitleSegment(2.5, 3.0, "mumble", avg_logprob=-1.5),
    ]

    processed = post_process_segments(segments, offset_seconds=0.0)

    assert [segment.text for segment in processed] == ["clear dialogue"]


def test_splits_long_segments_and_wraps_to_two_lines():
    text = "This is a deliberately long subtitle line that should be split into multiple subtitle blocks to stay readable on screen."
    processed = post_process_segments([SubtitleSegment(0.0, 6.0, text)], offset_seconds=0.0)

    assert len(processed) >= 2

    srt = render_srt(processed)
    blocks = [block for block in srt.strip().split("\n\n") if block]
    assert len(blocks) == len(processed)
    for block in blocks:
        lines = block.splitlines()[2:]
        assert len(lines) <= 2
        assert all(len(line) <= 48 for line in lines)


def test_negative_offset_clamps_to_zero():
    processed = post_process_segments(
        [SubtitleSegment(1.0, 2.0, "hello world")],
        offset_seconds=-2.0,
    )

    assert processed[0].start == 0.0
    assert processed[0].end > 0.0
