from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit


MAX_EXCEPTION_REASON_LENGTH = 300
_PATH_TERMINATORS = set(" \t\r\n\"'<>|()[]{}")
_PATH_TRAILING_CHARS = ".,;:"


def exception_reason(exc: BaseException, *, max_length: int = MAX_EXCEPTION_REASON_LENGTH) -> str:
    reason = str(exc).strip() or exc.__class__.__name__
    lines = [
        line.strip()
        for line in reason.splitlines()
        if line.strip() and not _is_traceback_line(line.strip())
    ]
    reason = " | ".join(lines) if lines else exc.__class__.__name__
    reason = _redact_absolute_paths(reason)
    reason = " ".join(reason.split())
    if len(reason) > max_length:
        reason = reason[: max_length - 3].rstrip() + "..."
    return reason


def _is_traceback_line(line: str) -> bool:
    return (
        line == "Traceback (most recent call last):"
        or line.startswith("File ")
        or line.startswith("File \"")
    )


def _redact_absolute_paths(text: str) -> str:
    parts: list[str] = []
    index = 0
    while index < len(text):
        path_range = _local_path_range_at(text, index)
        if path_range is None:
            parts.append(text[index])
            index += 1
            continue
        start, end = path_range
        parts.append(text[index:start])
        parts.append("<path>")
        index = end
    return "".join(parts)


def _local_path_range_at(text: str, index: int) -> tuple[int, int] | None:
    if text[index : index + len("file://")].lower() == "file://":
        end = _path_end(text, index)
        candidate = text[index:end]
        if _is_absolute_local_path(candidate):
            return index, end
        return None

    if _is_windows_path_start(text, index):
        end = _path_end(text, index)
        return index, end

    if _is_posix_path_start(text, index):
        end = _path_end(text, index)
        candidate = text[index:end]
        if PurePosixPath(candidate).is_absolute() and candidate.count("/") >= 2:
            return index, end
    return None


def _path_end(text: str, start: int) -> int:
    end = start
    while end < len(text) and text[end] not in _PATH_TERMINATORS:
        end += 1
    while end > start and text[end - 1] in _PATH_TRAILING_CHARS:
        end -= 1
    return end


def _is_windows_path_start(text: str, index: int) -> bool:
    if index + 2 >= len(text):
        return False
    if index > 0 and text[index - 1].isalnum():
        return False
    candidate = text[index : index + 3]
    return (
        candidate[0].isalpha()
        and candidate[1] == ":"
        and candidate[2] in {"/", "\\"}
        and PureWindowsPath(candidate).is_absolute()
    )


def _is_posix_path_start(text: str, index: int) -> bool:
    if text[index] != "/":
        return False
    if index > 0 and (text[index - 1].isalnum() or text[index - 1] in {":", "/"}):
        return False
    if index + 1 >= len(text) or text[index + 1] in {"/", " "}:
        return False
    return True


def _is_absolute_local_path(value: str) -> bool:
    if value.lower().startswith("file://"):
        parsed = urlsplit(value)
        return bool(parsed.path) or bool(parsed.netloc)
    if "://" in value:
        return False
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()
