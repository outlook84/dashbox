from dashbox.adapters import kodi
from dashbox import i18n
from dashbox.config import Config
from dashbox.core.client_model import ClientArt, ClientItem, ClientPage, ClientPlay


def test_kodi_page_response_uses_client_shape() -> None:
    page = ClientPage(
        id="root",
        title="Root",
        items=(
            ClientItem(
                id="item-1",
                title="Video",
                is_playable=True,
                play_url="https://example.test/watch",
                art=ClientArt(thumb="https://example.test/thumb.jpg"),
            ),
        ),
        total_items=1,
    )

    value = kodi.page_to_dict(page, Config(image_proxy_mode="off"))

    assert value["version"] == 2
    assert value["id"] == "root"
    assert value["items"][0]["id"] == "item-1"
    assert value["items"][0]["is_playable"] is True
    assert value["items"][0]["art"]["thumb"] == "https://example.test/thumb.jpg"
    assert value["items"][0]["art"]["icon"] == "https://example.test/thumb.jpg"
    assert value["icons"]["refresh"] == "/assets/icons/refresh.png"
    assert value["labels"]["play_directory"] == "播放此列表"
    assert "vod_id" not in value["items"][0]


def test_kodi_page_response_adds_fallback_icons() -> None:
    page = ClientPage(
        items=(
            ClientItem(
                id="folder",
                title="Folder",
                kind="folder",
                is_folder=True,
            ),
        ),
    )

    value = kodi.page_to_dict(page, Config(image_proxy_mode="off"), "http://testserver")

    assert value["items"][0]["art"]["thumb"] == "http://testserver/assets/icons/folder.png"
    assert value["items"][0]["art"]["icon"] == "http://testserver/assets/icons/folder.png"
    assert value["icons"]["refresh"] == "http://testserver/assets/icons/refresh.png"


def test_kodi_page_response_labels_use_current_locale() -> None:
    with i18n.use_locale("en-US"):
        value = kodi.page_to_dict(ClientPage(), Config(image_proxy_mode="off"))

    assert value["labels"]["play_directory"] == "Play all"
    assert value["labels"]["refresh_directory"] == "Refresh list"


def test_kodi_play_response_uses_headers_field() -> None:
    value = kodi.play_to_dict(ClientPlay(url="https://cdn.example.test/video.mp4", headers={"User-Agent": "UA"}))

    assert value["version"] == 2
    assert value["url"] == "https://cdn.example.test/video.mp4"
    assert value["headers"] == {"User-Agent": "UA"}
    assert "header" not in value
