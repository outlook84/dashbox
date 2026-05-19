from __future__ import annotations

import base64
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import Any

from fastapi.testclient import TestClient

from dashbox.adapters.tvbox_service import TvboxService
from dashbox.config import Config, FolderItem, Source, Subscription, TvboxSubscriptionConfig, UrlItem
from dashbox.sites.types import MetadataStrategy


def data_mpd_xml(url: str) -> str:
    assert url.startswith("data:application/dash+xml;base64,")
    return base64.b64decode(url.split(",", 1)[1]).decode("utf-8")


def segment_base_probe_bytes() -> bytes:
    return (
        (12).to_bytes(4, "big") + b"ftyp" + b"isom"
        + (8).to_bytes(4, "big") + b"moov"
        + (10).to_bytes(4, "big") + b"sidx" + b"xx"
    )


async def _metadata_handler_value(handler: Any, raw_id: str, plan: Any, force_refresh: bool) -> dict[str, Any]:
    try:
        value = handler(raw_id, plan, force_refresh=force_refresh)
    except TypeError:
        try:
            value = handler(raw_id, force_refresh=force_refresh)
        except TypeError:
            value = handler(raw_id)
    if hasattr(value, "__await__"):
        return await value
    return value


def patch_metadata_for_plan(
    monkeypatch: Any,
    service: TvboxService,
    *,
    single: Any = None,
    playlist: Any = None,
    display: Any = None,
    fallback: bool = True,
) -> None:
    original_metadata_for_plan = service.metadata.metadata_for_plan

    async def fake_metadata_for_plan(raw_id: str, plan: Any, *, force_refresh: bool = False) -> dict[str, Any]:
        if plan.strategy == MetadataStrategy.SINGLE_YTDLP and single is not None:
            return await _metadata_handler_value(single, raw_id, plan, force_refresh)
        if plan.strategy == MetadataStrategy.PLAYLIST_YTDLP and playlist is not None:
            return await _metadata_handler_value(playlist, raw_id, plan, force_refresh)
        if plan.strategy == MetadataStrategy.DISPLAY:
            if display is not None:
                return await _metadata_handler_value(display, raw_id, plan, force_refresh)
            if single is not None:
                return await _metadata_handler_value(single, raw_id, plan, force_refresh)
        if fallback:
            return await original_metadata_for_plan(raw_id, plan, force_refresh=force_refresh)
        return {}

    monkeypatch.setattr(service.metadata, "metadata_for_plan", fake_metadata_for_plan)


def disable_playable_prewarm(monkeypatch: Any, service: Any) -> None:
    monkeypatch.setattr(service, "start_single_video_playable_prewarm", lambda clean_id, extract_url="": None)


def config_item_id(service: TvboxService, source_id: str, index: int) -> str:
    return service.config_tree.item_id(source_id, service.config_tree.source_by_id(source_id).items[index])


def nested_config_item_id(service: TvboxService, source_id: str, folder_index: int, item_index: int) -> str:
    folder = service.config_tree.source_by_id(source_id).items[folder_index]
    return service.config_tree.item_id(service.config_tree.item_id(source_id, folder), folder.items[item_index])


@contextmanager
def no_lifespan_test_client(app: Any) -> Iterator[TestClient]:
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()


def fragmented_formats(video_url: str, audio_url: str, *, extra_video_segment: bool = False):
    video_fragments = [
        {"url": video_url + "/init"},
        {"url": video_url + "/1", "duration": 4},
    ]
    if extra_video_segment:
        video_fragments.append({"url": video_url + "/2", "duration": 4})
    return [
        {
            "format_id": "v1",
            "vcodec": "avc1.640028",
            "acodec": "none",
            "mime_type": "video/mp4",
            "tbr": 1000,
            "width": 1920,
            "height": 1080,
            "fragments": video_fragments,
        },
        {
            "format_id": "a1",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "mime_type": "audio/mp4",
            "abr": 128,
            "fragments": [
                {"url": audio_url + "/init"},
                {"url": audio_url + "/1", "duration": 4},
            ],
        },
    ]


def make_tvbox_service(
    config: Config | None = None,
    *,
    sources: tuple[Source, ...] = (),
    sub_id: str = "main",
    sub_name: str = "Main",
    vod_style: str = "list",
    tvbox_overrides: dict[str, Any] | None = None,
    **kwargs: Any,
) -> TvboxService:
    config = config or Config()
    sources = with_test_item_ids(sources)
    subscription = Subscription(
        id=sub_id,
        type="tvbox",
        tvbox=TvboxSubscriptionConfig(
            site_key="dashbox",
            site_name=sub_name,
            sources=sources,
            vod_style=vod_style,
            **(tvbox_overrides or {}),
        ),
    )
    return TvboxService(config, subscription, **kwargs)


def with_test_item_ids(sources: tuple[Source, ...]) -> tuple[Source, ...]:
    return tuple(
        Source(source.id, source.name, with_test_ids_for_items(source.items, source.id))
        for source in sources
    )


def with_test_ids_for_items(items: tuple[Any, ...], prefix: str) -> tuple[Any, ...]:
    out: list[Any] = []
    for index, item in enumerate(items, start=1):
        item_id = getattr(item, "id", "") or f"{prefix}_{index}"
        if isinstance(item, UrlItem):
            out.append(replace(item, id=item_id))
        elif isinstance(item, FolderItem):
            children = with_test_ids_for_items(item.items, item_id)
            out.append(replace(item, id=item_id, items=children))
        else:
            out.append(item)
    return tuple(out)
