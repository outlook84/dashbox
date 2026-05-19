# Development

Dashbox is a mixed Python and TypeScript workspace.

## Layout

- `dashbox/`: Python package and runtime code.
- `dashbox/server/`: FastAPI app, CLI, static routes, auth, media/image proxy
  routes, and Kodi repository endpoints.
- `dashbox/core/`: shared source navigation, detail, search, and playback flow.
- `dashbox/adapters/`: TVBox and Kodi protocol adapters.
- `dashbox/media/`: yt-dlp integration, DASH/HLS handling, media caches, and
  playback selection.
- `dashbox/config/`: config models, parsing, serialization, validation, and admin
  schema data.
- `dashbox/kodi/`: Kodi add-on source packaged with the Python distribution.
- `apps/admin/`: Vue/Vite admin UI.
- `apps/tvbox/`: TypeScript TVBox/CatVodSpider runtime.
- `tests/`: Python tests.
- `scripts/`: build, packaging, and audit scripts.

## Setup

```bash
uv sync --extra dev
pnpm install
```

Run the backend locally:

```bash
uv run dashbox --data-dir data --port 18990
```

Run the admin UI dev server:

```bash
pnpm run dev
```

## Build

```bash
pnpm run build:spider
pnpm run build:admin
pnpm run build
```

Generated admin output is written to `dashbox/assets/admin`. Generated TVBox
spider output is written to `dashbox/assets/dashbox.<hash>.js`.

Package the Kodi plugin:

```bash
uv run python scripts/package_kodi_plugin.py
```

## Checks

```bash
uv run pytest
pnpm run lint
pnpm run typecheck
pnpm run test
```

Focused checks:

```bash
uv run pytest tests/config/test_config_items.py
pnpm run test:admin
pnpm run test:tvbox
pnpm run typecheck:admin
pnpm run typecheck:tvbox
pnpm run lint:admin
pnpm run lint:tvbox
```

## Updating yt-dlp in Source

The source environment is locked by `uv.lock`. To update the stable yt-dlp
package:

```bash
uv lock --upgrade-package yt-dlp
uv sync
```

To allow pre-release yt-dlp fixes:

```bash
uv lock --upgrade-package yt-dlp --prerelease allow
uv sync
```
