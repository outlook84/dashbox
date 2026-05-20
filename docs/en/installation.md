# Installation

Dashbox requires Python 3.11 or newer. Source development also requires Node.js
22.13 or newer.

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

## Container Deployment

Container image:

```text
ghcr.io/outlook84/dashbox:latest
```

Mount a persistent data directory and set the public URL that clients use to
reach Dashbox:

```bash
docker run -d --name dashbox --restart unless-stopped -p 18990:18990 -v ./data:/data -e DASHBOX_PUBLIC_BASE_URL=http://192.168.6.10:18990 ghcr.io/outlook84/dashbox:latest
```

The image defaults to `DASHBOX_DATA_DIR=/data`, `DASHBOX_HOST=0.0.0.0`, and
`DASHBOX_PORT=18990`. After the first start, the config file is stored on the
host at `./data/config.json`. The admin UI is still served at:

```text
http://<server>:18990/admin
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

## Firefox Data Dir Cookies

To let yt-dlp read Firefox cookies from the Dashbox data directory, set
`Browser cookies mode` to `Firefox (data dir)` in the admin UI, or put this in
`config.json`:

```json
{
  "cookies_from_browser": {
    "mode": "firefox_data_dir"
  }
}
```

This mode requires Dashbox to start with `--data-dir` or `DASHBOX_DATA_DIR`.
Dashbox resolves the cookie source to `<data-dir>/firefox-profile`, so place the
Firefox profile files at:

```text
data/firefox-profile
```

Use a dedicated Firefox profile for Dashbox and sign in only to the sites that
Dashbox needs to extract. Avoid reusing your everyday browser profile; a
dedicated profile keeps the cookie scope smaller and avoids files being locked
or changed while Firefox is running.

You usually do not need to copy the full profile. Copy `cookies.sqlite` from the
dedicated profile into `data/firefox-profile/`. If you use Firefox
Multi-Account Containers, also copy `containers.json`:

```text
data/firefox-profile/cookies.sqlite
data/firefox-profile/containers.json
```

For container deployments, the matching host path is `./data/firefox-profile`
and the in-container path is `/data/firefox-profile`.

## Reverse Proxy or LAN Access

If clients do not use the same host/port that Dashbox sees internally, set a
public base URL:

```bash
dashbox --data-dir data --public-base-url http://192.168.6.10:18990
```

The same value can be supplied with `DASHBOX_PUBLIC_BASE_URL`.
