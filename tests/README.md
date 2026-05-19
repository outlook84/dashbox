# Test Layout

Tests follow the same ownership boundaries as `dashbox/`:

- `adapters/`: protocol-facing response shapes and TVBox service behavior.
  - `adapters/tvbox/`: TVBox-specific navigation, search, playlist, and thumbnail responses.
- `auth/`: access codes, tokens, and authentication helpers.
- `config/`: configuration parsing and subscription-level behavior.
- `core/`: orchestration, navigation, media mapping, and generic core utilities.
  - `core/media_service/`: `MediaService` detail, play, cache, and extraction orchestration.
- `media/`: yt-dlp clients, playback selection, DASH proxying, and media transport.
- `server/`: FastAPI routes, app state, image proxy routes, and request handling.
- `sites/`: site adapter rules, URL classification, metadata parsing, and pagination.
  - `sites/bilibili/`: Bilibili-specific adapter behavior split by product area.

Shared test builders live in `helpers.py`. Avoid importing helpers from another
test module; move common builders to `helpers.py` instead.
