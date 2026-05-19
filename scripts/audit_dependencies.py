from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def strip_editable_requirements(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    filtered = [
        line
        for line in lines
        if not line.startswith("-e ") and not line.startswith("--editable ")
    ]
    path.write_text("".join(filtered), encoding="utf-8")


def print_process_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit locked Python dependencies with pip-audit via uvx."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root containing pyproject.toml and uv.lock.",
    )
    parser.add_argument(
        "--no-all-extras",
        action="store_true",
        help="Audit only default dependencies instead of all extras.",
    )
    parser.add_argument(
        "pip_audit_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments passed to pip-audit after '--'.",
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    if not (project_root / "pyproject.toml").is_file():
        print(f"pyproject.toml not found under {project_root}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="dashbox-audit-") as temp_dir:
        requirements_path = Path(temp_dir) / "requirements.txt"
        export_args = [
            "uv",
            "export",
            "--locked",
            "--format",
            "requirements-txt",
            "--output-file",
            os.fspath(requirements_path),
        ]
        if not args.no_all_extras:
            export_args.append("--all-extras")

        export_result = run(export_args, cwd=project_root)
        if export_result.returncode != 0:
            print_process_output(export_result)
            return export_result.returncode

        strip_editable_requirements(requirements_path)

        pip_audit_args = args.pip_audit_args
        if pip_audit_args[:1] == ["--"]:
            pip_audit_args = pip_audit_args[1:]

        audit_result = run(
            ["uvx", "pip-audit", "-r", os.fspath(requirements_path), *pip_audit_args],
            cwd=project_root,
        )
        print_process_output(audit_result)
        return audit_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
