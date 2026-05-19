from dashbox.core import client_selection


def test_selection_id_round_trips_selected_item_without_episode_index() -> None:
    collection_url = "https://example.test/playlist?id=1"
    selected_url = "https://example.test/watch?v=abc&dashbox_index=2"

    raw_id = client_selection.encode_selection_id(collection_url, selected_url)

    assert raw_id.startswith(client_selection.SELECTION_ID_PREFIX)
    assert client_selection.decode_selection_id(raw_id) == {
        "playlist_url": collection_url,
        "selected_url": "https://example.test/watch?v=abc",
        "selected_key": client_selection.selection_key_from_values("", "https://example.test/watch?v=abc"),
    }


def test_selection_key_prefers_stable_item_id() -> None:
    item_id = "https://example.test/item?id=one&dashbox_index=4"
    selected_url = "https://example.test/watch?v=abc&dashbox_index=2"

    assert client_selection.selection_key_from_values(item_id, selected_url) == (
        "u-" + client_selection.selection_hash("https://example.test/item?id=one")
    )


def test_selection_occurrence_key_suffixes_duplicates() -> None:
    counts: dict[str, int] = {}

    assert client_selection.selection_occurrence_key("u-one", counts) == "u-one"
    assert client_selection.selection_occurrence_key("u-one", counts) == "u-one@2"
    assert client_selection.selection_occurrence_key("u-two", counts) == "u-two"
