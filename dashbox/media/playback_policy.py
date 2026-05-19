from __future__ import annotations

from typing import Any

from .formats import has_audio_format, has_video_format, is_audio_only_format


def known_media_formats(
    formats: list[dict[str, Any]],
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> list[dict[str, Any]]:
    return [fmt for fmt in formats if is_known_media_format(fmt, max_video_height, max_video_fps)]


def is_known_media_format(fmt: dict[str, Any], max_video_height: int = 0, max_video_fps: int = 0) -> bool:
    if is_audio_only_format(fmt):
        return True
    if not has_video_format(fmt):
        return False
    if max_video_height > 0 and video_height(fmt) is None:
        return False
    if max_video_fps > 0 and video_fps(fmt) is None:
        return False
    return True


def is_unknown_media_format(fmt: dict[str, Any]) -> bool:
    if is_audio_only_format(fmt):
        return False
    return not has_video_format(fmt) or video_height(fmt) is None


def has_unknown_codec_direct_url(info: dict[str, Any]) -> bool:
    return (
        bool(info.get("url"))
        and info.get("vcodec") is None
        and info.get("acodec") is None
        and not info.get("manifest_url")
    )


def best_video_format_by_codec_policy(
    formats: list[dict[str, Any]],
    video_codec_order: tuple[str, ...],
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> dict[str, Any] | None:
    candidates = [
        fmt for fmt in formats
        if fmt.get("url")
        and has_video_format(fmt)
        and video_codec_rank(fmt, video_codec_order) is not None
        and video_format_within_caps(fmt, max_video_height, max_video_fps)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda fmt: format_quality_key(fmt, video_codec_order))


def best_format_by_video_codec_policy(
    formats: list[dict[str, Any]],
    video_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> dict[str, Any] | None:
    if not video_codec_order:
        return None
    candidates = [
        fmt for fmt in formats
        if fmt.get("url")
        and has_video_format(fmt)
        and video_codec_rank(fmt, video_codec_order) is not None
        and video_format_within_caps(fmt, max_video_height, max_video_fps)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda fmt: format_quality_key(fmt, video_codec_order))


def formats_with_allowed_video_codecs(
    formats: list[dict[str, Any]],
    video_codec_order: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    if not video_codec_order:
        return formats
    return [
        fmt for fmt in formats
        if video_format_allowed_by_codec_order(fmt, video_codec_order)
    ]


def video_format_allowed_by_codec_order(
    fmt: dict[str, Any],
    video_codec_order: tuple[str, ...] = (),
) -> bool:
    return (
        not video_codec_order
        or not has_video_format(fmt)
        or video_codec_rank(fmt, video_codec_order) is not None
    )


def formats_with_playback_policy(
    formats: list[dict[str, Any]],
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> list[dict[str, Any]]:
    return formats_with_allowed_audio_codecs(
        formats_with_allowed_video_codecs(
            formats_with_video_caps(formats, max_video_height, max_video_fps),
            video_codec_order,
        ),
        audio_codec_order,
    )


def formats_with_allowed_audio_codecs(
    formats: list[dict[str, Any]],
    audio_codec_order: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    if not audio_codec_order:
        return formats
    return [
        fmt for fmt in formats
        if audio_format_allowed_by_codec_order(fmt, audio_codec_order)
    ]


def audio_format_allowed_by_codec_order(
    fmt: dict[str, Any],
    audio_codec_order: tuple[str, ...] = (),
) -> bool:
    return (
        not audio_codec_order
        or not has_audio_format(fmt)
        or audio_codec_rank(fmt, audio_codec_order) is not None
    )


def best_audio_format(
    formats: list[dict[str, Any]],
    audio_codec_order: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    candidates = [fmt for fmt in formats if fmt.get("url") and is_audio_only_format(fmt)]
    if not candidates:
        return None
    return max(candidates, key=lambda fmt: (
        audio_codec_score(fmt, audio_codec_order),
        int(fmt.get("abr") or fmt.get("tbr") or 0),
        int(fmt.get("asr") or 0),
        str(fmt.get("format_id") or ""),
    ))


FormatQualityKey = tuple[int, float, int, int, int, float, int, str]


def format_quality_key(fmt: dict[str, Any], video_codec_order: tuple[str, ...]) -> FormatQualityKey:
    return playback_format_policy_key(fmt, video_codec_order, ())


def single_url_quality_key(
    fmt: dict[str, Any],
    video_codec_order: tuple[str, ...],
    audio_codec_order: tuple[str, ...],
) -> FormatQualityKey:
    return playback_format_policy_key(fmt, video_codec_order, audio_codec_order)


def playback_format_policy_key(
    fmt: dict[str, Any],
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
) -> FormatQualityKey:
    return (
        int(fmt.get("height") or 0),
        float(fmt.get("fps") or 0),
        int(fmt.get("width") or 0),
        audio_codec_score(fmt, audio_codec_order),
        codec_score(fmt, video_codec_order),
        float(fmt.get("tbr") or fmt.get("vbr") or 0),
        int(fmt.get("abr") or 0),
        str(fmt.get("format_id") or ""),
    )


def codec_score(fmt: dict[str, Any], video_codec_order: tuple[str, ...] = ()) -> int:
    rank = video_codec_rank(fmt, video_codec_order)
    if rank is None:
        return 0
    return len(video_codec_order) - rank


def video_codec_rank(fmt: dict[str, Any], video_codec_order: tuple[str, ...]) -> int | None:
    codec = normalize_video_codec(fmt.get("vcodec"))
    if not codec:
        return None
    try:
        return video_codec_order.index(codec)
    except ValueError:
        return None


def audio_codec_score(fmt: dict[str, Any], audio_codec_order: tuple[str, ...] = ()) -> int:
    rank = audio_codec_rank(fmt, audio_codec_order)
    if rank is None:
        return 0
    return len(audio_codec_order) - rank


def audio_codec_rank(fmt: dict[str, Any], audio_codec_order: tuple[str, ...]) -> int | None:
    codec = normalize_audio_codec(fmt.get("acodec"))
    if not codec and not has_audio_format(fmt):
        return None
    try:
        if codec:
            return audio_codec_order.index(codec)
    except ValueError:
        pass
    try:
        return audio_codec_order.index("other")
    except ValueError:
        return None


def normalize_audio_codec(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text or text == "none":
        return ""
    if text.startswith(("mp4a", "aac")):
        return "aac"
    if text.startswith("opus"):
        return "opus"
    compact = text.replace("-", "")
    if compact.startswith("ec3") or compact.startswith("eac3"):
        return "eac3"
    if compact.startswith("ac3"):
        return "ac3"
    if text.startswith("flac"):
        return "flac"
    return ""


def normalize_video_codec(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text or text == "none":
        return ""
    if text.startswith(("vp09", "vp9")):
        return "vp9"
    if text.startswith(("avc1", "avc", "h264")):
        return "h264"
    if text.startswith(("hev1", "hvc1", "hevc", "h265")):
        return "hevc"
    if text.startswith(("av01", "av1")):
        return "av01"
    return text.split(".", 1)[0]


def formats_with_video_caps(
    formats: list[dict[str, Any]],
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> list[dict[str, Any]]:
    if max_video_height <= 0 and max_video_fps <= 0:
        return formats
    return [
        fmt for fmt in formats
        if format_within_video_caps(fmt, max_video_height, max_video_fps)
    ]


def format_within_video_caps(fmt: dict[str, Any], max_video_height: int = 0, max_video_fps: int = 0) -> bool:
    if max_video_height <= 0 and max_video_fps <= 0:
        return True
    if is_audio_only_format(fmt):
        return True
    if not has_video_format(fmt):
        return not _playable_without_video_metadata(fmt)
    return video_format_within_caps(fmt, max_video_height, max_video_fps)


def video_format_within_caps(fmt: dict[str, Any], max_video_height: int = 0, max_video_fps: int = 0) -> bool:
    if max_video_height <= 0:
        height_ok = True
    else:
        height = video_height(fmt)
        height_ok = height is not None and height <= max_video_height
    if max_video_fps <= 0:
        fps_ok = True
    else:
        fps = video_fps(fmt)
        fps_ok = fps is not None and fps <= max_video_fps
    return height_ok and fps_ok


def video_height(fmt: dict[str, Any]) -> int | None:
    value = fmt.get("height")
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def video_fps(fmt: dict[str, Any]) -> float | None:
    value = fmt.get("fps")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _playable_without_video_metadata(fmt: dict[str, Any]) -> bool:
    if not fmt.get("url") and not fmt.get("manifest_url"):
        return False
    if fmt.get("vcodec") == "images":
        return False
    if fmt.get("ext") == "mhtml":
        return False
    if fmt.get("protocol") == "mhtml":
        return False
    return bool(fmt.get("manifest_url")) or has_unknown_codec_direct_url(fmt)
