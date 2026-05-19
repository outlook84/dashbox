from dashbox.adapters.tvbox_service import TvboxService, tvbox_subtitle_languages
from dashbox.config import TvboxLocale
from dashbox.core.client_model import ClientPlay, ClientSubtitle


def test_tvbox_play_from_client_play_uses_mime_format_for_subtitles() -> None:
    value = TvboxService.tvbox_play_from_client_play(ClientPlay(
        url="https://media.example.test/video.mp4",
        subtitles=(
            ClientSubtitle(
                name="zh-Hans",
                language="zh-Hans",
                url="https://sub.example.test/caption",
                format="vtt",
            ),
        ),
    ))

    assert value["subs"] == [{
        "name": "zh-Hans",
        "lang": "zh-Hans",
        "url": "https://sub.example.test/caption",
        "ext": "vtt",
        "format": "text/vtt",
    }]


def test_tvbox_play_from_client_play_uses_srt_mime_format_for_subtitles() -> None:
    value = TvboxService.tvbox_play_from_client_play(ClientPlay(
        url="https://media.example.test/video.mp4",
        subtitles=(
            ClientSubtitle(
                name="Chinese (Simplified)",
                language="zh-Hans",
                url="https://www.youtube.com/api/timedtext?fmt=srt&tlang=zh-Hans",
                format="srt",
            ),
        ),
    ))

    assert value["subs"] == [{
        "name": "Chinese (Simplified)",
        "lang": "zh-Hans",
        "url": "https://www.youtube.com/api/timedtext?fmt=srt&tlang=zh-Hans",
        "ext": "srt",
        "format": "application/x-subrip",
    }]


def test_tvbox_subtitle_languages_preserve_locale_before_fallbacks() -> None:
    assert tvbox_subtitle_languages(TvboxLocale.ZH_CN) == ("zh-CN", "en")
    assert tvbox_subtitle_languages(TvboxLocale.EN_US) == ("en-US", "zh-CN")
