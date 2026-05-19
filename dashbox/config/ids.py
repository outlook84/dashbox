from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

CONFIG_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
TEMP_ID_PREFIX = "tmp:"


@dataclass(frozen=True)
class ConfigIdChange:
    path: str
    field: str
    value: str


@dataclass(frozen=True)
class ConfigIdNormalizeResult:
    config: dict[str, Any]
    changes: tuple[ConfigIdChange, ...]
    warnings: tuple[str, ...] = ()


def validate_config_id(value: Any, path: str) -> str:
    item_id = str(value or "").strip()
    if not item_id:
        raise ValueError(f"{path}.id is required")
    if not CONFIG_ID_PATTERN.fullmatch(item_id):
        raise ValueError(
            f"{path}.id must be 1 to 64 ASCII letters, digits, '_' or '-', starting with a letter or digit"
        )
    return item_id


def normalize_config_ids(data: dict[str, Any]) -> ConfigIdNormalizeResult:
    next_data = copy.deepcopy(data)
    changes: list[ConfigIdChange] = []
    subs = next_data.get("subs")
    if not isinstance(subs, list):
        return ConfigIdNormalizeResult(config=next_data, changes=tuple(changes))
    for sub_index, sub in enumerate(subs):
        if not isinstance(sub, dict):
            continue
        tvbox = sub.get("tvbox")
        if isinstance(tvbox, dict):
            sources = tvbox.get("sources")
            if isinstance(sources, list):
                normalize_source_ids(sources, f"subs[{sub_index}].tvbox.sources", changes)
        kodi = sub.get("kodi")
        if isinstance(kodi, dict):
            sources = kodi.get("sources")
            if isinstance(sources, list):
                used_item_ids: set[str] = set()
                normalize_item_ids(sources, f"subs[{sub_index}].kodi.sources", used_item_ids, changes)
    return ConfigIdNormalizeResult(config=next_data, changes=tuple(changes))


def normalize_source_ids(sources: list[Any], path: str, changes: list[ConfigIdChange]) -> None:
    used_source_ids: set[str] = set()
    for source_index, source in enumerate(sources):
        source_path = f"{path}[{source_index}]"
        if not isinstance(source, dict):
            continue
        source_id = normalize_object_id(
            source,
            source_path,
            seed=str(source.get("name") or "source"),
            used=used_source_ids,
            fallback="source",
            changes=changes,
        )
        used_source_ids.add(source_id)
        items = source.get("items")
        if isinstance(items, list):
            used_item_ids: set[str] = set()
            normalize_item_ids(items, f"{source_path}.items", used_item_ids, changes)


def normalize_item_ids(items: list[Any], path: str, used: set[str], changes: list[ConfigIdChange]) -> None:
    for item_index, item in enumerate(items):
        item_path = f"{path}[{item_index}]"
        if not isinstance(item, dict):
            continue
        seed = item_seed(item)
        item_id = normalize_object_id(
            item,
            item_path,
            seed=seed,
            used=used,
            fallback="item",
            changes=changes,
        )
        used.add(item_id)
        children = item.get("items")
        if isinstance(children, list):
            normalize_item_ids(children, f"{item_path}.items", used, changes)


def normalize_object_id(
    obj: dict[str, Any],
    path: str,
    *,
    seed: str,
    used: set[str],
    fallback: str,
    changes: list[ConfigIdChange],
) -> str:
    current = str(obj.get("id") or "").strip()
    if current and not current.startswith(TEMP_ID_PREFIX):
        item_id = validate_config_id(current, path)
        if item_id in used:
            raise ValueError(f"duplicate id at {path}: {item_id}")
        obj["id"] = item_id
        return item_id
    item_id = unique_config_id(seed, used, fallback=fallback)
    obj["id"] = item_id
    changes.append(ConfigIdChange(path=path, field="id", value=item_id))
    return item_id


def unique_config_id(seed: str, used: set[str], *, fallback: str) -> str:
    base = slug_config_id(seed) or fallback
    base = base[:64]
    if base not in used:
        return base
    suffix = 2
    while True:
        suffix_text = f"_{suffix}"
        candidate = base[: 64 - len(suffix_text)] + suffix_text
        if candidate not in used:
            return candidate
        suffix += 1


def slug_config_id(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_-")
    if not text or not text[0].isalnum():
        return ""
    return text[:64]


def item_seed(item: dict[str, Any]) -> str:
    for key in ("name", "title"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    url = str(item.get("url") or "").strip()
    if url:
        parts = urlsplit(url)
        seed = " ".join(part for part in (parts.netloc, parts.path.strip("/")) if part)
        return seed or url
    return "item"
