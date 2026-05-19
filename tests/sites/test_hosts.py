from dashbox.sites.hosts import first_query_value, url_query_value, with_query_param


def test_first_query_value_returns_first_value_or_empty() -> None:
    assert first_query_value({"q": ["one", "two"]}, "q") == "one"
    assert first_query_value({}, "q") == ""


def test_url_query_value_reads_first_value_from_url() -> None:
    assert url_query_value("https://example.test/watch?v=abc&v=def", "v") == "abc"
    assert url_query_value("https://example.test/watch", "v") == ""


def test_with_query_param_adds_or_replaces_query_value() -> None:
    assert with_query_param("https://example.test/watch?v=old&x=1#frag", "v", "new") == (
        "https://example.test/watch?v=new&x=1#frag"
    )
    assert with_query_param("https://example.test/watch", "page", "2") == "https://example.test/watch?page=2"
