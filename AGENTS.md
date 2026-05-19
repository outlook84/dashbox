# Dashbox Repository Notes

Dashbox turns configured video sources into TVBox and Kodi endpoints. 
The repository contains the Python service, the Vue admin UI, the
TVBox spider bundle, and Kodi plugin packaging.

## Directory Structure

- `dashbox/` - Python package and runtime code.
- `dashbox/server/` - FastAPI app, CLI, static routes, auth, image/media proxy routes.
- `dashbox/core/` - Application services and shared domain flow.
- `dashbox/adapters/` - TVBox and Kodi protocol adapters.
- `dashbox/sites/` - Site-specific URL, metadata, and navigation support.
- `dashbox/media/` - yt-dlp integration, playback selection, DASH/HLS helpers, caches.
- `dashbox/config/` - Config models, parsing, serialization, validation, and loading.
- `dashbox/auth/` - Access-code, token, and limiter helpers.
- `dashbox/assets/` - Packaged static assets, including generated spider/admin assets.
- `dashbox/kodi/` - Kodi plugin source packaged with the Python distribution.
- `apps/admin/` - Vue/Vite admin UI workspace package.
- `apps/tvbox/` - TypeScript TVBox spider source and tests.
- `tests/` - Python test suite, organized mostly by package area.
- `scripts/` - Build, packaging, and audit scripts.
- `docs/` - Project documentation.

## Development Commands

Install dependencies:

```powershell
uv sync --extra dev
pnpm install
```

Run the backend locally:

```powershell
uv run dashbox --data-dir data --port 18990
```

Run with an explicit config file:

```powershell
uv run dashbox -c config.json --port 18990
```

Run the admin UI dev server:

```powershell
pnpm run dev
```

Build generated assets:

```powershell
pnpm run build:spider
pnpm run build:admin
```

Build all pnpm workspace packages:

```powershell
pnpm run build
```

Run checks:

```powershell
uv run pytest
pnpm run lint
pnpm run typecheck
pnpm run test:admin
pnpm run test:tvbox
```

Run focused checks:

```powershell
uv run pytest tests/config/test_config_items.py
pnpm run test:admin
pnpm run typecheck:admin
pnpm run typecheck:tvbox
pnpm run lint:admin
pnpm run lint:tvbox
```

Update yt-dlp when site extraction breaks:

```powershell
uv lock --upgrade-package yt-dlp
uv sync
```

Package the Kodi plugin:

```powershell
uv run python scripts/package_kodi_plugin.py
```

## Notes

- Use Python 3.11+ and Node.js 22.13+.
- The root package manager is `pnpm@10.33.4`.
- Generated admin output is written under `dashbox/assets/admin`.
- Generated TVBox spider output is written under `dashbox/assets/dashbox.<hash>.js`.
- `config.example.json` is the reference config; local `config.json` may contain
  machine-specific or private values.
