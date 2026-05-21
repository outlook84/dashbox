from __future__ import annotations

import dashbox


class FakeMetadata:
    def __init__(self, project_urls: list[str], home_page: str = "") -> None:
        self.project_urls = project_urls
        self.home_page = home_page

    def get_all(self, key: str) -> list[str]:
        return self.project_urls if key == "Project-URL" else []

    def get(self, key: str, default: str = "") -> str:
        return self.home_page if key == "Home-page" else default


def test_project_url_prefers_source_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        dashbox,
        "metadata",
        lambda name: FakeMetadata([
            "Homepage, https://example.test/home",
            "Source, https://example.test/source",
        ]),
    )

    assert dashbox._project_url() == "https://example.test/source"


def test_project_url_falls_back_to_home_page_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        dashbox,
        "metadata",
        lambda name: FakeMetadata([], home_page="https://example.test/home"),
    )

    assert dashbox._project_url() == "https://example.test/home"
