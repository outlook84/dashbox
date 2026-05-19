from dashbox.core.client_model import item_from_media_node, page_from_media_nodes
from dashbox.models import MediaEpisode, MediaNode
from dashbox.models import NodeKind


def test_item_from_media_node_maps_display_metadata_without_protocol_fields() -> None:
    item = item_from_media_node(
        MediaNode(
            "https://example.test/watch",
            "Example",
            thumbnail="https://example.test/thumb.jpg",
            remarks="2:03",
            content="Description",
            node_kind=NodeKind.LEAF_VOD.value,
            extras={"source": "fixture"},
        )
    )

    assert item.id == "https://example.test/watch"
    assert item.title == "Example"
    assert item.subtitle == "2:03"
    assert item.summary == "Description"
    assert item.art.thumb == "https://example.test/thumb.jpg"
    assert item.info.title == "Example"
    assert item.info.plot == "Description"
    assert item.node_kind == NodeKind.LEAF_VOD.value
    assert item.extras == {"source": "fixture"}
    assert not hasattr(item, "vod_id")


def test_item_from_media_node_maps_structured_episodes() -> None:
    item = item_from_media_node(
        MediaNode(
            "playlist",
            "Playlist",
            episodes=(MediaEpisode("One", "https://example.test/one"),),
        )
    )

    assert [(episode.title, episode.url) for episode in item.episodes] == [
        ("One", "https://example.test/one")
    ]


def test_item_from_media_node_marks_folder_and_play_actions() -> None:
    folder = item_from_media_node(MediaNode("folder-id", "Folder", kind="folder"))

    assert folder.is_folder is True
    assert [action.kind for action in folder.actions] == ["open"]


def test_page_from_media_nodes_can_force_directory_ids() -> None:
    page = page_from_media_nodes(
        (MediaNode("one", "One"), MediaNode("two", "Two")),
        page_id="page",
        title="Page",
        directory_node_ids=("two",),
    )

    assert page.id == "page"
    assert page.title == "Page"
    assert page.total_items == 2
    assert page.items[0].is_folder is False
    assert page.items[1].is_folder is True
