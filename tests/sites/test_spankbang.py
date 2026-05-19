from dashbox.config import DEFAULT_USER_AGENT
from dashbox.core import image_policy
from dashbox.sites import spankbang


PLAYLIST_URL = "https://spankbang.com/ch0et/playlist/sample+collection"


def test_playlist_url_accepts_spankbang_subdomains() -> None:
    assert spankbang.is_playlist_url("https://m.spankbang.com/ug0k/playlist/big+ass+titties")
    assert spankbang.is_playlist_url("https://foo.spankbang.com/ug0k/playlist/big+ass+titties")
    assert not spankbang.is_playlist_url("https://notspankbang.com/ug0k/playlist/big+ass+titties")


def test_playlist_video_url_is_not_playlist_directory() -> None:
    url = "https://spankbang.com/pl001-item001/playlist/sample+playlist?dashbox_index=21"

    assert spankbang.is_playlist_video_url(url)
    assert not spankbang.is_playlist_url(url)
    assert spankbang.config_node_kind(url) is None


def test_playlist_entries_from_webpage_extracts_thumbnail_title_and_duration() -> None:
    webpage = """
    <div data-testid="video-item" data-id="15195379">
      <a href="/ch0et-qa704y/playlist/sample+collection">
        <picture>
          <img
            src="https://tbi.sb-cd.com/t/15195379/43/e4/w:300/t6-enh/sample-video-thumb.jpg"
            alt="Hot Nurse Layla Jenner Pussy Pulvarized - HardX"
          />
        </picture>
        <div data-testid="video-item-length">
          12m
        </div>
      </a>
    </div>
    """

    entries = spankbang.playlist_entries_from_webpage(webpage, PLAYLIST_URL)

    assert entries["qa704y"] == {
        "webpage_url": "https://spankbang.com/ch0et-qa704y/playlist/sample+collection",
        "title": "Hot Nurse Layla Jenner Pussy Pulvarized - HardX",
        "thumbnail": "https://tbi.sb-cd.com/t/15195379/43/e4/w:300/t6-enh/sample-video-thumb.jpg",
        "duration_string": "12m",
    }
    assert entries["15195379"] == entries["qa704y"]
    assert entries["/ch0et-qa704y/playlist/sample+collection"] == entries["qa704y"]


def test_playlist_entries_from_webpage_handles_reordered_spankbang_attrs() -> None:
    webpage = """
    <div class="item" data-id="15195379" data-testid="video-item">
      <a data-extra="x" href="/ch0et-qa704y/playlist/sample+collection">
        <div data-testid="video-item-length">
          <span>12m</span>
        </div>
        <img alt="Hot Nurse" data-src="https://example.test/fallback.jpg" src="https://example.test/one.jpg">
      </a>
    </div>
    """

    entries = spankbang.playlist_entries_from_webpage(webpage, PLAYLIST_URL)

    assert entries["qa704y"]["title"] == "Hot Nurse"
    assert entries["qa704y"]["thumbnail"] == "https://example.test/one.jpg"
    assert entries["qa704y"]["duration_string"] == "12m"


def test_enrich_flat_playlist_updates_matching_stub_entries() -> None:
    info = {
        "extractor_key": "SpankBangPlaylist",
        "webpage_url": PLAYLIST_URL,
        "entries": [
            {
                "id": "qa704y",
                "_type": "url",
                "url": "https://spankbang.com/ch0et-qa704y/playlist/sample+collection",
            },
        ],
    }
    webpage = """
    <div data-testid="video-item" data-id="15195379">
      <a href="/ch0et-qa704y/playlist/sample+collection">
        <img
          data-src="https://tbi.sb-cd.com/t/15195379/43/e4/w:300/t6-enh/sample-video-thumb.jpg"
          alt="Hot Nurse Layla Jenner Pussy Pulvarized - HardX"
        />
        <div data-testid="video-item-length">12m</div>
      </a>
    </div>
    """

    spankbang.enrich_flat_playlist(info, webpage)

    assert info["entries"][0]["title"] == "Hot Nurse Layla Jenner Pussy Pulvarized - HardX"
    assert info["entries"][0]["thumbnail"].startswith("https://tbi.sb-cd.com/t/15195379/")
    assert info["entries"][0]["duration_string"] == "12m"
    assert info["entries"][0]["webpage_url"] == "https://spankbang.com/ch0et-qa704y/playlist/sample+collection"


def test_enrich_flat_playlist_removes_duplicate_stub_entries() -> None:
    info = {
        "extractor_key": "SpankBangPlaylist",
        "webpage_url": PLAYLIST_URL,
        "entries": [
            {"id": "qa704y", "url": "https://spankbang.com/ch0et-qa704y/playlist/sample+collection"},
            {"id": "qa704y", "url": "https://spankbang.com/ch0et-qa704y/playlist/sample+collection"},
            {"id": "qa6zz2", "url": "https://spankbang.com/ch0et-qa6zz2/playlist/sample+collection"},
        ],
    }
    webpage = """
    <div data-testid="video-item" data-id="15195379">
      <a href="/ch0et-qa704y/playlist/sample+collection">
        <img src="https://tbi.sb-cd.com/t/15195379/43/e4/w:300/t6-enh/one.jpg" alt="One" />
      </a>
    </div>
    <div data-testid="video-item" data-id="16090629">
      <a href="/ch0et-qa6zz2/playlist/sample+collection">
        <img src="https://tbi.sb-cd.com/t/16090629/67/9c/w:300/t6-enh/two.jpg" alt="Two" />
      </a>
    </div>
    """

    spankbang.enrich_flat_playlist(info, webpage)

    assert [entry["id"] for entry in info["entries"]] == ["qa704y", "qa6zz2"]


def test_enrich_flat_playlist_does_not_overwrite_existing_metadata() -> None:
    info = {
        "extractor_key": "SpankBangPlaylist",
        "webpage_url": PLAYLIST_URL,
        "entries": [
            {
                "id": "qa704y",
                "url": "https://spankbang.com/ch0et-qa704y/playlist/sample+collection",
                "title": "Existing title",
                "thumbnail": "https://example.test/existing.jpg",
            },
        ],
    }
    webpage = """
    <div data-testid="video-item" data-id="15195379">
      <a href="/ch0et-qa704y/playlist/sample+collection">
        <img src="https://tbi.sb-cd.com/t/15195379/43/e4/w:300/t6-enh/sample-video-thumb.jpg" alt="New title" />
      </a>
    </div>
    """

    spankbang.enrich_flat_playlist(info, webpage)

    assert info["entries"][0]["title"] == "Existing title"
    assert info["entries"][0]["thumbnail"] == "https://example.test/existing.jpg"


def test_append_flat_playlist_entries_adds_missing_page_items() -> None:
    info = {
        "extractor_key": "SpankBangPlaylist",
        "webpage_url": PLAYLIST_URL,
        "entries": [
            {
                "id": "qa704y",
                "url": "https://spankbang.com/ch0et-qa704y/playlist/sample+collection",
            },
        ],
    }
    webpage = """
    <div data-testid="video-item" data-id="15195379">
      <a href="/ch0et-qa704y/playlist/sample+collection">
        <img src="https://example.test/one.jpg" alt="One" />
      </a>
    </div>
    <div data-testid="video-item" data-id="16090629">
      <a href="/ch0et-qa6zz2/playlist/sample+collection">
        <img src="https://example.test/two.jpg" alt="Two" />
        <div data-testid="video-item-length">8m</div>
      </a>
    </div>
    """

    added = spankbang.append_flat_playlist_entries(info, webpage, PLAYLIST_URL)

    assert added == 1
    assert [entry["id"] for entry in info["entries"]] == ["qa704y", "qa6zz2"]
    assert info["entries"][1]["ie_key"] == "SpankBang"
    assert info["entries"][1]["title"] == "Two"
    assert info["entries"][1]["duration_string"] == "8m"


def test_append_flat_playlist_entries_honors_limit() -> None:
    info = {
        "extractor_key": "SpankBangPlaylist",
        "webpage_url": PLAYLIST_URL,
        "entries": [
            {"id": "qa704y", "url": "https://spankbang.com/ch0et-qa704y/playlist/sample+collection"},
        ],
    }
    webpage = """
    <div data-testid="video-item" data-id="16090629">
      <a href="/ch0et-qa6zz2/playlist/sample+collection">
        <img src="https://example.test/two.jpg" alt="Two" />
      </a>
    </div>
    <div data-testid="video-item" data-id="16090630">
      <a href="/ch0et-qa6zz3/playlist/sample+collection">
        <img src="https://example.test/three.jpg" alt="Three" />
      </a>
    </div>
    """

    added = spankbang.append_flat_playlist_entries(info, webpage, PLAYLIST_URL, limit=2)

    assert added == 1
    assert [entry["id"] for entry in info["entries"]] == ["qa704y", "qa6zz2"]


def test_playlist_info_from_webpage_builds_public_playlist_entries() -> None:
    webpage = """
    <title>Layla Jenner Playlist</title>
    <div data-testid="video-item" data-id="15195379">
      <a href="/ch0et-qa704y/playlist/sample+collection">
        <img src="https://example.test/one.jpg" alt="One" />
        <div data-testid="video-item-length">12m</div>
      </a>
    </div>
    """

    info = spankbang.playlist_info_from_webpage(webpage, PLAYLIST_URL, limit=10)

    assert info["extractor_key"] == "SpankBangPlaylist"
    assert info["title"] == "Layla Jenner Playlist"
    assert info["entries"] == [
        {
            "_type": "url",
            "ie_key": "SpankBang",
            "id": "qa704y",
            "url": "https://spankbang.com/ch0et-qa704y/playlist/sample+collection",
            "webpage_url": "https://spankbang.com/ch0et-qa704y/playlist/sample+collection",
            "title": "One",
            "thumbnail": "https://example.test/one.jpg",
            "duration_string": "12m",
        },
    ]


def test_playlist_info_fetches_numbered_pages_with_limited_concurrency() -> None:
    fetched: list[str] = []
    first = """
    <div data-testid="video-item" data-id="1">
      <a href="/ch0et-qa704y/playlist/sample+collection"><img src="https://example.test/one.jpg" alt="One" /></a>
    </div>
    <a href="/ch0et/playlist/sample+collection/2/">2</a>
    <a href="/ch0et/playlist/sample+collection/3/">3</a>
    """
    pages = {
        "https://spankbang.com/ch0et/playlist/sample+collection/2/": """
        <div data-testid="video-item" data-id="2">
          <a href="/ch0et-qa6zz2/playlist/sample+collection"><img src="https://example.test/two.jpg" alt="Two" /></a>
        </div>
        """,
        "https://spankbang.com/ch0et/playlist/sample+collection/3/": """
        <div data-testid="video-item" data-id="3">
          <a href="/ch0et-qa6zz3/playlist/sample+collection"><img src="https://example.test/three.jpg" alt="Three" /></a>
        </div>
        """,
    }

    def fake_download(url: str) -> str:
        fetched.append(url)
        return pages[url]

    info = spankbang.playlist_info_from_webpage(
        first,
        PLAYLIST_URL,
        download_webpage=fake_download,
        limit=2,
        concurrency=1,
    )

    assert fetched == ["https://spankbang.com/ch0et/playlist/sample+collection/2/"]
    assert [entry["id"] for entry in info["entries"]] == ["qa704y", "qa6zz2"]


def test_next_playlist_page_url_prefers_explicit_next_link() -> None:
    webpage = '<a href="/ch0et/playlist/sample+collection?page=2" data-id="n" rel="next">Next</a>'

    assert spankbang.next_playlist_page_url(webpage, PLAYLIST_URL, 1) == (
        "https://spankbang.com/ch0et/playlist/sample+collection?page=2"
    )


def test_next_playlist_page_url_uses_numbered_playlist_link() -> None:
    webpage = """
    <a href="/ch0et/playlist/sample+collection/">1</a>
    <a href="/ch0et/playlist/sample+collection/2/">2</a>
    <a href="/ch0et/playlist/sample+collection/3/">3</a>
    """

    assert spankbang.next_playlist_page_url(webpage, PLAYLIST_URL, 1) == (
        "https://spankbang.com/ch0et/playlist/sample+collection/2/"
    )


def test_numbered_playlist_page_urls_returns_sorted_unique_pages() -> None:
    webpage = """
    <a href="/ch0et/playlist/sample+collection/3/">3</a>
    <a href="/ch0et/playlist/sample+collection/2/">2</a>
    <a href="/ch0et/playlist/sample+collection/2/">2</a>
    """

    assert spankbang.numbered_playlist_page_urls(webpage, PLAYLIST_URL) == [
        "https://spankbang.com/ch0et/playlist/sample+collection/2/",
        "https://spankbang.com/ch0et/playlist/sample+collection/3/",
    ]


def test_enrich_flat_playlist_pages_fetches_numbered_pages() -> None:
    fetched: list[str] = []
    first = """
    <div data-testid="video-item" data-id="1">
      <a href="/ch0et-qa704y/playlist/sample+collection">
        <img src="https://example.test/one.jpg" alt="One" />
      </a>
    </div>
    <a href="/ch0et/playlist/sample+collection/2/">2</a>
    <a href="/ch0et/playlist/sample+collection/3/">3</a>
    """
    pages = {
        "https://spankbang.com/ch0et/playlist/sample+collection/2/": """
        <div data-testid="video-item" data-id="2">
          <a href="/ch0et-qa6zz2/playlist/sample+collection">
            <img src="https://example.test/two.jpg" alt="Two" />
          </a>
        </div>
        """,
        "https://spankbang.com/ch0et/playlist/sample+collection/3/": """
        <div data-testid="video-item" data-id="3">
          <a href="/ch0et-qa6zz3/playlist/sample+collection">
            <img src="https://example.test/three.jpg" alt="Three" />
          </a>
        </div>
        """,
    }

    def fake_download(url: str) -> str:
        fetched.append(url)
        return pages[url]

    info = {
        "extractor_key": "SpankBangPlaylist",
        "webpage_url": PLAYLIST_URL,
        "entries": [
            {"id": "qa704y", "url": "https://spankbang.com/ch0et-qa704y/playlist/sample+collection"},
        ],
    }

    spankbang.enrich_flat_playlist_pages(
        info,
        first,
        PLAYLIST_URL,
        download_webpage=fake_download,
        limit=10,
        concurrency=2,
    )

    assert set(fetched) == set(pages)
    assert [entry["id"] for entry in info["entries"]] == ["qa704y", "qa6zz2", "qa6zz3"]


def test_enrich_flat_playlist_pages_limits_numbered_page_fetches_by_page_size() -> None:
    fetched: list[str] = []
    first = """
    <div data-testid="video-item" data-id="1">
      <a href="/ch0et-qa704y/playlist/sample+collection"><img src="https://example.test/one.jpg" alt="One" /></a>
    </div>
    <div data-testid="video-item" data-id="2">
      <a href="/ch0et-qa6zz2/playlist/sample+collection"><img src="https://example.test/two.jpg" alt="Two" /></a>
    </div>
    <a href="/ch0et/playlist/sample+collection/2/">2</a>
    <a href="/ch0et/playlist/sample+collection/3/">3</a>
    """
    pages = {
        "https://spankbang.com/ch0et/playlist/sample+collection/2/": """
        <div data-testid="video-item" data-id="3">
          <a href="/ch0et-qa6zz3/playlist/sample+collection"><img src="https://example.test/three.jpg" alt="Three" /></a>
        </div>
        <div data-testid="video-item" data-id="4">
          <a href="/ch0et-qa6zz4/playlist/sample+collection"><img src="https://example.test/four.jpg" alt="Four" /></a>
        </div>
        """,
        "https://spankbang.com/ch0et/playlist/sample+collection/3/": """
        <div data-testid="video-item" data-id="5">
          <a href="/ch0et-qa6zz5/playlist/sample+collection"><img src="https://example.test/five.jpg" alt="Five" /></a>
        </div>
        """,
    }

    def fake_download(url: str) -> str:
        fetched.append(url)
        return pages[url]

    info = {
        "extractor_key": "SpankBangPlaylist",
        "webpage_url": PLAYLIST_URL,
        "entries": [],
    }

    spankbang.enrich_flat_playlist_pages(
        info,
        first,
        PLAYLIST_URL,
        download_webpage=fake_download,
        limit=3,
        concurrency=2,
    )

    assert fetched == ["https://spankbang.com/ch0et/playlist/sample+collection/2/"]
    assert [entry["id"] for entry in info["entries"]] == ["qa704y", "qa6zz2", "qa6zz3"]


def test_next_playlist_page_url_falls_back_to_page_query() -> None:
    assert spankbang.next_playlist_page_url("", PLAYLIST_URL, 1) == (
        "https://spankbang.com/ch0et/playlist/sample+collection?page=2"
    )


def test_thumbnail_url_adds_headers_for_spankbang_cdn_urls() -> None:
    url = "https://tbi.sb-cd.com/t/15195379/43/e4/w:300/t6-enh/sample-video-thumb.jpg"

    assert image_policy.thumbnail_url(url) == f"{url}@Referer=https://spankbang.com/@User-Agent={DEFAULT_USER_AGENT}"
    assert image_policy.proxied_thumbnail_url(url, "http://127.0.0.1:18990") == (
        "http://127.0.0.1:18990/image?"
        "url=https%3A%2F%2Ftbi.sb-cd.com%2Ft%2F15195379%2F43%2Fe4%2Fw%3A300%2Ft6-enh%2Fsample-video-thumb.jpg"
    )
    assert image_policy.proxied_thumbnail_url("https://example.test/image.jpg", "http://127.0.0.1:18990") == "https://example.test/image.jpg"


def test_thumbnail_url_adds_headers_for_pornhub_cdn_urls() -> None:
    url = "https://ei.phncdn.com/videos/202306/30/434565631/original/(m=qY699PYbeaAaGwObaaaa)(mh=6EqNO9Vz8OLTNXwR)0.jpg"

    assert image_policy.thumbnail_url(url) == f"{url}@Referer=https://www.pornhub.com/@User-Agent={DEFAULT_USER_AGENT}"
    assert image_policy.proxied_thumbnail_url(url, "http://127.0.0.1:18990").startswith(
        "http://127.0.0.1:18990/image?url=https%3A%2F%2Fei.phncdn.com%2Fvideos%2F"
    )
    assert image_policy.referer_for_image_url(url) == "https://www.pornhub.com/"


def test_proxyable_thumbnail_url_uses_https_host_suffix_matching() -> None:
    assert image_policy.is_proxyable_thumbnail_url("https://foo.sb-cd.com/a.jpg")
    assert image_policy.is_proxyable_thumbnail_url("https://foo.bar.phncdn.com/a.jpg")
    assert not image_policy.is_proxyable_thumbnail_url("http://foo.phncdn.com/a.jpg")
    assert not image_policy.is_proxyable_thumbnail_url("https://foo.notphncdn.com/a.jpg")
