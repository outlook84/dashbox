from dashbox.adapters import tvbox
from dashbox.adapters import tvbox_text
from dashbox.core.client_model import ClientItem, item_from_media_node
from dashbox.core.client_service import ClientService
from dashbox.core import media_mapper
from dashbox.sites import bilibili
from dashbox.utils import text


def test_node_from_info_displays_numeric_duration() -> None:
    node = media_mapper.node_from_info({
        "webpage_url": "https://example.test/watch/1",
        "duration": 123,
    })

    assert node.title == "https://example.test/watch/1"
    assert node.remarks == "2:03"


def test_node_from_info_prefers_duration_string_over_numeric_duration() -> None:
    node = media_mapper.node_from_info({
        "webpage_url": "https://example.test/watch/1",
        "duration": 123,
        "duration_string": "2 min",
    })

    assert node.remarks == "2 min"


def test_core_clean_title_only_trims_display_whitespace() -> None:
    assert text.display_title(" A#B$C ") == "A#B$C"
    assert media_mapper.clean_title(" A#B$C ") == "A#B$C"


def test_tvbox_clean_title_preserves_separator_glyphs_as_full_width_for_display() -> None:
    assert tvbox_text.safe_title(" A#B$C ") == "A＃B＄C"
    assert tvbox.clean_title(" A#B$C ") == "A＃B＄C"


def test_bilibili_clean_title_only_trims_display_whitespace() -> None:
    assert bilibili.clean_title(" 第1#话$试看 ") == "第1#话$试看"


def test_tvbox_play_value_escapes_protocol_separators_and_restores_them() -> None:
    value = "https://example.test/watch#frag$part?x=%23"

    escaped = tvbox_text.safe_play_value(value)

    assert escaped == "https://example.test/watch%23frag%24part?x=%2523"
    assert tvbox_text.restore_play_value(escaped) == value


def test_tvbox_playlist_episode_escapes_play_value_separators() -> None:
    episode = tvbox.playlist_episode({
        "title": "Clip",
        "webpage_url": "https://example.test/watch#frag$part",
    }, 1)

    assert episode == "Clip$https://example.test/watch?dashbox_index=1%23frag%24part"


def test_aggregate_playlist_node_leaves_tvbox_play_url_formatting_to_adapter() -> None:
    node = media_mapper.aggregate_playlist_node_from_info({
        "title": "Playlist",
        "entries": [
            {
                "title": "Clip",
                "webpage_url": "https://example.test/watch#frag$part",
            },
        ],
    }, "https://example.test/playlist")

    assert node.play_url == ""
    assert [(episode.title, episode.url) for episode in node.episodes] == [
        ("Clip", "https://example.test/watch?dashbox_index=1#frag$part")
    ]
    vod = tvbox.vod_from_client_item(item_from_media_node(node))
    assert vod["vod_play_url"] == "Clip$https://example.test/watch?dashbox_index=1%23frag%24part"
    assert node.extras == {}


def test_aggregate_playlist_node_preserves_deferred_item_count_subtitle() -> None:
    node = media_mapper.aggregate_playlist_node_from_info({
        "title": "Playlist",
        "entries": [
            {
                "title": "Clip",
                "webpage_url": "https://example.test/watch",
            },
        ],
    }, "https://example.test/playlist")

    item = item_from_media_node(node)

    assert item.subtitle_key == "item_count"
    assert item.item_count == 1


def test_search_playlist_node_preserves_deferred_item_count_subtitle() -> None:
    node = media_mapper.search_node_from_entry({
        "_type": "playlist",
        "title": "Playlist",
        "webpage_url": "https://www.youtube.com/playlist?list=PL1111111111111111111111111111111111",
        "playlist_count": 12,
    })

    assert node is not None
    item = item_from_media_node(node)

    assert item.subtitle_key == "item_count"
    assert item.item_count == 12


def test_bilibili_aggregate_playlist_episode_uses_part_urls() -> None:
    node = media_mapper.aggregate_playlist_node_from_info({
        "_type": "playlist",
        "title": "Bili Video",
        "webpage_url": "https://www.bilibili.com/video/BV1wx411w7pe",
        "entries": [
            {"title": "P01 开场"},
            {"title": "过长标题会退回分 P 标记" * 4},
        ],
    }, "https://www.bilibili.com/video/BV1wx411w7pe")

    vod = tvbox.vod_from_client_item(item_from_media_node(node))

    assert vod["vod_id"] == "https://www.bilibili.com/video/BV1wx411w7pe"
    assert vod["vod_play_url"] == (
        "P01 开场$https://www.bilibili.com/video/BV1wx411w7pe?p=1&dashbox_index=1#"
        "P02$https://www.bilibili.com/video/BV1wx411w7pe?p=2&dashbox_index=2"
    )


def test_selection_ids_preserve_duplicate_playlist_occurrences() -> None:
    items = ClientService.with_selection_ids([
        ClientItem(
            id="https://example.test/watch?v=1",
            title="First",
            selected_url="https://example.test/watch?v=1&dashbox_index=1",
        ),
        ClientItem(
            id="https://example.test/watch?v=1",
            title="Second",
            selected_url="https://example.test/watch?v=1&dashbox_index=2",
        ),
    ], "https://example.test/playlist")

    assert items[0].selected_key
    assert items[1].selected_key == f"{items[0].selected_key}@2"
    assert items[0].id != items[1].id
