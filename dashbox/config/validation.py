from __future__ import annotations


YTDLP_SEARCH_PREFIXES = frozenset(
    {
        "bilisearch",
        "gvsearch",
        "netsearch",
        "nicosearch",
        "nicosearchdate",
        "prxseries",
        "prxstories",
        "rkfnsearch",
        "scsearch",
        "ytsearch",
        "yvsearch",
    }
)
SUPPORTED_BROWSER_KEYRINGS = {"BASICTEXT", "GNOMEKEYRING", "KWALLET", "KWALLET5", "KWALLET6"}


def validate_ytdlp_search_prefix(value: str) -> str:
    prefix = value.strip().lower().removesuffix(":")
    if prefix not in YTDLP_SEARCH_PREFIXES:
        supported = ", ".join(sorted(YTDLP_SEARCH_PREFIXES))
        raise ValueError(f"unsupported ytdlp_search_prefix: {value}. Supported: {supported}")
    return prefix


def is_ytdlp_search_prefix(prefix: str) -> bool:
    return ytdlp_search_prefix_base(prefix) in YTDLP_SEARCH_PREFIXES


def ytdlp_search_prefix_base(prefix: str) -> str:
    head = prefix.strip().lower().removesuffix(":")
    if head.endswith("all"):
        return head[:-3]
    return head.rstrip("0123456789")


def parse_cookies_from_browser(value: str) -> tuple[str, str | None, str | None, str | None]:
    raw = value.strip()
    head, container_sep, container = raw.partition("::")
    container = container.strip() if container_sep else None
    browser_spec, profile_sep, profile = head.partition(":")
    profile = profile.strip() if profile_sep else None
    browser_name, keyring_sep, keyring = browser_spec.partition("+")
    keyring = keyring.strip() if keyring_sep else None
    browser_name = browser_name.strip().lower()
    if (
        not browser_name
        or (keyring_sep and not keyring)
        or (profile_sep and not profile)
        or (container_sep and not container)
    ):
        raise ValueError(f"invalid cookies_from_browser value: {value}")
    if keyring is not None:
        keyring = keyring.upper()
        if keyring not in SUPPORTED_BROWSER_KEYRINGS:
            supported = ", ".join(sorted(SUPPORTED_BROWSER_KEYRINGS))
            raise ValueError(f"unsupported keyring specified for cookies_from_browser: {keyring}. Supported: {supported}")
    return browser_name, profile, keyring, container
