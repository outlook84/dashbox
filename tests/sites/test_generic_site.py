from dashbox.models import NodeKind
from dashbox.sites import generic


def test_generic_config_url_classification_defaults_to_probeable_leaf_vod() -> None:
    assert generic.config_node_kind("https://example.test/videos") == NodeKind.LEAF_VOD
    assert generic.config_url_supports_playlist_probe(
        "https://example.test/videos",
        config_kind=NodeKind.LEAF_VOD,
    )


def test_generic_probe_skips_known_leaf_and_non_http_urls() -> None:
    assert not generic.config_url_supports_playlist_probe(
        "https://example.test/watch",
        config_kind=NodeKind.LEAF_VOD,
        known_leaf=True,
    )
    assert not generic.config_url_supports_playlist_probe(
        ":ytfav",
        config_kind=NodeKind.LEAF_VOD,
    )


def test_generic_metadata_classification_respects_known_leaf_override() -> None:
    assert generic.node_kind_from_metadata(
        NodeKind.LEAF_VOD,
        {"playlist_count": 2},
    ) == NodeKind.PLAYLIST_DIRECTORY
    assert generic.node_kind_from_metadata(
        NodeKind.LEAF_VOD,
        {"playlist_count": 2},
        known_leaf=True,
    ) == NodeKind.LEAF_VOD


def test_generic_metadata_classification_uses_non_empty_entries_as_folder() -> None:
    assert generic.node_kind_from_metadata(
        NodeKind.LEAF_VOD,
        {"entries": [{"url": "https://example.test/watch/1"}]},
    ) == NodeKind.PLAYLIST_DIRECTORY
    assert generic.node_kind_from_metadata(
        NodeKind.LEAF_VOD,
        {"entries": []},
    ) == NodeKind.LEAF_VOD


def test_generic_metadata_supplement_fills_missing_display_fields() -> None:
    value = generic.merge_metadata(
        {"webpage_url": "https://example.test/watch", "title": "Probe"},
        {
            "webpage_url": "https://example.test/canonical",
            "title": "HTML",
            "thumbnail": "https://example.test/thumb.jpg",
        },
    )

    assert value["webpage_url"] == "https://example.test/watch"
    assert value["title"] == "Probe"
    assert value["thumbnail"] == "https://example.test/thumb.jpg"


def test_generic_metadata_raw_duration_is_display_value() -> None:
    assert generic.metadata_has_display_value({"duration": 123})
    assert generic.metadata_has_display_value({"duration_string": "02:03"})


def test_generic_fallback_config_node_uses_directory_copy_for_playlist() -> None:
    node = generic.fallback_config_node(
        "item-1",
        "https://example.test/list",
        kind=NodeKind.PLAYLIST_DIRECTORY,
    )

    assert node.kind == "folder"
    assert node.title == "https://example.test/list"
    assert node.remarks == ""
    assert node.remarks_key == "enter"
