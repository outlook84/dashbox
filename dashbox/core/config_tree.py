from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..config import FolderItem, Source, UrlItem
from ..config.ids import validate_config_id
from ..sites import registry


CONFIG_ID_PREFIX = "cfg:"


class ConfigTree:
    def __init__(self, sub_id: str, sources: Sequence[Source] | Any) -> None:
        self.sub_id = sub_id
        self.sources = tuple(getattr(sources, "sources", sources))
        self._item_index = self.build_item_index()

    def source_by_id(self, source_id: str) -> Any | None:
        for source in self.sources:
            if source.id == source_id:
                return source
        return None

    def item_id(self, parent_id: str, item: Any) -> str:
        source_id, parent_key = self.parent_identity(parent_id)
        return f"{CONFIG_ID_PREFIX}{self.sub_id}:{source_id}:{self.item_key(item, parent_key)}" if source_id else ""

    def folder_item_by_id(self, item_id: str) -> FolderItem | None:
        item = self.config_item_by_id(item_id)
        return item if isinstance(item, FolderItem) else None

    def url_item_by_id(self, item_id: str) -> UrlItem | None:
        item = self.config_item_by_id(item_id)
        return item if isinstance(item, UrlItem) else None

    def config_item_by_id(self, item_id: str) -> Any | None:
        sub_id, source_id, key = self.parse_item_id(item_id)
        if sub_id != self.sub_id or not source_id or not key:
            return None
        return self._item_index.get((source_id, key))

    def parent_identity(self, parent_id: str) -> tuple[str, str]:
        sub_id, source_id, _key = self.parse_item_id(parent_id)
        if sub_id and sub_id != self.sub_id:
            return "", ""
        if source_id:
            return source_id, _key
        return (parent_id, "") if self.source_by_id(parent_id) else ("", "")

    @staticmethod
    def parse_item_id(item_id: str) -> tuple[str, str, str]:
        if not item_id.startswith(CONFIG_ID_PREFIX):
            return "", "", ""
        rest = item_id.removeprefix(CONFIG_ID_PREFIX)
        sub_id, separator, rest = rest.partition(":")
        if not separator or not sub_id or not rest:
            return "", "", ""
        source_id, separator, key = rest.partition(":")
        if not separator or not source_id or not key:
            return "", "", ""
        return sub_id, source_id, key

    @classmethod
    def item_key(cls, item: Any, parent_key: str = "") -> str:
        if isinstance(item, UrlItem):
            return cls.url_item_key(item, parent_key)
        if isinstance(item, FolderItem):
            return cls.folder_item_key(item, parent_key)
        return ""

    @classmethod
    def url_item_key(cls, item: UrlItem, parent_key: str = "") -> str:
        item_id = validate_config_id(item.id, "config url item")
        return "i-" + item_id

    @classmethod
    def folder_item_key(cls, item: FolderItem, parent_key: str = "") -> str:
        item_id = validate_config_id(item.id, "config folder item")
        return "i-" + item_id

    @classmethod
    def parent_scope(cls, parent_key: str) -> str:
        return f"p-{cls.short_hash(parent_key)}-" if parent_key else ""

    @staticmethod
    def short_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def canonical_url(url: str) -> str:
        value = registry.normalize_config_url(url)
        if not value.startswith(("http://", "https://")):
            return value
        parts = urlsplit(value)
        query = urlencode([
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key != "dashbox_index"
        ])
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

    @classmethod
    def iter_items(cls, items: tuple[Any, ...], parent_key: str = "") -> Any:
        for item in items:
            key = cls.item_key(item, parent_key)
            yield item, key
            if isinstance(item, FolderItem):
                yield from cls.iter_items(item.items, key)

    def build_item_index(self) -> dict[tuple[str, str], Any]:
        out: dict[tuple[str, str], Any] = {}
        for source in self.sources:
            for item, key in self.iter_items(source.items):
                if key:
                    index_key = (source.id, key)
                    if index_key in out:
                        raise ValueError(f"duplicate config item key in subscription {self.sub_id} source {source.id}: {key}")
                    out[index_key] = item
        return out
