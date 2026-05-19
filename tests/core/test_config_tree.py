
import pytest

from dashbox.config import (
    Config,
    FolderItem,
    Source,
    UrlItem,
)
from dashbox.core.config_tree import ConfigTree
from tests.helpers import config_item_id, make_tvbox_service as MediaService, nested_config_item_id


def test_config_item_ids_use_explicit_ids() -> None:
    first = UrlItem("https://example.test/a", title="Title", id="stable")
    second = UrlItem("https://example.test/a", title="Renamed", id="renamed")
    folder = FolderItem("Folder", id="folder")
    service = MediaService(Config(), sources=(Source("main", "Main", (first, second, folder)),))

    assert service.config_tree.item_id("main", first) == "cfg:main:main:i-stable"
    assert service.config_tree.item_id("main", second) == "cfg:main:main:i-renamed"
    assert service.config_tree.item_id("main", folder) == "cfg:main:main:i-folder"


def test_config_item_key_allows_same_title_with_different_explicit_ids() -> None:
    service = MediaService(Config(), sources=(Source("main", "Main", (
        UrlItem("https://example.test/a", title="Same", id="first"),
        UrlItem("https://example.test/b", title="Same", id="second"),
    )),))

    first = config_item_id(service, "main", 0)
    second = config_item_id(service, "main", 1)

    assert first != second
    assert service.config_tree.url_item_by_id(first).url == "https://example.test/a"
    assert service.config_tree.url_item_by_id(second).url == "https://example.test/b"


def test_config_item_key_rejects_duplicate_explicit_ids() -> None:
    with pytest.raises(ValueError, match="duplicate config item key in subscription main source main"):
        MediaService(Config(), sources=(Source("main", "Main", (
            UrlItem("https://example.test/a", id="dup"),
            FolderItem("Folder", id="dup"),
        )),))


def test_config_item_key_rejects_missing_item_ids() -> None:
    with pytest.raises(ValueError, match=r"config folder item\.id is required"):
        ConfigTree("main", (Source("main", "Main", (FolderItem("Folder"),)),))


def test_config_item_key_requires_nested_explicit_ids() -> None:
    service = MediaService(Config(), sources=(Source("main", "Main", (
        FolderItem("A", (UrlItem("https://example.test/same", id="same-a"),), id="folder-a"),
        FolderItem("B", (UrlItem("https://example.test/same", id="same-b"),), id="folder-b"),
    )),))

    first = nested_config_item_id(service, "main", 0, 0)
    second = nested_config_item_id(service, "main", 1, 0)

    assert first != second
    assert service.config_tree.url_item_by_id(first) is service.config_tree.source_by_id("main").items[0].items[0]
