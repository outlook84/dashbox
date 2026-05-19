from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..utils.dicts import compact_dict


@dataclass(frozen=True)
class Vod:
    vod_id: str
    vod_name: str
    vod_pic: str = ""
    vod_remarks: str = ""
    vod_content: str = ""
    type_flag: str = ""
    vod_tag: str = ""
    vod_play_from: str = ""
    vod_play_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(
            vod_id=self.vod_id,
            vod_name=self.vod_name,
            vod_pic=self.vod_pic,
            vod_remarks=self.vod_remarks,
            vod_content=self.vod_content,
            type_flag=self.type_flag,
            vod_tag=self.vod_tag,
            vod_play_from=self.vod_play_from,
            vod_play_url=self.vod_play_url,
        )


@dataclass
class Page:
    list: list[dict[str, Any]] = field(default_factory=list)
    page: int = 1
    pagecount: int = 1
    limit: int = 0
    total: int = 0

    def to_dict(self) -> dict[str, Any]:
        limit = self.limit or len(self.list)
        total = self.total or len(self.list)
        return compact_dict(list=self.list, page=self.page, pagecount=self.pagecount, limit=limit, total=total)
