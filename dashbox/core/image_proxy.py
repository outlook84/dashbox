from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import Response

from ..config import Config, ImageProxyMode
from . import image_policy


logger = logging.getLogger("dashbox.image_proxy")

IMAGE_CACHE_TTL_SECONDS = 24 * 60 * 60
IMAGE_CACHE_MAX_BYTES = 64 * 1024 * 1024
IMAGE_CACHE_MAX_ITEM_BYTES = 2 * 1024 * 1024
IMAGE_PREFETCH_LIMIT = 32
IMAGE_PREFETCH_CONCURRENCY = 8
IMAGE_FETCH_CONCURRENCY = 12
IMAGE_FETCH_MAX_REDIRECTS = 3
IMAGE_FETCH_PRIORITY_FOREGROUND = 0
IMAGE_FETCH_PRIORITY_BACKGROUND = 10
IMAGE_PREFETCH_INDEX_TTL_SECONDS = 10 * 60
IMAGE_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class ImageCache:
    def __init__(
        self,
        max_bytes: int = IMAGE_CACHE_MAX_BYTES,
        max_item_bytes: int = IMAGE_CACHE_MAX_ITEM_BYTES,
    ) -> None:
        self.max_bytes = max_bytes
        self.max_item_bytes = max_item_bytes
        self._current_bytes = 0
        self._items: OrderedDict[str, tuple[float, bytes, str, dict[str, str], int]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, url: str) -> tuple[bytes, str, dict[str, str]] | None:
        async with self._lock:
            item = self._items.get(url)
            if not item:
                return None
            expires_at, content, media_type, headers, _size = item
            if expires_at <= time.monotonic():
                self._pop(url)
                return None
            self._items.move_to_end(url)
            return content, media_type, dict(headers)

    async def set(self, url: str, content: bytes, media_type: str, headers: dict[str, str]) -> None:
        async with self._lock:
            self._pop(url)
            size = len(content)
            if size > self.max_item_bytes:
                return
            self._items[url] = (time.monotonic() + IMAGE_CACHE_TTL_SECONDS, content, media_type, dict(headers), size)
            self._current_bytes += size
            self._items.move_to_end(url)
            self._prune_expired()
            self._prune_bytes()

    def _prune_expired(self) -> None:
        now = time.monotonic()
        expired = [url for url, (expires_at, *_rest) in self._items.items() if expires_at <= now]
        for url in expired:
            self._pop(url)

    def _prune_bytes(self) -> None:
        while self._current_bytes > self.max_bytes and self._items:
            _url, item = self._items.popitem(last=False)
            self._current_bytes -= item[4]

    def _pop(self, url: str) -> None:
        item = self._items.pop(url, None)
        if item:
            self._current_bytes -= item[4]


class ImagePrefetchIndex:
    def __init__(self) -> None:
        self._groups: dict[str, tuple[float, tuple[str, ...], bool]] = {}
        self._url_to_groups: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def scoped_key(protocol: str, sub_id: str, key: str) -> str:
        return "\0".join((protocol, sub_id, key))

    async def register(self, key: str, urls: list[str], *, protocol: str = "", sub_id: str = "") -> None:
        key = self.scoped_key(protocol, sub_id, key) if protocol or sub_id else key
        urls = list(dict.fromkeys(urls))[:IMAGE_PREFETCH_LIMIT]
        if not key or not urls:
            return
        async with self._lock:
            self._drop_group(key)
            expires_at = time.monotonic() + IMAGE_PREFETCH_INDEX_TTL_SECONDS
            self._groups[key] = (expires_at, tuple(urls), False)
            for url in urls:
                self._url_to_groups.setdefault(url, set()).add(key)

    async def trigger(self, url: str, *, protocol: str = "", sub_id: str = "") -> tuple[str, ...]:
        async with self._lock:
            keys = self._url_to_groups.get(url) or set()
            if protocol or sub_id:
                prefix = self.scoped_key(protocol, sub_id, "")
                keys = {key for key in keys if key.startswith(prefix)}
            key = sorted(keys)[0] if keys else ""
            if not key:
                return ()
            item = self._groups.get(key)
            if not item:
                self._remove_url_group(url, key)
                return ()
            expires_at, urls, started = item
            if expires_at <= time.monotonic():
                self._drop_group(key)
                return ()
            if started:
                return ()
            self._groups[key] = (expires_at, urls, True)
            return tuple(item for item in urls if item != url)

    def _drop_group(self, key: str) -> None:
        item = self._groups.pop(key, None)
        if not item:
            return
        _expires_at, urls, _started = item
        for url in urls:
            self._remove_url_group(url, key)

    def _remove_url_group(self, url: str, key: str) -> None:
        keys = self._url_to_groups.get(url)
        if not keys:
            return
        keys.discard(key)
        if not keys:
            self._url_to_groups.pop(url, None)


class ImageFetchJob:
    def __init__(
        self,
        url: str,
        config: Config,
        request_headers: dict[str, str],
        priority: int,
        sequence: int,
        future: asyncio.Future[tuple[bytes, str, dict[str, str]]],
    ) -> None:
        self.url = url
        self.config = config
        self.request_headers = request_headers
        self.priority = priority
        self.sequence = sequence
        self.future = future
        self.running = False


class ImageFetchManager:
    def __init__(self, concurrency: int = IMAGE_FETCH_CONCURRENCY) -> None:
        self._jobs: dict[str, ImageFetchJob] = {}
        self._queue: asyncio.PriorityQueue[tuple[int, int, str]] = asyncio.PriorityQueue()
        self._workers: list[asyncio.Task[None]] = []
        self._concurrency = max(1, concurrency)
        self._sequence = 0
        self._closed = False
        self._lock = asyncio.Lock()
        self._client: Any = None
        self._client_lock = asyncio.Lock()

    async def get(
        self,
        url: str,
        config: Config,
        request_headers: dict[str, str],
        priority: int = IMAGE_FETCH_PRIORITY_FOREGROUND,
    ) -> tuple[bytes, str, dict[str, str]]:
        async with self._lock:
            if self._closed:
                raise RuntimeError("image fetch manager is closed")
            self._ensure_workers_locked()
            job = self._jobs.get(url)
            if job:
                if priority < job.priority and not job.running and not job.future.done():
                    self._sequence += 1
                    job.priority = priority
                    job.sequence = self._sequence
                    job.config = config
                    job.request_headers = request_headers
                    await self._queue.put((job.priority, job.sequence, url))
                future = job.future
            else:
                self._sequence += 1
                future = asyncio.get_running_loop().create_future()
                job = ImageFetchJob(url, config, request_headers, priority, self._sequence, future)
                self._jobs[url] = job
                await self._queue.put((job.priority, job.sequence, url))
        try:
            return await future
        finally:
            if future.done():
                async with self._lock:
                    if self._jobs.get(url) is job:
                        self._jobs.pop(url, None)

    def _ensure_workers_locked(self) -> None:
        while len(self._workers) < self._concurrency:
            self._workers.append(asyncio.create_task(self._worker()))

    async def _worker(self) -> None:
        while True:
            priority, sequence, url = await self._queue.get()
            try:
                async with self._lock:
                    job = self._jobs.get(url)
                    if (
                        not job
                        or job.future.done()
                        or job.running
                        or job.priority != priority
                        or job.sequence != sequence
                    ):
                        continue
                    job.running = True
                try:
                    client = await self._get_client()
                    result = await fetch_image_with_client(client, job.url, job.config, job.request_headers)
                except Exception as exc:
                    if not job.future.done():
                        job.future.set_exception(exc)
                else:
                    if not job.future.done():
                        job.future.set_result(result)
                finally:
                    async with self._lock:
                        if self._jobs.get(url) is job:
                            self._jobs.pop(url, None)
            finally:
                self._queue.task_done()

    async def _get_client(self) -> Any:
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                import httpx

                self._client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
            return self._client

    async def aclose(self) -> None:
        async with self._lock:
            self._closed = True
            jobs = list(self._jobs.values())
            self._jobs.clear()
            workers = self._workers
            self._workers = []
        for job in jobs:
            if not job.future.done():
                job.future.cancel()
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        async with self._client_lock:
            client = self._client
            self._client = None
        if client is not None:
            await client.aclose()


async def register_image_urls(
    key: str,
    urls: list[str],
    state: Any,
    *,
    protocol: str = "",
    sub_id: str = "",
) -> None:
    if state.config.image_proxy_mode == ImageProxyMode.OFF:
        return
    await state.image_prefetch.register(key, urls, protocol=protocol, sub_id=sub_id)


async def trigger_image_prefetch(url: str, state: Any, *, protocol: str = "", sub_id: str = "") -> None:
    if state.config.image_proxy_mode == ImageProxyMode.OFF:
        return
    urls = await state.image_prefetch.trigger(url, protocol=protocol, sub_id=sub_id)
    if urls:
        asyncio.create_task(prefetch_images(urls, state))


async def prefetch_images(urls: tuple[str, ...], state: Any) -> None:
    try:
        if state.config.image_proxy_mode == ImageProxyMode.OFF:
            return
        if not urls:
            return
        semaphore = asyncio.Semaphore(IMAGE_PREFETCH_CONCURRENCY)

        async def prefetch(url: str) -> None:
            if await state.image_cache.get(url):
                return
            async with semaphore:
                try:
                    await fetch_cached_image(
                        url,
                        state.config,
                        {},
                        state.image_cache,
                        state.image_fetcher,
                        IMAGE_FETCH_PRIORITY_BACKGROUND,
                    )
                except HTTPException:
                    return

        await asyncio.gather(*(prefetch(url) for url in urls))
    except Exception:
        logger.debug("image prefetch failed", exc_info=True)


def image_upstream_from_proxy_url(value: str, config: Config) -> str:
    parts = urlsplit(value)
    if parts.path != "/image":
        return ""
    values = parse_qs(parts.query).get("url") or []
    if not values:
        return ""
    url = values[0]
    if image_policy.is_supported_image_proxy_url(url, config.image_proxy_mode):
        return url
    return ""


async def proxy_image(
    url: str,
    config: Config,
    request: Request,
    cache: ImageCache | None = None,
    fetcher: ImageFetchManager | None = None,
) -> Response:
    if cache:
        cached = await cache.get(url)
        if cached:
            content, media_type, response_headers = cached
            if image_not_modified(request, response_headers):
                return Response(status_code=304, headers=response_headers)
            return Response(content=content, media_type=media_type, headers=response_headers)
    content, media_type, response_headers = await fetch_cached_image(url, config, {}, cache, fetcher)
    return Response(content=content, media_type=media_type, headers=response_headers)


async def proxy_image_head(
    url: str,
    config: Config,
    request: Request,
    cache: ImageCache | None = None,
) -> Response:
    if cache:
        cached = await cache.get(url)
        if cached:
            content, media_type, response_headers = cached
            if image_not_modified(request, response_headers):
                return Response(status_code=304, headers=response_headers)
            headers = dict(response_headers)
            headers["Content-Length"] = str(len(content))
            return Response(content=b"", media_type=media_type, headers=headers)
    media_type, response_headers = await fetch_image_head(url, config, {})
    return Response(content=b"", media_type=media_type, headers=response_headers)


def image_not_modified(request: Request, response_headers: dict[str, str]) -> bool:
    etag = response_headers.get("etag")
    if etag and etag_matches(request.headers.get("if-none-match", ""), etag):
        return True
    last_modified = response_headers.get("last-modified")
    if last_modified and request.headers.get("if-modified-since") == last_modified:
        return True
    return False


def etag_matches(header_value: str, etag: str) -> bool:
    values = [value.strip() for value in header_value.split(",")]
    return "*" in values or etag in values


async def fetch_cached_image(
    url: str,
    config: Config,
    request_headers: dict[str, str],
    cache: ImageCache | None,
    fetcher: ImageFetchManager | None,
    priority: int = IMAGE_FETCH_PRIORITY_FOREGROUND,
) -> tuple[bytes, str, dict[str, str]]:
    if cache:
        cached = await cache.get(url)
        if cached:
            return cached
    if fetcher:
        content, media_type, response_headers = await fetcher.get(url, config, request_headers, priority)
    else:
        content, media_type, response_headers = await fetch_image(url, config, request_headers)
    if cache:
        await cache.set(url, content, media_type, response_headers)
    return content, media_type, response_headers


async def fetch_image(url: str, config: Config, request_headers: dict[str, str]) -> tuple[bytes, str, dict[str, str]]:
    import httpx

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        return await fetch_image_with_client(client, url, config, request_headers)


async def fetch_image_head(url: str, config: Config, request_headers: dict[str, str]) -> tuple[str, dict[str, str]]:
    import httpx

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        return await fetch_image_head_with_client(client, url, config, request_headers)


async def fetch_image_head_with_client(
    client: Any,
    url: str,
    config: Config,
    request_headers: dict[str, str],
    host_resolves_to_blocked_address: Any = None,
) -> tuple[str, dict[str, str]]:
    import httpx

    if host_resolves_to_blocked_address is None:
        host_resolves_to_blocked_address = image_policy.image_proxy_host_resolves_to_blocked_address
    current_url = url
    response = None
    try:
        for _redirect_count in range(IMAGE_FETCH_MAX_REDIRECTS + 1):
            if not image_policy.is_supported_image_proxy_url(current_url, config.image_proxy_mode):
                raise HTTPException(status_code=400, detail="unsupported image upstream")
            host = urlsplit(current_url).hostname or ""
            if await host_resolves_to_blocked_address(host):
                raise HTTPException(status_code=400, detail="unsupported image upstream")
            headers = {
                "User-Agent": config.effective_user_agent,
            }
            if referer := image_policy.referer_for_image_url(current_url):
                headers["Referer"] = referer
            headers.update(request_headers)
            request = client.build_request("HEAD", current_url, headers=headers)
            response = await client.send(request, stream=True, follow_redirects=False)
            if response.status_code not in IMAGE_REDIRECT_STATUSES:
                break
            location = response.headers.get("location", "")
            await response.aclose()
            response = None
            if not location:
                raise HTTPException(status_code=502, detail="image upstream redirect missing location")
            current_url = urljoin(current_url, location)
        else:
            raise HTTPException(status_code=502, detail="image upstream redirected too many times")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="image upstream failed") from exc
    if response is None:
        raise HTTPException(status_code=502, detail="image upstream failed")
    try:
        if response.status_code == 304:
            raise HTTPException(status_code=502, detail="image upstream returned no content")
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail="image upstream rejected")
        media_type = response.headers.get("content-type", "").strip() or "image/jpeg"
        if not image_content_type_is_allowed(media_type):
            raise HTTPException(status_code=415, detail="image upstream returned non-image content")
        response_headers = {"Cache-Control": "public, max-age=86400"}
        for key in ("content-length", "etag", "last-modified"):
            value = response.headers.get(key)
            if value:
                response_headers[key] = value
        return media_type, response_headers
    finally:
        await response.aclose()


async def fetch_image_with_client(
    client: Any,
    url: str,
    config: Config,
    request_headers: dict[str, str],
    host_resolves_to_blocked_address: Any = None,
) -> tuple[bytes, str, dict[str, str]]:
    import httpx

    if host_resolves_to_blocked_address is None:
        host_resolves_to_blocked_address = image_policy.image_proxy_host_resolves_to_blocked_address
    current_url = url
    response = None
    try:
        for _redirect_count in range(IMAGE_FETCH_MAX_REDIRECTS + 1):
            if not image_policy.is_supported_image_proxy_url(current_url, config.image_proxy_mode):
                raise HTTPException(status_code=400, detail="unsupported image upstream")
            host = urlsplit(current_url).hostname or ""
            if await host_resolves_to_blocked_address(host):
                raise HTTPException(status_code=400, detail="unsupported image upstream")
            headers = {
                "User-Agent": config.effective_user_agent,
            }
            if referer := image_policy.referer_for_image_url(current_url):
                headers["Referer"] = referer
            headers.update(request_headers)
            request = client.build_request("GET", current_url, headers=headers)
            response = await client.send(request, stream=True, follow_redirects=False)
            if response.status_code not in IMAGE_REDIRECT_STATUSES:
                break
            location = response.headers.get("location", "")
            await response.aclose()
            response = None
            if not location:
                raise HTTPException(status_code=502, detail="image upstream redirect missing location")
            current_url = urljoin(current_url, location)
        else:
            raise HTTPException(status_code=502, detail="image upstream redirected too many times")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="image upstream failed") from exc
    if response is None:
        raise HTTPException(status_code=502, detail="image upstream failed")
    if response.status_code == 304:
        await response.aclose()
        raise HTTPException(status_code=502, detail="image upstream returned no content")
    if response.status_code >= 400:
        await response.aclose()
        raise HTTPException(status_code=response.status_code, detail="image upstream rejected")
    media_type = response.headers.get("content-type", "").strip() or "image/jpeg"
    if not image_content_type_is_allowed(media_type):
        await response.aclose()
        raise HTTPException(status_code=415, detail="image upstream returned non-image content")
    try:
        content = await read_limited_image_response(response)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="image upstream failed") from exc
    response_headers = {"Cache-Control": "public, max-age=86400"}
    for key in ("etag", "last-modified"):
        value = response.headers.get(key)
        if value:
            response_headers[key] = value
    return content, media_type, response_headers


def image_content_type_is_allowed(value: str) -> bool:
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type.startswith("image/")


async def read_limited_image_response(response: Any) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = 0
        if declared_size > IMAGE_CACHE_MAX_ITEM_BYTES:
            await response.aclose()
            raise HTTPException(status_code=413, detail="image upstream too large")
    chunks = []
    size = 0
    try:
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > IMAGE_CACHE_MAX_ITEM_BYTES:
                raise HTTPException(status_code=413, detail="image upstream too large")
            chunks.append(chunk)
    finally:
        await response.aclose()
    return b"".join(chunks)
