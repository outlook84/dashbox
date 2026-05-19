# Installation

Dashbox requires Python 3.11 or newer. Source development also requires Node.js
22.13 or newer and `pnpm` 10.33.4.

Always start Dashbox with an explicit `--public-base-url` set to the full URL
that clients use to reach it, such as `http://192.168.6.10:18990` or the HTTPS
domain behind your reverse proxy. Dashbox uses this value to generate TVBox
spider URLs, media helper URLs, Kodi repository metadata, and other
self-referencing links. If it is missing or points at an internal server address,
clients may not be able to open those links.

## Install from PyPI

Use the PyPI package for a simple deployment:

```bash
uv tool install dashbox --prerelease=allow
dashbox --data-dir data --host 0.0.0.0 --port 18990 --public-base-url http://192.168.6.10:18990
```

Upgrade Dashbox:

```bash
uv tool upgrade dashbox --prerelease=allow
```

Dashbox depends on `yt-dlp[default,curl-cffi]`. When site extraction breaks, you
can force reinstall the isolated `uv tool` environment and refresh `yt-dlp`:

```bash
uv tool install --force dashbox --upgrade-package yt-dlp --prerelease=allow
```

## Run from Source

For source setup, frontend asset builds, tests, and source environment
dependency updates, see [Development](development.md).

## Data Directory and Admin UI

The recommended runtime shape is:

```bash
dashbox --data-dir data --host 0.0.0.0 --port 18990 --public-base-url http://192.168.6.10:18990
```

With `--data-dir data`, Dashbox reads `data/config.json` and creates a minimal
file if it does not exist. The admin UI is served at:

```text
http://<server>:18990/admin
```

On first use, Dashbox creates an admin setup code in the data directory. Use it
to set the admin access code, then log in with that access code for later edits.

You can also run with an explicit config file:

```bash
dashbox -c config.json --host 0.0.0.0 --port 18990 --public-base-url http://192.168.6.10:18990
```

Other runtime settings such as `DASHBOX_UPSTREAM_TIMEOUT` and
`DASHBOX_UNSAFE_IMAGE_PROXY_MODE` are documented in [Configuration
fields](config-fields.md).

## Reverse Proxy or LAN Access

If clients do not use the same host/port that Dashbox sees internally, set a
public base URL:

```bash
dashbox --data-dir data --public-base-url http://192.168.6.10:18990
```

The same value can be supplied with `DASHBOX_PUBLIC_BASE_URL`.
