from __future__ import annotations

import base64
import hashlib
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SELECTION_ID_PREFIX = "__dashbox_selection__:"
SELECTION_DIRECTORY_SELECTED_URL = "__dashbox_directory__"


def encode_selection_id(collection_url: str, selected_url: str, selected_key: str = "") -> str:
    selected_clean = without_episode_index(selected_url)
    payload = json.dumps(
        {
            "v": 2,
            "playlist": collection_url,
            "selected": selected_clean,
            "key": selected_key or selection_key_from_values("", selected_clean),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    token = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return SELECTION_ID_PREFIX + token


def decode_selection_id(raw_id: str) -> dict[str, str]:
    if not raw_id.startswith(SELECTION_ID_PREFIX):
        return {}
    token = raw_id.removeprefix(SELECTION_ID_PREFIX)
    padding = "=" * (-len(token) % 4)
    try:
        decoded = base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    collection_url = payload.get("playlist")
    selected_url = payload.get("selected")
    selected_key = payload.get("key")
    if not isinstance(collection_url, str) or not isinstance(selected_url, str):
        return {}
    if not collection_url.startswith(("http://", "https://")) or not selected_url:
        return {}
    out = {"playlist_url": collection_url, "selected_url": selected_url}
    if isinstance(selected_key, str) and selected_key:
        out["selected_key"] = selected_key
    return out


def selection_key_from_values(item_id: str, selected_url: str) -> str:
    clean_id = without_episode_index(item_id.strip())
    if clean_id and not clean_id.startswith(SELECTION_ID_PREFIX):
        return "u-" + selection_hash(clean_id)
    selected_clean = without_episode_index(selected_url.strip())
    return "u-" + selection_hash(selected_clean) if selected_clean else ""


def selection_occurrence_key(base_key: str, key_counts: dict[str, int] | None) -> str:
    if not base_key or key_counts is None:
        return base_key
    key_counts[base_key] = key_counts.get(base_key, 0) + 1
    count = key_counts[base_key]
    return base_key if count == 1 else f"{base_key}@{count}"


def without_episode_index(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return url
    parts = urlsplit(url)
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key != "dashbox_index"
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def selection_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
