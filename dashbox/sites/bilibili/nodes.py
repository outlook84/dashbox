from __future__ import annotations

from typing import Any

from ... import i18n
from ...core.duration import duration_text, existing_duration_text
from ...models import MediaEpisode, MediaNode
from ...models import NodeKind
from ..hosts import with_query_param
from .utils import (
    clean_content,
    clean_html_text,
    clean_title,
    collection_count_fields,
    dict_list,
    normalize_image_url,
    positive_int,
)

def bangumi_episode_id_from_url(url: str) -> str:
    from . import bangumi_episode_id_from_url as impl
    return impl(url)


def cheese_episode_id_from_url(url: str) -> str:
    from . import cheese_episode_id_from_url as impl
    return impl(url)

def node_from_pages(info: dict[str, Any], fallback_url: str) -> MediaNode:
    pages = dict_list(info.get("pages"))
    return MediaNode(
        id=fallback_url,
        title=str(info.get("title") or fallback_url),
        kind="playlist",
        thumbnail=str(info.get("pic") or ""),
        remarks_key="part_count" if pages else "playlist",
        part_count=len(pages),
        content=clean_content(str(info.get("desc") or "")),
        node_kind=NodeKind.AGGREGATE_VOD.value,
    )


def playable_playlist_node_from_pages(info: dict[str, Any], fallback_url: str) -> MediaNode:
    pages = dict_list(info.get("pages"))
    episodes = tuple(
        episode
        for episode in (page_episode(page, index, fallback_url) for index, page in enumerate(pages, 1))
        if episode
    )
    return MediaNode(
        id=fallback_url,
        title=str(info.get("title") or fallback_url),
        kind="playlist",
        thumbnail=str(info.get("pic") or ""),
        remarks_key="part_count" if pages else "playlist",
        part_count=len(pages),
        content=clean_content(str(info.get("desc") or "")),
        play_from="yt-dlp",
        episodes=episodes,
        node_kind=NodeKind.AGGREGATE_VOD.value,
    )


def single_node_from_video_metadata(url: str, info: dict[str, Any]) -> MediaNode:
    title = clean_title(str(info.get("title") or url))
    return MediaNode(
        id=url,
        title=title,
        thumbnail=str(info.get("pic") or ""),
        remarks=duration_text(info.get("duration")),
        content=clean_content(str(info.get("desc") or "")),
        play_from="yt-dlp",
        play_url=url,
        node_kind=NodeKind.LEAF_VOD.value,
    )


def single_node_from_bangumi_metadata(url: str, info: dict[str, Any]) -> MediaNode | None:
    if not info:
        return None
    episode_id = bangumi_episode_id_from_url(url)
    episodes = dict_list(info.get("episodes"))
    episode = next(
        (
            item
            for item in episodes
            if str(item.get("id") or item.get("ep_id") or "") == episode_id
        ),
        episodes[0] if len(episodes) == 1 else {},
    )
    title = bangumi_episode_title(episode, 1) if episode else clean_title(str(info.get("title") or url))
    return MediaNode(
        id=url,
        title=title,
        thumbnail=str(episode.get("cover") or info.get("cover") or ""),
        remarks=duration_text(bangumi_duration_seconds(episode.get("duration"))),
        content=clean_content(str(info.get("evaluate") or "")),
        play_from="yt-dlp",
        play_url=url,
        node_kind=NodeKind.LEAF_VOD.value,
    )


def single_node_from_cheese_metadata(url: str, info: dict[str, Any]) -> MediaNode | None:
    if not info:
        return None
    episode_id = cheese_episode_id_from_url(url)
    episodes = dict_list(info.get("episodes"))
    episode = next(
        (
            item
            for item in episodes
            if str(item.get("id") or "") == episode_id
        ),
        episodes[0] if len(episodes) == 1 else {},
    )
    title = cheese_episode_title(episode, 1) if episode else clean_title(str(info.get("title") or url))
    return MediaNode(
        id=url,
        title=title,
        thumbnail=str(episode.get("cover") or info.get("cover") or ""),
        remarks=duration_text(episode.get("duration")),
        content=cheese_content_from_metadata(info),
        play_from="yt-dlp",
        play_url=url,
        node_kind=NodeKind.LEAF_VOD.value,
    )


def page_episode(page: dict[str, Any], index: int, fallback_url: str) -> MediaEpisode:
    page_number = page.get("page") or index
    title = clean_title(str(page.get("part") or f"P{int(page_number):02d}"))
    if not title.lower().startswith("p"):
        title = f"P{int(page_number):02d} {title}".strip()
    url = with_query_param(fallback_url, "p", str(page_number))
    return MediaEpisode(title, url)


def node_from_medialist(info: dict[str, Any], fallback_url: str) -> MediaNode:
    entries = dict_list(info.get("entries"))
    return MediaNode(
        id=fallback_url,
        title=str(info.get("title") or fallback_url),
        kind="playlist",
        thumbnail=str(info.get("thumbnail") or ""),
        **collection_count_fields(info, len(entries), "playlist"),
    )


def light_playlist_node(
    info: dict[str, Any],
    fallback_url: str,
    title_fallback: str,
    remarks: str = "",
    remarks_key: str = "",
) -> MediaNode:
    return MediaNode(
        id=fallback_url,
        title=str(info.get("title") or title_fallback),
        kind="playlist",
        thumbnail=str(info.get("thumbnail") or ""),
        **collection_count_fields(info, 0, remarks_key, remarks),
    )


def aggregate_nodes_from_medialist(info: dict[str, Any]) -> list[MediaNode]:
    entries = dict_list(info.get("entries"))
    return [
        node
        for node in (aggregate_node_from_medialist_entry(entry, index) for index, entry in enumerate(entries, 1))
        if node
    ]


def node_from_medialist_entry(entry: dict[str, Any]) -> MediaNode | None:
    bvid = entry_bvid(entry)
    if not bvid:
        return None
    page_count = medialist_entry_page_count(entry)
    remarks = f"{page_count}P" if page_count > 1 else duration_text(entry.get("duration"))
    return MediaNode(
        id=f"https://www.bilibili.com/video/{bvid}",
        title=clean_title(str(entry.get("title") or bvid)),
        thumbnail=str(entry.get("cover") or entry.get("pic") or ""),
        remarks=remarks,
        node_kind=(NodeKind.AGGREGATE_VOD if page_count > 1 else NodeKind.LEAF_VOD).value,
    )


def aggregate_node_from_medialist_entry(entry: dict[str, Any], index: int) -> MediaNode | None:
    node = node_from_medialist_entry(entry)
    if not node:
        return None
    if not medialist_entry_is_single_page(entry):
        return node
    episode = medialist_episode(entry, index)
    if not episode:
        return None
    return MediaNode(
        id=node.id,
        title=node.title,
        thumbnail=node.thumbnail,
        remarks=node.remarks,
        playlist_name=episode.title,
        playlist_url=episode.url,
        node_kind=NodeKind.LEAF_VOD.value,
    )


def playable_playlist_node_from_medialist(info: dict[str, Any], fallback_url: str) -> MediaNode:
    entries = dict_list(info.get("entries"))
    episodes = tuple(
        episode
        for episode in (medialist_episode(entry, index) for index, entry in enumerate(entries, 1) if medialist_entry_is_single_page(entry))
        if episode
    )
    return MediaNode(
        id=fallback_url,
        title=str(info.get("title") or fallback_url),
        kind="playlist",
        thumbnail=str(info.get("thumbnail") or ""),
        **collection_count_fields(info, len(entries), "playlist"),
        play_from="yt-dlp",
        episodes=episodes,
    )


def medialist_episode(entry: dict[str, Any], index: int) -> MediaEpisode | None:
    bvid = entry_bvid(entry)
    if not bvid:
        return None
    title = clean_title(str(entry.get("title") or i18n.episode_title(index)))
    url = with_query_param(f"https://www.bilibili.com/video/{bvid}", "dashbox_index", str(index))
    return MediaEpisode(title, url)


def medialist_entry_page_count(entry: dict[str, Any]) -> int:
    pages = dict_list(entry.get("pages"))
    if pages:
        return len(pages)
    return positive_int(entry.get("videos"))


def medialist_entry_is_single_page(entry: dict[str, Any]) -> bool:
    return medialist_entry_page_count(entry) == 1


def medialist_entry_has_page_count_hint(entry: dict[str, Any]) -> bool:
    if entry.get("pages"):
        return True
    return bool(positive_int(entry.get("videos")))


def entry_bvid(entry: dict[str, Any]) -> str:
    return str(entry.get("bv_id") or entry.get("bvid") or "")


def search_node_from_entry(entry: dict[str, Any]) -> MediaNode | None:
    bvid = entry_bvid(entry)
    url = f"https://www.bilibili.com/video/{bvid}" if bvid else str(entry.get("arcurl") or "")
    if not url:
        return None
    title = clean_html_text(str(entry.get("title") or bvid or url))
    duration = existing_duration_text(entry.get("duration")) or duration_text(entry.get("duration"))
    author = clean_html_text(str(entry.get("author") or entry.get("typename") or ""))
    remarks = duration or author
    return MediaNode(
        id=url,
        title=title or url,
        thumbnail=normalize_image_url(str(entry.get("pic") or "")),
        remarks=remarks,
    )


def node_from_bangumi_season(info: dict[str, Any], fallback_url: str) -> MediaNode:
    episodes = dict_list(info.get("episodes"))
    return MediaNode(
        id=fallback_url,
        title=clean_title(str(info.get("title") or fallback_url)),
        kind="playlist",
        thumbnail=str(info.get("cover") or ""),
        remarks_key="item_count" if episodes else "bilibili_bangumi",
        item_count=len(episodes),
        content=clean_content(str(info.get("evaluate") or "")),
        node_kind=NodeKind.PLAYLIST_DIRECTORY.value,
    )


def aggregate_nodes_from_bangumi_season(info: dict[str, Any]) -> list[MediaNode]:
    episodes = dict_list(info.get("episodes"))
    directory_content = clean_content(str(info.get("evaluate") or ""))
    return [
        node
        for node in (
            aggregate_node_from_bangumi_episode(
                episode,
                index,
                directory_content=directory_content,
            )
            for index, episode in enumerate(episodes, 1)
        )
        if node
    ]


def node_from_bangumi_episode(episode: dict[str, Any], index: int, *, content: str = "") -> MediaNode | None:
    episode_id = str(episode.get("id") or episode.get("ep_id") or "")
    if not episode_id:
        return None
    title = bangumi_episode_title(episode, index)
    return MediaNode(
        id=f"https://www.bilibili.com/bangumi/play/ep{episode_id}",
        title=title,
        thumbnail=str(episode.get("cover") or ""),
        remarks=duration_text(bangumi_duration_seconds(episode.get("duration"))),
        content=content,
        node_kind=NodeKind.LEAF_VOD.value,
    )


def aggregate_node_from_bangumi_episode(
    episode: dict[str, Any],
    index: int,
    *,
    directory_content: str = "",
) -> MediaNode | None:
    node = node_from_bangumi_episode(episode, index, content=directory_content)
    if not node:
        return None
    return MediaNode(
        id=node.id,
        title=node.title,
        thumbnail=node.thumbnail,
        remarks=node.remarks,
        content=node.content,
        playlist_name=bangumi_episode_title(episode, index),
        playlist_url=node.id,
        node_kind=NodeKind.LEAF_VOD.value,
    )


def playable_playlist_node_from_bangumi_season(info: dict[str, Any], fallback_url: str) -> MediaNode:
    episodes = dict_list(info.get("episodes"))
    media_episodes = tuple(
        episode
        for episode in (bangumi_episode(episode, index) for index, episode in enumerate(episodes, 1))
        if episode
    )
    return MediaNode(
        id=fallback_url,
        title=clean_title(str(info.get("title") or fallback_url)),
        kind="playlist",
        thumbnail=str(info.get("cover") or ""),
        remarks_key="item_count" if episodes else "bilibili_bangumi",
        item_count=len(episodes),
        content=clean_content(str(info.get("evaluate") or "")),
        play_from="yt-dlp",
        episodes=media_episodes,
        node_kind=NodeKind.PLAYLIST_DIRECTORY.value,
    )


def node_from_cheese_season(info: dict[str, Any], fallback_url: str) -> MediaNode:
    episodes = dict_list(info.get("episodes"))
    return MediaNode(
        id=fallback_url,
        title=clean_title(str(info.get("title") or fallback_url)),
        kind="playlist",
        thumbnail=str(info.get("cover") or ""),
        remarks_key="item_count" if episodes else "bilibili_course",
        item_count=len(episodes),
        content=cheese_content_from_metadata(info),
        node_kind=NodeKind.PLAYLIST_DIRECTORY.value,
    )


def aggregate_nodes_from_cheese_season(info: dict[str, Any]) -> list[MediaNode]:
    episodes = dict_list(info.get("episodes"))
    directory_content = cheese_content_from_metadata(info)
    return [
        node
        for node in (
            aggregate_node_from_cheese_episode(
                episode,
                index,
                directory_content=directory_content,
            )
            for index, episode in enumerate(episodes, 1)
        )
        if node
    ]


def aggregate_node_from_cheese_episode(
    episode: dict[str, Any],
    index: int,
    *,
    directory_content: str = "",
) -> MediaNode | None:
    node = node_from_cheese_episode(episode, index, content=directory_content)
    if not node:
        return None
    return MediaNode(
        id=node.id,
        title=node.title,
        thumbnail=node.thumbnail,
        remarks=node.remarks,
        content=node.content,
        playlist_name=node.title,
        playlist_url=node.id,
        node_kind=NodeKind.LEAF_VOD.value,
    )


def node_from_cheese_episode(episode: dict[str, Any], index: int, *, content: str = "") -> MediaNode | None:
    episode_id = str(episode.get("id") or "")
    if not episode_id:
        return None
    return MediaNode(
        id=f"https://www.bilibili.com/cheese/play/ep{episode_id}",
        title=cheese_episode_title(episode, index),
        thumbnail=str(episode.get("cover") or ""),
        remarks=duration_text(episode.get("duration")),
        content=content,
        node_kind=NodeKind.LEAF_VOD.value,
    )


def playable_playlist_node_from_cheese_season(info: dict[str, Any], fallback_url: str) -> MediaNode:
    episodes = dict_list(info.get("episodes"))
    media_episodes = tuple(
        episode
        for episode in (cheese_episode(episode, index) for index, episode in enumerate(episodes, 1))
        if episode
    )
    return MediaNode(
        id=fallback_url,
        title=clean_title(str(info.get("title") or fallback_url)),
        kind="playlist",
        thumbnail=str(info.get("cover") or ""),
        remarks_key="item_count" if episodes else "bilibili_course",
        item_count=len(episodes),
        content=cheese_content_from_metadata(info),
        play_from="yt-dlp",
        episodes=media_episodes,
    )


def cheese_episode(episode: dict[str, Any], index: int) -> MediaEpisode | None:
    episode_id = str(episode.get("id") or "")
    if not episode_id:
        return None
    url = f"https://www.bilibili.com/cheese/play/ep{episode_id}"
    return MediaEpisode(cheese_episode_title(episode, index), url)


def cheese_episode_title(episode: dict[str, Any], index: int) -> str:
    title = clean_title(str(episode.get("title") or ""))
    ep_index = positive_int(episode.get("index"))
    prefix = str(ep_index or index)
    return f"{prefix} - {title}" if title else i18n.lesson_title(index)


def cheese_content_from_metadata(info: dict[str, Any]) -> str:
    brief = info.get("brief")
    if isinstance(brief, dict):
        content = str(brief.get("content") or "")
        if content:
            return clean_content(content)
    return clean_content(str(info.get("subtitle") or info.get("description") or ""))


def node_from_audio_album(info: dict[str, Any], fallback_url: str) -> MediaNode:
    entries = dict_list(info.get("entries"))
    return MediaNode(
        id=fallback_url,
        title=clean_title(str(info.get("title") or fallback_url)),
        kind="playlist",
        thumbnail=str(info.get("thumbnail") or ""),
        **collection_count_fields(info, len(entries), "bilibili_songlist"),
        node_kind=NodeKind.PLAYLIST_DIRECTORY.value,
    )


def aggregate_nodes_from_audio_album(info: dict[str, Any]) -> list[MediaNode]:
    entries = dict_list(info.get("entries"))
    return [
        node
        for node in (aggregate_node_from_audio_entry(entry, index) for index, entry in enumerate(entries, 1))
        if node
    ]


def aggregate_node_from_audio_entry(entry: dict[str, Any], index: int) -> MediaNode | None:
    node = node_from_audio_entry(entry)
    if not node:
        return None
    return MediaNode(
        id=node.id,
        title=node.title,
        thumbnail=node.thumbnail,
        remarks=node.remarks,
        playlist_name=node.title,
        playlist_url=with_query_param(node.id, "dashbox_index", str(index)),
        node_kind=NodeKind.LEAF_VOD.value,
    )


def node_from_audio_entry(entry: dict[str, Any]) -> MediaNode | None:
    audio_id = str(entry.get("id") or "")
    if not audio_id:
        return None
    return MediaNode(
        id=f"https://www.bilibili.com/audio/au{audio_id}",
        title=clean_title(str(entry.get("title") or audio_id)),
        thumbnail=str(entry.get("cover") or ""),
        remarks=duration_text(entry.get("duration")),
        node_kind=NodeKind.LEAF_VOD.value,
    )


def playable_playlist_node_from_audio_album(info: dict[str, Any], fallback_url: str) -> MediaNode:
    entries = dict_list(info.get("entries"))
    episodes = tuple(
        episode
        for episode in (audio_episode(entry, index) for index, entry in enumerate(entries, 1))
        if episode
    )
    return MediaNode(
        id=fallback_url,
        title=clean_title(str(info.get("title") or fallback_url)),
        kind="playlist",
        thumbnail=str(info.get("thumbnail") or ""),
        **collection_count_fields(info, len(entries), "bilibili_songlist"),
        play_from="yt-dlp",
        episodes=episodes,
        node_kind=NodeKind.PLAYLIST_DIRECTORY.value,
    )


def audio_episode(entry: dict[str, Any], index: int) -> MediaEpisode | None:
    audio_id = str(entry.get("id") or "")
    if not audio_id:
        return None
    title = clean_title(str(entry.get("title") or i18n.song_title(index)))
    url = with_query_param(f"https://www.bilibili.com/audio/au{audio_id}", "dashbox_index", str(index))
    return MediaEpisode(title, url)


def bangumi_episode(episode: dict[str, Any], index: int) -> MediaEpisode | None:
    episode_id = str(episode.get("id") or episode.get("ep_id") or "")
    if not episode_id:
        return None
    title = bangumi_episode_title(episode, index)
    url = f"https://www.bilibili.com/bangumi/play/ep{episode_id}"
    return MediaEpisode(title, url)


def bangumi_episode_title(episode: dict[str, Any], index: int) -> str:
    title = clean_title(str(episode.get("title") or ""))
    long_title = clean_title(str(episode.get("long_title") or ""))
    if title and long_title:
        return f"{title} {long_title}"
    return title or long_title or i18n.episode_title(index)


def bangumi_duration_seconds(value: Any) -> Any:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return value
    if duration > 100000:
        return duration // 1000
    return duration
