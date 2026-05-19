from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlaybackScope:
    protocol: str
    sub_id: str
    policy_hash: str = ""
    video_codec_order: tuple[str, ...] = ()
    audio_codec_order: tuple[str, ...] = ()
    max_video_height: int = 0
    max_video_fps: int = 0
    proxy_dash_media_url: bool = False
    subtitle_languages: tuple[str, ...] = ()
    youtube_subtitles: bool = False
    all_manual_subtitles: bool = False
