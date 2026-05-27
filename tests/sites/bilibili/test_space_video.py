import asyncio

from dashbox.config import Config
from dashbox.sites import bilibili
from tests.helpers import make_tvbox_service as MediaService


def test_space_video_metadata_uses_wbi2_arc_search_api() -> None:
    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, payload: dict, status_code: int = 200) -> None:
            self.payload = payload
            self.status_code = status_code

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class FakeAsyncClient:
        async def get(self, url: str, **kwargs):
            calls.append({"url": url, **kwargs})
            if url.endswith("/x/web-interface/card"):
                assert kwargs["params"] == {"mid": "60000004"}
                return FakeResponse({
                    "code": 0,
                    "data": {
                        "card": {
                            "name": "Sample UP",
                            "face": "https://i0.hdslb.com/bfs/face.jpg",
                            "sign": "Sample sign",
                        }
                    },
                })
            if url.endswith("/x/frontend/finger/spi"):
                return FakeResponse({"data": {"b_3": "buvid3-value", "b_4": "buvid4-value"}})
            if url.endswith("/x/web-interface/nav"):
                return FakeResponse({
                    "data": {
                        "wbi_img": {
                            "img_url": "https://i0.hdslb.com/bfs/wbi/abcdefghijklmnopqrstuvwxyzabcdef.png",
                            "sub_url": "https://i0.hdslb.com/bfs/wbi/0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ01.png",
                        }
                    }
                })
            if url.endswith("/x/space/wbi/arc/search"):
                params = kwargs["params"]
                assert params["mid"] == "60000004"
                assert params["pn"] == "1"
                assert params["ps"] == "30"
                assert params["tid"] == "0"
                assert params["order"] == "pubdate"
                assert params["order_avoided"] == "true"
                assert params["platform"] == "web"
                assert params["dm_img_list"] == "[]"
                assert params["dm_img_str"]
                assert params["dm_cover_img_str"]
                assert params["dm_img_inter"] == '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}'
                assert params["w_rid"]
                assert "buvid3=buvid3-value" in kwargs["headers"]["Cookie"]
                return FakeResponse({
                    "code": 0,
                    "message": "OK",
                    "data": {
                        "page": {"count": 42},
                        "list": {
                            "vlist": [
                                {
                                    "bvid": "BV1xx411c7mD",
                                    "aid": 10000001,
                                    "title": "主页投稿",
                                    "pic": "https://i0.hdslb.com/bfs/archive.jpg",
                                    "pages": [{"page": 1, "part": "正片"}],
                                }
                            ]
                        },
                    },
                })
            raise AssertionError(url)

    site = bilibili.BilibiliSite(http_client_provider=lambda: FakeAsyncClient())

    value = asyncio.run(site.space_video_metadata("https://space.bilibili.com/60000004/video"))

    assert [call["url"] for call in calls] == [
        "https://api.bilibili.com/x/web-interface/card",
        "https://api.bilibili.com/x/frontend/finger/spi",
        "https://api.bilibili.com/x/web-interface/nav",
        "https://api.bilibili.com/x/space/wbi/arc/search",
    ]
    assert value["title"] == "Sample UP - 视频"
    assert value["thumbnail"] == "https://i0.hdslb.com/bfs/face.jpg"
    assert value["description"] == "Sample sign"
    assert value["total"] == 42
    assert value["entries"][0]["bvid"] == "BV1xx411c7mD"


def test_space_video_category_expands_archive_nodes(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_space_video_metadata(url: str) -> dict:
        return {
            "title": "60000004 - 视频",
            "total": 1,
            "entries": [
                {
                    "bvid": "BV1xx411c7mD",
                    "title": "主页投稿",
                    "pic": "https://i0.hdslb.com/bfs/archive.jpg",
                    "pages": [{"page": 1, "part": "正片"}],
                }
            ],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "space_video_metadata", fake_space_video_metadata)

    value = asyncio.run(service.category("https://space.bilibili.com/60000004/video"))

    directory, first = value["list"]
    assert directory["vod_name"] == "播放此列表"
    assert directory["vod_remarks"] == "1项"
    assert first["vod_name"] == "主页投稿"
    assert first["dashbox_playlist_url"] == "https://www.bilibili.com/video/BV1xx411c7mD?dashbox_index=1"
