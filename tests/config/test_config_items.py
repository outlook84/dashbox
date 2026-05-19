
import pytest

from dashbox.config import (
    DEFAULT_BILIBILI_LIST_LIMIT,
    DEFAULT_USER_AGENT,
    Config,
    FolderItem,
    ImageProxyMode,
    LogLevel,
    UrlItem,
    load_config,
    parse_sources,
)
from dashbox.core.config_tree import ConfigTree
from dashbox import sites


def test_parse_sources_supports_url_items_and_folders() -> None:
    sources = parse_sources([
        {
            "id": "main",
            "name": "Main",
            "items": [
                {"id": "a", "url": "https://example.test/a"},
                {
                    "id": "folder",
                    "name": "Folder",
                    "items": [
                        {"id": "manual", "url": "https://example.test/b", "title": "Manual title"},
                    ],
                },
            ],
        },
    ])

    assert sources[0].items[0] == UrlItem("https://example.test/a", id="a")
    folder = sources[0].items[1]
    assert isinstance(folder, FolderItem)
    assert folder.name == "Folder"
    assert folder.id == "folder"
    assert folder.items[0] == UrlItem("https://example.test/b", title="Manual title", id="manual")


def test_playlist_limit_zero_uses_default_limit() -> None:
    assert Config().effective_playlist_limit == 100
    assert Config(playlist_limit=0).effective_playlist_limit == 100
    assert Config(playlist_limit=5).effective_playlist_limit == 5


def test_bilibili_list_limit_zero_uses_default_limit() -> None:
    assert Config().effective_bilibili_list_limit == DEFAULT_BILIBILI_LIST_LIMIT
    assert Config(bilibili_list_limit=0).effective_bilibili_list_limit == DEFAULT_BILIBILI_LIST_LIMIT
    assert Config(bilibili_list_limit=5).effective_bilibili_list_limit == 5


def test_empty_user_agent_uses_unified_default() -> None:
    assert Config().effective_user_agent == DEFAULT_USER_AGENT
    assert Config(user_agent="Custom UA").effective_user_agent == "Custom UA"


def test_sites_normalize_config_url_handles_youtube_playlist_id() -> None:
    playlist_id = "PL1111111111111111111111111111111111"

    assert sites.normalize_config_url(playlist_id) == f"https://www.youtube.com/playlist?list={playlist_id}"


def test_parse_sources_allows_scheme_less_site_shortcuts() -> None:
    playlist_id = "PL1111111111111111111111111111111111"

    sources = parse_sources([
        {
            "id": "main",
            "name": "Main",
            "items": [{"id": "playlist", "url": playlist_id}],
        },
    ])

    assert sources[0].items[0] == UrlItem(playlist_id, id="playlist")


@pytest.mark.parametrize("url", ("ytsearch5:cats", "bilisearch10:foo", "scsearch4:music"))
def test_parse_sources_allows_ytdlp_search_url_items(url: str) -> None:
    sources = parse_sources([
        {
            "id": "main",
            "name": "Main",
            "items": [{"id": "search", "url": url}],
        },
    ])

    assert sources[0].items[0] == UrlItem(url, id="search")


def test_config_tree_canonical_url_uses_site_normalizer() -> None:
    playlist_id = "PL1111111111111111111111111111111111"

    assert ConfigTree.canonical_url(playlist_id) == f"https://www.youtube.com/playlist?list={playlist_id}"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("ytdlp_search_limit", -1),
        ("bilibili_search_limit", -1),
        ("playlist_limit", -1),
        ("bilibili_list_limit", -1),
        ("upstream_timeout", 0),
        ("ytdlp_concurrency", 0),
        ("playlist_limit", True),
        ("playlist_limit", 1001),
        ("ytdlp_search_limit", 201),
        ("bilibili_search_limit", 201),
        ("bilibili_list_limit", 1001),
        ("upstream_timeout", 301),
        ("ytdlp_concurrency", 33),
        ("playlist_limit", 1.5),
        ("playlist_limit", "5"),
    ),
)
def test_config_rejects_invalid_numeric_values(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        Config(**{field: value})


def test_load_config_reads_log_level(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"log_level": "DEBUG"}', encoding="utf-8")

    assert load_config(str(path)).log_level is LogLevel.DEBUG


def test_load_config_reads_proxy_media_idle_ttl_seconds(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"proxy_media_idle_ttl_seconds": 120}', encoding="utf-8")

    assert load_config(str(path)).proxy_media_idle_ttl_seconds == 120


def test_load_config_reads_image_proxy_mode_from_unsafe_env(tmp_path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DASHBOX_UNSAFE_IMAGE_PROXY_MODE", "all")

    assert load_config(str(path)).image_proxy_mode is ImageProxyMode.ALL


def test_load_config_reads_upstream_timeout_from_env(tmp_path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DASHBOX_UPSTREAM_TIMEOUT", "12")

    config = load_config(str(path))

    assert config.upstream_timeout == 12


@pytest.mark.parametrize(
    ("env_name", "value"),
    (
        ("DASHBOX_UPSTREAM_TIMEOUT", "0"),
        ("DASHBOX_UPSTREAM_TIMEOUT", "301"),
        ("DASHBOX_UPSTREAM_TIMEOUT", "abc"),
    ),
)
def test_load_config_rejects_invalid_runtime_env(tmp_path, monkeypatch, env_name: str, value: str) -> None:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(env_name, value)

    with pytest.raises(ValueError, match=env_name):
        load_config(str(path))


def test_load_config_rejects_invalid_unsafe_image_proxy_mode_env(tmp_path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DASHBOX_UNSAFE_IMAGE_PROXY_MODE", "some")

    with pytest.raises(ValueError, match="DASHBOX_UNSAFE_IMAGE_PROXY_MODE"):
        load_config(str(path))


def test_config_rejects_unsupported_log_level() -> None:
    with pytest.raises(ValueError, match="unsupported log_level"):
        Config(log_level="verbose")


def test_parse_sources_rejects_ambiguous_item() -> None:
    with pytest.raises(ValueError, match="cannot have both url and items"):
        parse_sources([
            {
                "id": "main",
                "name": "Main",
                "items": [
                    {"url": "https://example.test/a", "items": []},
                ],
            },
        ])


@pytest.mark.parametrize("url", ("javascript:alert(1)", "data:text/html,<script></script>", "file:///etc/passwd"))
def test_parse_sources_rejects_unsafe_url_schemes(url: str) -> None:
    with pytest.raises(ValueError, match="url scheme must be http or https"):
        parse_sources([
            {
                "id": "main",
                "name": "Main",
                "items": [{"id": "bad", "url": url}],
            },
        ])


@pytest.mark.parametrize("url", ("//example.com/video", "https:example.com/video"))
def test_parse_sources_rejects_malformed_absolute_urls(url: str) -> None:
    with pytest.raises(ValueError, match="url must include"):
        parse_sources([
            {
                "id": "main",
                "name": "Main",
                "items": [{"id": "bad", "url": url}],
            },
        ])


def test_parse_sources_rejects_missing_source_id() -> None:
    with pytest.raises(ValueError, match=r"sources\[0\]\.id is required"):
        parse_sources([{"name": "Main", "items": []}])


def test_parse_sources_rejects_duplicate_source_id() -> None:
    with pytest.raises(ValueError, match="duplicate source id: main"):
        parse_sources([
            {"id": "main", "name": "Main", "items": []},
            {"id": "main", "name": "Other", "items": []},
        ])


def test_parse_sources_rejects_invalid_source_id() -> None:
    with pytest.raises(ValueError, match=r"sources\[0\]\.id must be"):
        parse_sources([{"id": "bad:id", "name": "Main", "items": []}])


def test_parse_sources_rejects_missing_item_id() -> None:
    with pytest.raises(ValueError, match=r"sources\[0\]\.items\[0\]\.id is required"):
        parse_sources([
            {"id": "main", "name": "Main", "items": [{"url": "https://example.test/a"}]},
        ])


def test_parse_sources_rejects_duplicate_nested_item_id() -> None:
    with pytest.raises(ValueError, match="duplicate item id in source main: dup"):
        parse_sources([
            {
                "id": "main",
                "name": "Main",
                "items": [
                    {"id": "folder", "name": "Folder", "items": [{"id": "dup", "url": "https://example.test/a"}]},
                    {"id": "dup", "url": "https://example.test/b"},
                ],
            },
        ])


def test_parse_sources_rejects_name_on_url_item() -> None:
    with pytest.raises(ValueError, match="url item cannot have name; use title"):
        parse_sources([
            {
                "id": "main",
                "name": "Main",
                "items": [
                    {"name": "Old title", "url": "https://example.test/a"},
                ],
            },
        ])
