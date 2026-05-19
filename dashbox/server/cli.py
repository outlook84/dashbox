from __future__ import annotations

import argparse
import copy
import logging
import os
from pathlib import Path
from typing import Any

import uvicorn

from ..config import PUBLIC_BASE_URL_ENV, load_config, minimal_config_file_data, write_config_file


DASHBOX_CONFIG_ENV = "DASHBOX_CONFIG"
DASHBOX_DATA_DIR_ENV = "DASHBOX_DATA_DIR"
DASHBOX_HOST_ENV = "DASHBOX_HOST"
DASHBOX_PORT_ENV = "DASHBOX_PORT"
DASHBOX_RELOAD_ENV = "DASHBOX_RELOAD"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="yt-dlp powered TVBox gateway")
    parser.add_argument("-c", "--config", default=None, help=f"Path to JSON config file. Defaults to {DASHBOX_CONFIG_ENV}")
    parser.add_argument("--data-dir", default=None, help=f"Path to Dashbox data directory. Defaults to {DASHBOX_DATA_DIR_ENV}")
    parser.add_argument("--host", default=None, help=f"Listen host. Defaults to {DASHBOX_HOST_ENV} or 0.0.0.0")
    parser.add_argument("--port", default=None, type=int, help=f"Listen port. Defaults to {DASHBOX_PORT_ENV} or 18990")
    parser.add_argument("--public-base-url", default=None, help=f"External base URL. Defaults to {PUBLIC_BASE_URL_ENV}")
    parser.add_argument("--reload", action="store_true", default=None, help=f"Enable uvicorn reload. Defaults to {DASHBOX_RELOAD_ENV}")
    return parser.parse_args()


def config_path_from_env(value: str | None = None) -> str:
    if value is not None:
        return value.strip()
    return os.environ.get(DASHBOX_CONFIG_ENV, "").strip()


def data_dir_from_env(value: str | None = None) -> str:
    if value is not None:
        return value.strip()
    return os.environ.get(DASHBOX_DATA_DIR_ENV, "").strip()


def config_path_from_startup_options(config_path: str | None = None, data_dir: str | None = None) -> str:
    explicit_config_path = config_path_from_env(config_path)
    if explicit_config_path:
        return explicit_config_path
    resolved_data_dir = data_dir_from_env(data_dir)
    if resolved_data_dir:
        return str(Path(resolved_data_dir) / "config.json")
    return ""


def ensure_data_dir_config(config_path: str, data_dir: str) -> None:
    if not data_dir or not config_path:
        return
    target = Path(config_path)
    if target.exists():
        return
    write_config_file(target, minimal_config_file_data())


def host_from_env(value: str | None = None) -> str:
    if value is not None:
        return value.strip() or "0.0.0.0"
    value = os.environ.get(DASHBOX_HOST_ENV, "").strip()
    return value or "0.0.0.0"


def port_from_env(value: int | None = None) -> int:
    if value is not None:
        validate_port(value, "--port")
        return value
    return parse_port_value(os.environ.get(DASHBOX_PORT_ENV, "").strip(), DASHBOX_PORT_ENV)


def parse_port_value(value: str, path: str) -> int:
    if not value:
        return 18990
    try:
        port = int(value)
    except ValueError:
        raise ValueError(f"unsupported {path}: {value}. Expected integer") from None
    validate_port(port, path)
    return port


def validate_port(port: int, path: str) -> None:
    if port < 1 or port > 65535:
        raise ValueError(f"unsupported {path}: {port}. Expected integer between 1 and 65535")


def reload_from_env(value: bool | None = None) -> bool:
    if value is not None:
        return value
    value = os.environ.get(DASHBOX_RELOAD_ENV, "").strip().lower()
    if not value:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"unsupported {DASHBOX_RELOAD_ENV}: {value}. Expected boolean")


def apply_public_base_url_arg(value: str | None) -> None:
    if value is not None:
        os.environ[PUBLIC_BASE_URL_ENV] = value.strip()


def uvicorn_log_config(log_level: str = "info") -> dict[str, Any]:
    log_config = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    level = str(log_level).upper()
    log_config["loggers"]["dashbox"] = {
        "handlers": ["default"],
        "level": level,
        "propagate": False,
    }
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger_config = log_config["loggers"].setdefault(logger_name, {})
        logger_config["level"] = level
    return log_config


def apply_runtime_log_level(log_level: str) -> None:
    level = str(log_level).upper()
    for logger_name in ("dashbox", "uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).setLevel(level)


def main() -> None:
    from .app import create_app

    args = parse_args()
    apply_public_base_url_arg(args.public_base_url)
    data_dir = data_dir_from_env(args.data_dir)
    explicit_config_path = config_path_from_env(args.config)
    config_path = config_path_from_startup_options(args.config, args.data_dir)
    if not explicit_config_path:
        ensure_data_dir_config(config_path, data_dir)
    config = load_config(config_path)
    app = create_app(config, config_path=config_path or None, data_dir=data_dir or None)
    uvicorn.run(
        app,
        host=host_from_env(args.host),
        port=port_from_env(args.port),
        reload=reload_from_env(args.reload),
        log_config=uvicorn_log_config(config.log_level),
        log_level=config.log_level,
    )
