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


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def release_tag(version: str) -> str:
    return f"v{version}"


def tag_exists(tag: str) -> bool:
    result = subprocess.run(
        ["git", "tag", "--list", tag],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return tag in result.stdout.splitlines()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-ytdlp-version", required=True)
    parser.add_argument("--updated-ytdlp-version", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    current_version = project_version()
    package_base = parse_project_version(current_version).group("release")
    current_release_tag = release_tag(current_version)
    has_current_release = tag_exists(current_release_tag)
    should_release = args.current_ytdlp_version != args.updated_ytdlp_version or not has_current_release

    write_output("package_base", package_base)
    write_output("ref_base", package_base if has_current_release else "")
    write_output("should_release", "true" if should_release else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
