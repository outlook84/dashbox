from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def project_version() -> str:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def parse_project_version(version: str) -> re.Match[str]:
    match = re.fullmatch(r"(?P<release>\d+(?:\.\d+)*)(?:\.post(?P<post>\d+))?", version)
    if match is None:
        raise RuntimeError(f"Unsupported project version for ytdlp release: {version}")
    return match


def tag_safe(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "-", value).strip(".-")


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def latest_release_tag(ytdlp_version: str) -> str:
    result = subprocess.run(
        ["git", "tag", "--list", f"v*.ytdlp.{tag_safe(ytdlp_version)}", "--sort=-v:refname"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.splitlines()[0] if result.stdout else ""


def release_base_from_tag(tag: str) -> str:
    if not tag:
        return ""
    return tag.removeprefix("v").split(".ytdlp.", 1)[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-ytdlp-version", required=True)
    parser.add_argument("--updated-ytdlp-version", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_base = parse_project_version(project_version()).group("release")
    ref_base = release_base_from_tag(latest_release_tag(args.updated_ytdlp_version))
    should_release = args.current_ytdlp_version != args.updated_ytdlp_version or package_base != ref_base

    write_output("package_base", package_base)
    write_output("ref_base", ref_base)
    write_output("should_release", "true" if should_release else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
