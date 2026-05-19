from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ..config import Config
from ..sites import html_metadata
from ..sites import registry


class DisplayMetadataRuntime:
    def __init__(
        self,
        config: Config,
        *,
        download_impersonated: Callable[[str], Awaitable[str]],
        http_client_provider: Callable[[], Any] | None = None,
    ) -> None:
        self.config = config
        self.download_impersonated = download_impersonated
        self.http_client_provider = http_client_provider

    async def fetch(self, raw_id: str) -> dict[str, Any]:
        adapter = registry.resolve(raw_id)
        display_metadata = registry.default_callable(adapter, "display_metadata")
        return await display_metadata(
            raw_id,
            config=self.config,
            html_metadata=self.html_metadata,
            impersonated_html_metadata=self.impersonated_html_metadata,
            http_client_provider=self.http_client_provider,
        )

    async def html_metadata(self, raw_id: str) -> dict[str, Any]:
        return await html_metadata.html_light_metadata(raw_id, self.config, self.http_client_provider)

    async def impersonated_html_metadata(self, raw_id: str) -> dict[str, Any]:
        return await html_metadata.impersonated_html_light_metadata(raw_id, self.download_impersonated)
