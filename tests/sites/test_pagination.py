from dashbox.sites.pagination import limit_page_urls, with_page_query_param


def test_limit_page_urls_applies_configured_item_limit() -> None:
    cases = (
        (
            ["page2", "page3", "page4"],
            {"current_count": 27, "limit": 60, "items_per_page": 27},
            ["page2", "page3"],
        ),
        (
            ["page2", "page3"],
            {"current_count": 27, "limit": 0, "items_per_page": 27},
            ["page2", "page3"],
        ),
        (
            ["page2"],
            {"current_count": 3, "limit": 3, "items_per_page": 3},
            [],
        ),
    )

    for page_urls, kwargs, expected in cases:
        assert limit_page_urls(page_urls, **kwargs) == expected


def test_with_page_query_param_adds_or_replaces_page() -> None:
    assert with_page_query_param("https://example.test/list?sort=hot&page=1#top", 3) == (
        "https://example.test/list?sort=hot&page=3#top"
    )
    assert with_page_query_param("https://example.test/list", 2) == "https://example.test/list?page=2"
