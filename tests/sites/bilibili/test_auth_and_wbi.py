import asyncio
from http.cookiejar import Cookie, CookieJar


from dashbox.config import Config
from dashbox.sites import bilibili
from dashbox.sites.bilibili import site as bilibili_site
from tests.helpers import make_tvbox_service as MediaService
from tests.sites.bilibili.helpers import FAVLIST_URL


def test_bilibili_headers_adds_scoped_cookie() -> None:
    site = bilibili.BilibiliSite(
        user_agent="UA",
        cookie_header_provider=lambda url: "SESSDATA=value" if url == "https://api.bilibili.com/x/v3/fav/resource/list" else "",
    )

    headers = site.headers("https://api.bilibili.com/x/v3/fav/resource/list", FAVLIST_URL)

    assert headers["User-Agent"] == "UA"
    assert headers["Referer"] == FAVLIST_URL
    assert headers["Cookie"] == "SESSDATA=value"


def test_bilibili_wbi_search_uses_signed_search_api(monkeypatch) -> None:
    calls = []

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
            if url.endswith("/x/web-interface/wbi/search/type"):
                params = kwargs["params"]
                assert params["keyword"] == "samples live"
                assert params["search_type"] == "video"
                assert params["page_size"] == "2"
                assert params["web_location"] == "1550101"
                assert params["wts"]
                assert params["w_rid"]
                assert "buvid3=buvid3-value" in kwargs["headers"]["Cookie"]
                return FakeResponse({
                    "code": 0,
                    "data": {
                        "result": [
                                {
                                    "bvid": "BV1xx411c7mD",
                                    "title": "<em class=\"keyword\">sample</em> title",
                                    "pic": "//i1.hdslb.com/bfs/archive/pic.jpg",
                                    "duration": "01:02",
                                }
                        ]
                    },
                })
            raise AssertionError(url)

    site = bilibili.BilibiliSite(http_client_provider=lambda: FakeAsyncClient())

    nodes = asyncio.run(site.search_nodes("sample's (live)", limit=2))

    assert nodes[0].id == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert nodes[0].title == "sample title"
    assert nodes[0].thumbnail == "https://i1.hdslb.com/bfs/archive/pic.jpg"
    assert nodes[0].remarks == "01:02"
    assert [call["url"] for call in calls] == [
        "https://api.bilibili.com/x/frontend/finger/spi",
        "https://api.bilibili.com/x/web-interface/nav",
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
    ]


def test_bilibili_wbi_search_pages_by_requested_limit_not_list_limit(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class FakeAsyncClient:
        async def get(self, url: str, **kwargs):
            calls.append({"url": url, **kwargs})
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
            if url.endswith("/x/web-interface/wbi/search/type"):
                params = kwargs["params"]
                page = int(params["page"])
                page_size = int(params["page_size"])
                first_index = (page - 1) * 50
                results = [
                    {
                        "bvid": f"BV{first_index + index:010d}",
                        "title": f"video {first_index + index}",
                    }
                    for index in range(page_size)
                ]
                return FakeResponse({"code": 0, "data": {"result": results}})
            raise AssertionError(url)

    site = bilibili.BilibiliSite(list_limit=1, http_client_provider=lambda: FakeAsyncClient())

    nodes = asyncio.run(site.search_nodes("sample", limit=55))

    search_calls = [call for call in calls if call["url"].endswith("/x/web-interface/wbi/search/type")]
    assert len(nodes) == 55
    assert [call["params"]["page"] for call in search_calls] == ["1", "2"]
    assert [call["params"]["page_size"] for call in search_calls] == ["50", "5"]


def test_bilibili_wbi_params_send_sanitized_signed_values(monkeypatch) -> None:
    monkeypatch.setattr(bilibili_site.time, "time", lambda: 1234567890)

    params = bilibili.encode_wbi_params({"keyword": "Bob's (live)", "page": 1}, "mixin-key")

    assert params["keyword"] == "Bobs live"
    assert params["page"] == "1"
    assert params["wts"] == "1234567890"
    assert params["web_location"] == "1550101"
    assert params["w_rid"]


def test_bilibili_wbi_mixin_key_cache_expires(monkeypatch) -> None:
    now = 1000.0
    nav_calls = 0

    def fake_time() -> float:
        return now

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/abcdefghijklmnopqrstuvwxyzabcdef.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ01.png",
                    }
                }
            }

    class FakeAsyncClient:
        async def get(self, url: str, **kwargs):
            nonlocal nav_calls
            assert url.endswith("/x/web-interface/nav")
            nav_calls += 1
            return FakeResponse()

    monkeypatch.setattr(bilibili_site.time, "time", fake_time)
    site = bilibili.BilibiliSite()
    client = FakeAsyncClient()

    first_key = asyncio.run(site.wbi_mixin_key(client, {}))
    second_key = asyncio.run(site.wbi_mixin_key(client, {}))
    now += bilibili.WBI_MIXIN_KEY_TTL_SECONDS + 1
    third_key = asyncio.run(site.wbi_mixin_key(client, {}))

    assert first_key == second_key == third_key
    assert nav_calls == 2


def test_bilibili_wbi_get_json_refreshes_key_on_invalid_signature(monkeypatch) -> None:
    monkeypatch.setattr(bilibili_site.time, "time", lambda: 1000.0)
    calls = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class FakeAsyncClient:
        async def get(self, url: str, **kwargs):
            calls.append({"url": url, **kwargs})
            if url.endswith("/x/web-interface/nav"):
                return FakeResponse({
                    "data": {
                        "wbi_img": {
                            "img_url": "https://i0.hdslb.com/bfs/wbi/abcdefghijklmnopqrstuvwxyzabcdef.png",
                            "sub_url": "https://i0.hdslb.com/bfs/wbi/0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ01.png",
                        }
                    }
                })
            if url.endswith("/x/web-interface/wbi/search/type") and len([call for call in calls if call["url"] == url]) == 1:
                return FakeResponse({"code": -403, "message": "w_rid signature invalid"})
            return FakeResponse({"code": 0, "data": {"result": []}})

    site = bilibili.BilibiliSite()

    payload = asyncio.run(site.wbi_get_json(
        FakeAsyncClient(),
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
        {"keyword": "sample"},
        {},
        "stale-key",
        referer="https://www.bilibili.com",
    ))

    assert payload == {"code": 0, "data": {"result": []}}
    assert [call["url"] for call in calls] == [
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
        "https://api.bilibili.com/x/web-interface/nav",
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
    ]


def test_bilibili_cookie_header_uses_yt_dlp_cookiejar_scope() -> None:
    service = MediaService(Config(cookies_from_browser={"mode": "firefox"}))
    jar = CookieJar()
    jar.set_cookie(make_cookie("SESSDATA", "api-value", ".bilibili.com"))
    jar.set_cookie(make_cookie("OTHER", "example-value", ".example.com"))
    service.site_runtime.bilibili.cookies.cookiejar = jar
    service.site_runtime.bilibili.cookies.loaded = True

    cookie = service.site_runtime.bilibili.cookie_header("https://api.bilibili.com/x/v3/fav/resource/list")

    assert cookie == "SESSDATA=api-value"



def make_cookie(name: str, value: str, domain: str) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path="/",
        path_specified=True,
        secure=False,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )
