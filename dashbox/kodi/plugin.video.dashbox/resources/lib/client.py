from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API_VERSION = "2"


def addon_version() -> str:
    try:
        import xbmcaddon

        return str(xbmcaddon.Addon().getAddonInfo("version") or "")
    except Exception:
        return ""


def kodi_locale() -> str:
    try:
        import xbmc

        value = str(xbmc.getLanguage(xbmc.ISO_639_1, region=True) or "")
    except Exception:
        return ""
    normalized = value.replace("_", "-")
    if normalized.lower().startswith("zh"):
        return "zh-CN"
    if normalized.lower().startswith("en"):
        return "en-US"
    return normalized


class DashboxError(Exception):
    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class DashboxClient:
    def __init__(self, gateway: str, sub_id: str, access_token: str = "") -> None:
        self.gateway = gateway.rstrip("/")
        self.sub_id = sub_id.strip("/")
        self.access_token = access_token

    def auth(self, code: str = "") -> dict:
        return self.request("POST", "auth", {"client": "kodi", "code": code}, auth_required=False)

    def home(self) -> dict:
        return self.request("GET", "home")

    def items(self, item_id: str, refresh: bool = False) -> dict:
        return self.request("GET", "items", query={"id": item_id, "refresh": "true" if refresh else "false"})

    def detail(self, item_id: str) -> dict:
        return self.request("GET", "detail", query={"id": item_id})

    def search(self, key: str) -> dict:
        return self.request("GET", "search", query={"key": key})

    def play(self, item_id: str, playback: dict | None = None) -> dict:
        return self.request("POST", "play", {"id": item_id, "playback": playback or {}})

    def request(self, method: str, endpoint: str, body: dict | None = None, *, query: dict | None = None, auth_required: bool = True) -> dict:
        url = "{}/api/v1/subs/{}/{}".format(self.gateway, self.sub_id, endpoint.strip("/"))
        if query:
            url += "?" + urlencode(query)
        data = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
        headers = {
            "Accept": "application/json",
            "X-Dashbox-Kodi-Addon-Version": addon_version(),
            "X-Dashbox-Kodi-Api-Version": API_VERSION,
        }
        locale = kodi_locale()
        if locale:
            headers["X-Dashbox-Locale"] = locale
        if data is not None:
            headers["Content-Type"] = "application/json"
        if auth_required and self.access_token:
            headers["X-Access-Token"] = self.access_token
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=60) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            raise DashboxError(str(exc), status_code=exc.code) from exc
        except Exception as exc:
            raise DashboxError(str(exc)) from exc
        try:
            value = json.loads(payload)
        except ValueError as exc:
            raise DashboxError("invalid JSON response") from exc
        if isinstance(value, dict) and value.get("error"):
            raise DashboxError(str(value["error"]))
        if not isinstance(value, dict):
            raise DashboxError("unexpected response")
        return value
