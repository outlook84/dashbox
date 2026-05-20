from __future__ import annotations

import os
import re
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
LOCK = PROJECT_ROOT / "uv.lock"


def project_version() -> str:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def project_dependencies() -> list[str]:
    with PYPROJECT.open("rb") as handle:
        dependencies = tomllib.load(handle)["project"].get("dependencies", [])
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        raise RuntimeError("project.dependencies must be a list of strings")
    return dependencies


def locked_ytdlp_version() -> str:
    with LOCK.open("rb") as handle:
        data = tomllib.load(handle)
    for package in data["package"]:
        if package["name"] == "yt-dlp":
            return package["version"]
    raise RuntimeError("yt-dlp is not present in uv.lock")


def parse_project_version(version: str) -> re.Match[str]:
    match = re.fullmatch(r"(?P<release>\d+(?:\.\d+)*)(?:\.post(?P<post>\d+))?", version)
    if match is None:
        raise RuntimeError(f"Unsupported project version for ytdlp release: {version}")
    return match


def next_post_version(version: str) -> str:
    match = parse_project_version(version)
    stamp = os.environ.get("YTDLP_RELEASE_STAMP")
    if stamp is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    post = int(stamp)
    current_post = match.group("post")
    if current_post is not None and post <= int(current_post):
        post = int(current_post) + 1
    return f"{match.group('release')}.post{post}"


def ytdlp_dependency() -> str:
    matches = []
    for dependency in project_dependencies():
        try:
            requirement = Requirement(dependency)
        except InvalidRequirement as exc:
            raise RuntimeError(f"Invalid project dependency: {dependency}") from exc
        if canonicalize_name(requirement.name) == "yt-dlp":
            matches.append(dependency)
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one yt-dlp dependency, found {len(matches)}")
    return matches[0]


def update_ytdlp_lower_bound(dependency: str, ytdlp_version: str) -> str:
    updated, count = re.subn(r"(>=\s*)[^,\s;]+", rf"\g<1>{ytdlp_version}", dependency, count=1)
    if count != 1:
        raise RuntimeError(f"Unable to update yt-dlp dependency lower bound: {dependency}")
    return updated


def project_table_bounds(lines: list[str]) -> tuple[int, int]:
    start = next((index for index, line in enumerate(lines) if line.strip() == "[project]"), None)
    if start is None:
        raise RuntimeError("Unable to find [project] table")
    end = next(
        (index for index in range(start + 1, len(lines)) if re.fullmatch(r"\s*\[[^\]]+\]\s*", lines[index])),
        len(lines),
    )
    return start, end


def replace_project_version(lines: list[str], new_version: str) -> None:
    start, end = project_table_bounds(lines)
    pattern = re.compile(r'^(\s*version\s*=\s*)"[^"]+"(\s*)$')
    matches = [index for index in range(start + 1, end) if pattern.fullmatch(lines[index])]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one project version line, found {len(matches)}")
    index = matches[0]
    lines[index] = pattern.sub(rf'\g<1>"{new_version}"\2', lines[index])


def replace_project_dependency(lines: list[str], old_dependency: str, new_dependency: str) -> None:
    start, end = project_table_bounds(lines)
    pattern = re.compile(rf'^(\s*)"{re.escape(old_dependency)}"(,?\s*)$')
    matches = [index for index in range(start + 1, end) if pattern.fullmatch(lines[index])]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one yt-dlp dependency line, found {len(matches)}")
    index = matches[0]
    lines[index] = pattern.sub(rf'\g<1>"{new_dependency}"\2', lines[index])


def update_pyproject(new_version: str, ytdlp_version: str) -> None:
    old_dependency = ytdlp_dependency()
    new_dependency = update_ytdlp_lower_bound(old_dependency, ytdlp_version)
    lines = PYPROJECT.read_text(encoding="utf-8").splitlines()
    replace_project_version(lines, new_version)
    replace_project_dependency(lines, old_dependency, new_dependency)
    PYPROJECT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def main() -> int:
    current_version = project_version()
    ytdlp_version = locked_ytdlp_version()
    base_version = parse_project_version(current_version).group("release")
    new_version = next_post_version(current_version)
    release_tag = f"v{new_version}"

    update_pyproject(new_version, ytdlp_version)

    write_output("version", new_version)
    write_output("base_version", base_version)
    write_output("tag", release_tag)
    write_output("ytdlp_version", ytdlp_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
