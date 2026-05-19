from dashbox.sites import xvideos
from dashbox.adapters import tvbox
from dashbox.core import media_mapper
from dashbox.core.client_model import item_from_media_node
from dashbox.config import ImageProxyMode


FAVORITE_URL = "https://www.xvideos.com/favorite/91000001/sample_list"


def test_playlist_entries_from_webpage_extracts_xvideos_favorite_items() -> None:
    webpage = """
    <div id="video_samplevideoid" data-id="83036075" data-eid="samplevideoid" class="frame-block thumb-block">
      <div class="thumb">
        <a href="/video.samplevideoid/sample_video?pl=91000001&amp;plname=sample_list">
          <img
            src="https://assets-cdn77.xvideos-cdn.com/img/lightbox/lightbox-blank.gif"
            data-src="https://thumb-cdn77.xvideos-cdn.com/6d26f8a2/0/xv_21_t.jpg"
          />
        </a>
      </div>
      <div class="thumb-under">
        <p class="title">
          <a href="/video.samplevideoid/sample_video?pl=91000001&amp;plname=sample_list" title="Risky Cheating">Risky Cheating <span class="duration">15 min</span></a>
        </p>
      </div>
    </div>
    """

    entries = xvideos.playlist_entries_from_webpage(webpage, FAVORITE_URL)

    assert entries["samplevideoid"] == {
        "ie_key": "XVideos",
        "_type": "url",
        "id": "samplevideoid",
        "url": "https://www.xvideos.com/video.samplevideoid/sample_video?pl=91000001&plname=sample_list",
        "webpage_url": "https://www.xvideos.com/video.samplevideoid/sample_video?pl=91000001&plname=sample_list",
        "title": "Risky Cheating",
        "thumbnail": "https://thumb-cdn77.xvideos-cdn.com/6d26f8a2/0/xv_21_t.jpg",
        "duration_string": "15 min",
    }


def test_playlist_entries_from_webpage_handles_reordered_xvideos_attrs() -> None:
    webpage = """
    <div data-eid="one" class="thumb-block frame-block" data-id="1">
      <p class="title">
        <a title="One title" href="/video.one/title">
          <span class="duration">7 min</span>
        </a>
      </p>
      <a data-extra="x" href="/video.one/title?pl=91000001&amp;plname=sample_list">
        <img alt="ignored" src="https://example.test/fallback.jpg" data-src="https://example.test/one.jpg">
      </a>
    </div>
    """

    entries = xvideos.playlist_entries_from_webpage(webpage, FAVORITE_URL)

    assert entries["one"]["title"] == "One title"
    assert entries["one"]["thumbnail"] == "https://example.test/one.jpg"
    assert entries["one"]["duration_string"] == "7 min"
    assert entries["one"]["url"] == "https://www.xvideos.com/video.one/title?pl=91000001&plname=sample_list"


def test_favorite_title_from_url_uses_path_after_favorite() -> None:
    assert xvideos.favorite_title_from_url("https://www.xvideos.com/favorite/91000002/_") == "91000002/_"
    assert xvideos.favorite_title_from_url("https://www.xvideos.com/favorite/91000002/sample_list/") == "91000002/sample_list"
    assert xvideos.favorite_title_from_url("https://www.xvideos.com/video.one/title") == ""


def test_playlist_info_from_webpage_fetches_numbered_favorite_pages() -> None:
    fetched: list[str] = []
    first = """
    <div id="video_one" data-id="1" data-eid="one" class="frame-block thumb-block">
      <a href="/video.one/first?pl=91000001&amp;plname=sample_list">
        <img data-src="https://example.test/one.jpg" />
      </a>
      <p class="title"><a title="One"><span class="duration">1 min</span></a></p>
    </div>
    <a href="/favorite/91000001/sample_page/1">2</a>
    <a href="/favorite/91000001/sample_page/2">3</a>
    """
    pages = {
        "https://www.xvideos.com/favorite/91000001/sample_page/1": """
        <div id="video_two" data-id="2" data-eid="two" class="frame-block thumb-block">
          <a href="/video.two/second?pl=91000001&amp;plname=sample_list">
            <img data-src="https://example.test/two.jpg" />
          </a>
          <p class="title"><a title="Two"><span class="duration">2 min</span></a></p>
        </div>
        """,
        "https://www.xvideos.com/favorite/91000001/sample_page/2": """
        <div id="video_three" data-id="3" data-eid="three" class="frame-block thumb-block">
          <a href="/video.three/third?pl=91000001&amp;plname=sample_list">
            <img data-src="https://example.test/three.jpg" />
          </a>
          <p class="title"><a title="Three"><span class="duration">3 min</span></a></p>
        </div>
        """,
    }

    def fake_download(url: str) -> str:
        fetched.append(url)
        return pages[url]

    info = xvideos.playlist_info_from_webpage(
        first,
        FAVORITE_URL,
        download_webpage=fake_download,
        limit=10,
        concurrency=2,
    )

    assert set(fetched) == set(pages)
    assert [entry["id"] for entry in info["entries"]] == ["one", "two", "three"]
    assert info["entries"][1]["url"] == "https://www.xvideos.com/video.two/second?pl=91000001&plname=sample_list"


def test_playlist_info_from_webpage_honors_limit() -> None:
    first = """
    <div id="video_one" data-id="1" data-eid="one" class="frame-block thumb-block">
      <a href="/video.one/first"><img data-src="https://example.test/one.jpg" /></a>
      <p class="title"><a title="One"></a></p>
    </div>
    <a href="/favorite/91000001/sample_page/1">2</a>
    """

    def fake_download(_url: str) -> str:
        return """
        <div id="video_two" data-id="2" data-eid="two" class="frame-block thumb-block">
          <a href="/video.two/second"><img data-src="https://example.test/two.jpg" /></a>
          <p class="title"><a title="Two"></a></p>
        </div>
        """

    info = xvideos.playlist_info_from_webpage(
        first,
        FAVORITE_URL,
        download_webpage=fake_download,
        limit=1,
    )

    assert [entry["id"] for entry in info["entries"]] == ["one"]


def test_next_playlist_page_url_uses_favorite_numbered_link() -> None:
    webpage = """
    <a href="/favorite/91000001/sample_list/">1</a>
    <a href="/favorite/91000001/sample_page/1">2</a>
    """

    assert xvideos.next_playlist_page_url(webpage, FAVORITE_URL, 1) == (
        "https://www.xvideos.com/favorite/91000001/sample_page/1"
    )


def test_next_playlist_page_url_uses_xvideos_next_page_class() -> None:
    webpage = '<a class="no-page next-page" data-id="n" href="/favorite/91000001/sample_page/1">Next</a>'

    assert xvideos.next_playlist_page_url(webpage, FAVORITE_URL, 1) == (
        "https://www.xvideos.com/favorite/91000001/sample_page/1"
    )


def test_numbered_playlist_page_urls_fills_ellipsis_gap_from_last_page() -> None:
    webpage = """
    <a href="/favorite/91000001/sample_page/1">2</a>
    <a href="/favorite/91000001/sample_page/2">3</a>
    <a href="#" class="ellipsis last-ellipsis">...</a>
    <a href="/favorite/91000001/sample_page/4" class="last-page">5</a>
    """

    assert xvideos.numbered_playlist_page_urls(webpage, FAVORITE_URL) == [
        "https://www.xvideos.com/favorite/91000001/sample_page/1",
        "https://www.xvideos.com/favorite/91000001/sample_page/2",
        "https://www.xvideos.com/favorite/91000001/sample_page/3",
        "https://www.xvideos.com/favorite/91000001/sample_page/4",
    ]


def test_xvideos_thumbnail_stays_direct_url() -> None:
    node = media_mapper.node_from_info({
        "webpage_url": "https://www.xvideos.com/video.samplevideoid/sample_video",
        "title": "Risky Cheating",
        "thumbnail": "https://thumb-cdn77.xvideos-cdn.com/6d26f8a2/0/xv_21_t.jpg",
    }, "http://127.0.0.1:18990", ImageProxyMode.KNOWN)
    vod = tvbox.vod_from_client_item(item_from_media_node(node))

    assert vod["vod_pic"] == "https://thumb-cdn77.xvideos-cdn.com/6d26f8a2/0/xv_21_t.jpg"
