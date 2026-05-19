from __future__ import annotations

from typing import Any


def has_video_format(fmt: dict[str, Any]) -> bool:
    vcodec = fmt.get("vcodec")
    if vcodec is not None:
        return vcodec not in ("none", "images")
    video_ext = fmt.get("video_ext")
    return video_ext not in (None, "none", "images")


def has_audio_format(fmt: dict[str, Any]) -> bool:
    acodec = fmt.get("acodec")
    if acodec is not None:
        return acodec != "none"
    return fmt.get("audio_ext") not in (None, "none")


def is_audio_only_format(fmt: dict[str, Any]) -> bool:
    return has_audio_format(fmt) and not has_video_format(fmt)


def media_content_type(fmt: dict[str, Any]) -> str:
    if has_video_format(fmt):
        return "video"
    if is_audio_only_format(fmt):
        return "audio"
    return ""


def mime_from_ext(ext: Any, video: bool) -> str:
    if ext == "webm":
        return "video/webm" if video else "audio/webm"
    return "video/mp4" if video else "audio/mp4"
