from __future__ import annotations

from typing import Any


def compact_dict(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, "", [], {})}
