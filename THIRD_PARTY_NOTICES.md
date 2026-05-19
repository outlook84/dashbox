# Third-Party Notices

Dashbox is distributed under `GPL-3.0-only`. Third-party components keep their
own licenses. This file summarizes the license families currently used by the
locked Python and pnpm dependency sets; consult the installed package metadata
for the full license text of each dependency.

## Python Runtime Dependencies

- `biliass`: `GPL-3.0-only`
- `mutagen`: `GPL-2.0-or-later`
- `yt-dlp`, `yt-dlp-ejs`: `Unlicense`, with `yt-dlp-ejs` also declaring `MIT`
  and `ISC`
- `bcrypt`, `requests`: `Apache-2.0`
- `certifi`: `MPL-2.0`
- `fastapi`, `pydantic`, `pydantic-core`, `anyio`, `brotli`, `cffi`,
  `charset-normalizer`, `h11`, `h2`, `hpack`, `httptools`, `hyperframe`,
  `pyyaml`, `typing-inspection`, `urllib3`, `watchfiles`: `MIT`
- `httpx`, `httpcore`, `uvicorn`, `click`, `idna`, `pycparser`,
  `python-dotenv`, `starlette`, `websockets`: `BSD-3-Clause`
- `pycryptodomex`: `BSD` and public domain notices
- `typing-extensions`: `PSF-2.0`

Development-only Python dependencies include `pytest`, `pytest-xdist`, and
their transitive dependencies.

## JavaScript and Admin UI Dependencies

The pnpm workspace dependency set is composed of packages declaring these
license families:

- `MIT`
- `Apache-2.0`
- `ISC`
- `BSD-2-Clause`
- `BSD-3-Clause`
- `Python-2.0`
- `BlueOak-1.0.0`

Notable bundled UI/runtime packages include CodeMirror packages, `@lucide/vue`,
`naive-ui`, and `vue`. Build and test tooling includes Vite, Vitest, ESLint,
TypeScript, and related transitive packages.

## Assets

Fallback TVBox icons generated from Lucide icons are covered by the ISC notice
in `dashbox/assets/NOTICE.md`.
