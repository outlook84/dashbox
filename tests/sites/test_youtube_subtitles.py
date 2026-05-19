from dashbox.sites import youtube_subtitles


def test_youtube_subtitles_prefers_manual_srt_by_language() -> None:
    info = {
        "subtitles": {
            "en": [{"ext": "srt", "url": "https://sub.example.test/en.srt"}],
            "zh-Hans": [
                {"ext": "vtt", "url": "https://sub.example.test/zh.vtt"},
                {"ext": "srt", "url": "https://sub.example.test/zh.srt"},
            ],
        },
        "automatic_captions": {
            "zh-Hans": [{"ext": "srt", "url": "https://sub.example.test/auto.zh.srt"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN",),
        subtitles_enabled=True,
    )

    assert subtitles == ({
        "name": "zh-Hans",
        "language": "zh-Hans",
        "url": "https://sub.example.test/zh.srt",
        "format": "srt",
    },)


def test_youtube_subtitles_falls_back_to_automatic_original_when_no_manual_exists() -> None:
    info = {
        "subtitles": {},
        "automatic_captions": {
            "zh-Hans": [{"ext": "srt", "url": "https://sub.example.test/auto.zh.srt?tlang=zh-Hans"}],
            "en-orig": [{"ext": "srt", "url": "https://sub.example.test/orig.en.srt"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN",),
        subtitles_enabled=True,
    )

    assert subtitles == ({
        "name": "en-orig",
        "language": "en-orig",
        "url": "https://sub.example.test/orig.en.srt",
        "format": "srt",
    },)


def test_youtube_subtitles_falls_back_to_original_automatic_caption_in_any_language() -> None:
    info = {
        "subtitles": {},
        "automatic_captions": {
            "ja": [{"ext": "srt", "url": "https://sub.example.test/orig.ja.srt"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN",),
        subtitles_enabled=True,
    )

    assert subtitles == ({
        "name": "ja",
        "language": "ja",
        "url": "https://sub.example.test/orig.ja.srt",
        "format": "srt",
    },)


def test_youtube_subtitles_zh_cn_request_matches_manual_zh_tw_srt() -> None:
    info = {
        "subtitles": {
            "zh-TW": [
                {"ext": "vtt", "url": "https://sub.example.test/zh-tw.vtt"},
                {"ext": "srt", "url": "https://sub.example.test/zh-tw.srt"},
            ],
        },
        "automatic_captions": {
            "zh-Hans": [{"ext": "srt", "url": "https://sub.example.test/auto.zh-hans.srt?tlang=zh-Hans"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN",),
        subtitles_enabled=True,
    )

    assert subtitles == ({
        "name": "zh-TW",
        "language": "zh-TW",
        "url": "https://sub.example.test/zh-tw.srt",
        "format": "srt",
    },)


def test_youtube_subtitles_prefers_exact_traditional_chinese_region() -> None:
    info = {
        "subtitles": {
            "zh-TW": [
                {"ext": "srt", "url": "https://sub.example.test/zh-tw.srt"},
            ],
            "zh-HK": [
                {"ext": "srt", "url": "https://sub.example.test/zh-hk.srt"},
            ],
        },
        "automatic_captions": {},
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-HK",),
        subtitles_enabled=True,
    )

    assert subtitles == ({
        "name": "zh-HK",
        "language": "zh-HK",
        "url": "https://sub.example.test/zh-hk.srt",
        "format": "srt",
    },)


def test_youtube_subtitles_returns_no_subtitles_when_disabled_and_no_manual_exists() -> None:
    info = {
        "subtitles": {},
        "automatic_captions": {
            "zh-Hans": [{"ext": "srt", "url": "https://sub.example.test/auto.zh.srt"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN",),
        subtitles_enabled=False,
    )

    assert subtitles == ()


def test_youtube_subtitles_returns_no_subtitles_when_disabled_and_manual_exists() -> None:
    info = {
        "subtitles": {
            "zh-Hans": [{"ext": "srt", "url": "https://sub.example.test/zh.srt"}],
        },
        "automatic_captions": {
            "zh-Hans": [{"ext": "srt", "url": "https://sub.example.test/auto.zh.srt"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN",),
        subtitles_enabled=False,
    )

    assert subtitles == ()


def test_youtube_subtitles_kodi_keeps_manual_only_even_when_automatic_enabled() -> None:
    info = {
        "subtitles": {
            "en": [{"ext": "srt", "url": "https://sub.example.test/en.srt"}],
            "fr": [{"ext": "srt", "url": "https://sub.example.test/fr.srt"}],
        },
        "automatic_captions": {
            "zh-Hans": [{"ext": "srt", "url": "https://sub.example.test/auto.zh.srt"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN",),
        subtitles_enabled=True,
        all_manual=True,
    )

    assert [item["url"] for item in subtitles] == [
        "https://sub.example.test/en.srt",
        "https://sub.example.test/fr.srt",
    ]


def test_youtube_subtitles_kodi_returns_no_subtitles_when_disabled_and_no_manual_exists() -> None:
    info = {
        "subtitles": {},
        "automatic_captions": {
            "zh-Hans": [{"ext": "srt", "url": "https://sub.example.test/auto.zh.srt"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN",),
        subtitles_enabled=False,
        all_manual=True,
    )

    assert subtitles == ()


def test_youtube_subtitles_ignores_automatic_translation_entries() -> None:
    info = {
        "subtitles": {},
        "automatic_captions": {
            "zh-Hans": [{"ext": "srt", "url": "https://sub.example.test/auto.zh.srt?tlang=zh-Hans"}],
        },
    }

    assert youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN",),
        subtitles_enabled=True,
    ) == ()


def test_youtube_subtitles_kodi_sorts_manual_subtitles_by_language_preference() -> None:
    info = {
        "subtitles": {
            "en": [{"ext": "srt", "url": "https://sub.example.test/en.srt"}],
            "zh-Hans": [{"ext": "srt", "url": "https://sub.example.test/zh.srt"}],
            "fr": [{"ext": "srt", "url": "https://sub.example.test/fr.srt"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN",),
        subtitles_enabled=True,
        all_manual=True,
    )

    assert [item["url"] for item in subtitles] == [
        "https://sub.example.test/zh.srt",
        "https://sub.example.test/en.srt",
        "https://sub.example.test/fr.srt",
    ]


def test_youtube_subtitles_prefers_exact_english_locale_before_generic_fallback() -> None:
    info = {
        "subtitles": {
            "en-US": [{"ext": "srt", "url": "https://sub.example.test/en-us.srt"}],
            "en": [{"ext": "srt", "url": "https://sub.example.test/en.srt"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("en-US",),
        subtitles_enabled=True,
    )

    assert subtitles == ({
        "name": "en-US",
        "language": "en-US",
        "url": "https://sub.example.test/en-us.srt",
        "format": "srt",
    },)


def test_youtube_subtitles_prefers_manual_english_before_original_automatic_fallback() -> None:
    info = {
        "subtitles": {
            "en": [{"ext": "srt", "url": "https://sub.example.test/en.srt"}],
        },
        "automatic_captions": {
            "en-orig": [{"ext": "srt", "url": "https://sub.example.test/en-orig.srt"}],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("zh-CN", "en"),
        subtitles_enabled=True,
    )

    assert subtitles == ({
        "name": "en",
        "language": "en",
        "url": "https://sub.example.test/en.srt",
        "format": "srt",
    },)


def test_youtube_subtitles_prefers_vtt_when_srt_is_unavailable() -> None:
    info = {
        "subtitles": {
            "en": [
                {"ext": "json3", "url": "https://sub.example.test/en.json3"},
                {"ext": "srv1", "url": "https://sub.example.test/en.srv1"},
                {"ext": "vtt", "url": "https://sub.example.test/en.vtt"},
            ],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("en",),
        subtitles_enabled=True,
    )

    assert subtitles == ({
        "name": "en",
        "language": "en",
        "url": "https://sub.example.test/en.vtt",
        "format": "vtt",
    },)


def test_youtube_subtitles_prefers_srt_when_url_fmt_disagrees_with_ext_order() -> None:
    info = {
        "subtitles": {
            "en": [
                {"ext": "vtt", "url": "https://sub.example.test/api/timedtext?fmt=vtt"},
                {"ext": "vtt", "url": "https://sub.example.test/api/timedtext?fmt=srt"},
            ],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("en",),
        subtitles_enabled=True,
    )

    assert subtitles == ({
        "name": "en",
        "language": "en",
        "url": "https://sub.example.test/api/timedtext?fmt=srt",
        "format": "srt",
    },)


def test_youtube_subtitles_prefers_srt_mime_before_vtt() -> None:
    info = {
        "subtitles": {
            "en": [
                {"format": "text/vtt", "url": "https://sub.example.test/en"},
                {"format": "application/x-subrip", "url": "https://sub.example.test/en-srt"},
            ],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("en",),
        subtitles_enabled=True,
    )

    assert subtitles == ({
        "name": "en",
        "language": "en",
        "url": "https://sub.example.test/en-srt",
        "format": "srt",
    },)


def test_youtube_subtitles_returns_none_when_only_unsupported_formats_exist() -> None:
    info = {
        "subtitles": {
            "en": [
                {"ext": "json3", "url": "https://sub.example.test/en.json3"},
                {"ext": "srv1", "url": "https://sub.example.test/en.srv1"},
            ],
        },
    }

    subtitles = youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=("en",),
        subtitles_enabled=True,
    )

    assert subtitles == ()
