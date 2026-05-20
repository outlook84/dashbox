## Environment Variables

These values are process-level settings, not `config.json` fields. The admin UI may show the effective runtime values for `public_base_url`, `upstream_timeout`, and `image_proxy_mode`, but putting those keys in `config.json` has no effect.

| Environment variable | CLI option | Default | Allowed values | Description |
| --- | --- | --- | --- | --- |
| `DASHBOX_CONFIG` | `-c`, `--config` | empty | file path | JSON config file path. |
| `DASHBOX_DATA_DIR` | `--data-dir` | empty | directory path | Dashbox data directory. When no explicit config path is set, Dashbox uses `<data-dir>/config.json` and creates a minimal file if needed. |
| `DASHBOX_HOST` | `--host` | `0.0.0.0` | listen host | Server listen host. |
| `DASHBOX_PORT` | `--port` | `18990` | `1` to `65535` | Server listen port. |
| `DASHBOX_PUBLIC_BASE_URL` | `--public-base-url` | empty | absolute public URL | Public URL used when Dashbox must generate self-referencing links behind a proxy. |
| `DASHBOX_RELOAD` | `--reload` | `false` | `1/0`, `true/false`, `yes/no`, `on/off` | Enables uvicorn reload. |
| `DASHBOX_UPSTREAM_TIMEOUT` | none | `30` | `1` to `300` | Timeout for upstream HTTP requests, in seconds. |
| `DASHBOX_UNSAFE_IMAGE_PROXY_MODE` | none | `known` | `off`, `known`, `all` | Controls which image URLs Dashbox may proxy. `all` is intentionally unsafe. |

## Config File Scope

Dashbox currently persists these top-level fields in `config.json`:

- `proxy_media_idle_ttl_seconds`
- `proxy_dash_media_url`
- `ytdlp_concurrency`
- `log_level`
- `user_agent`
- `cookies_from_browser`
- `subs`

## Global Fields

| Field | Type | Default | Allowed values | Tooltip |
| --- | --- | --- | --- | --- |
| `log_level` | string | `info` | `critical`, `error`, `warning`, `info`, `debug` | Controls Dashbox server log verbosity. |
| `ytdlp_concurrency` | integer | `8` | `1` to `32` | Maximum number of concurrent yt-dlp extraction jobs. |
| `proxy_media_idle_ttl_seconds` | integer | `21600` | `1` to `604800` | How long idle DASH/inline media proxy sessions stay available, in seconds. Direct media URLs are not affected. |
| `proxy_dash_media_url` | boolean | `false` | `true`, `false` | Proxy DASH media segment URLs through Dashbox when needed by clients. |
| `user_agent` | string | empty | any string | Custom User-Agent used for upstream media and metadata requests. Empty uses yt-dlp's default. |
| `cookies_from_browser.mode` | string | `disabled` | `disabled`, `firefox`, `firefox_data_dir`, `chrome`, `edge`, `custom` | Selects a browser cookie source for yt-dlp. `firefox_data_dir` reads from `<data-dir>/firefox-profile`. |
| `cookies_from_browser.value` | string | empty | yt-dlp cookies-from-browser syntax | Custom cookie source. Only valid when cookie mode is `custom`. |

## Subscriptions

Each item in `subs` defines one TVBox or Kodi endpoint.

| Field | Type | Required | Allowed values | Tooltip |
| --- | --- | --- | --- | --- |
| `id` | string | yes | config id | Stable subscription identifier used in URLs and admin edits. Must be unique across all subscriptions. |
| `type` | string | yes | `tvbox`, `kodi` | Endpoint type exposed by this subscription. |
| `auth_mode` | string | yes | `anonymous`, `access_code` | Controls whether clients can open this subscription without an access code. |
| `access_code_hash` | string | when `auth_mode` is `access_code` | bcrypt hash | Stored hash for the subscription access code. Access codes must be 4 to 12 digits, and the admin UI redacts the original value. |
| `tvbox` | object | for `type: tvbox` | TVBox payload | TVBox-specific settings. Mutually exclusive with `kodi`. |
| `kodi` | object | for `type: kodi` | Kodi payload | Kodi-specific settings. Mutually exclusive with `tvbox`. |

## Shared Subscription Payload Fields

These fields are supported in both `tvbox` and `kodi` payloads. When omitted, Dashbox uses the global default from the schema.

| Field | Type | Default | Allowed values | Tooltip |
| --- | --- | --- | --- | --- |
| `search_provider` | string | `ytdlp` | `ytdlp`, `bilibili` | Search backend used by this subscription. |
| `ytdlp_search_prefix.mode` | string | `youtube` | `youtube`, `bilibili`, `soundcloud`, `custom` | yt-dlp search target used when the search provider is `ytdlp`. |
| `ytdlp_search_prefix.value` | string | empty | valid yt-dlp search prefix | Custom yt-dlp search prefix. Only valid when mode is `custom`. |
| `ytdlp_search_limit` | integer | `30` | `0` to `200` | Maximum yt-dlp search results. `0` means use the built-in default. |
| `bilibili_search_limit` | integer | `30` | `0` to `200` | Maximum Bilibili search results. `0` means use the built-in default. |
| `playlist_limit` | integer | `100` | `0` to `1000` | Maximum entries loaded from generic playlists. `0` means use the built-in default. |
| `bilibili_list_limit` | integer | `100` | `0` to `1000` | Maximum entries loaded from Bilibili lists. `0` means use the built-in default. |

## TVBox Payload Fields

| Field | Type | Default | Allowed values | Tooltip |
| --- | --- | --- | --- | --- |
| `site_key` | string | `dashbox` | unique config id | Unique TVBox site key. Duplicate site keys are rejected. |
| `site_name` | string | `Dashbox` | any non-empty string | Display name shown by TVBox clients. |
| `locale` | string | `zh-CN` | `zh-CN`, `en-US` | Display language used by TVBox clients. |
| `vod_style` | string | `list` | `list`, `landscape`, `portrait` | Preferred TVBox VOD card layout. |
| `max_video_height` | integer | `0` | `0`, `480`, `720`, `1080`, `1440`, `2160`, `4320` | Highest allowed video height. `0` means unlimited. |
| `max_video_fps` | integer | `0` | `0`, `24`, `30`, `60`, `120` | Highest allowed video frame rate. `0` means unlimited. |
| `youtube_subtitles` | boolean | `false` | `true`, `false` | Include YouTube subtitle formats when available. |
| `video_codec_preferences` | array | all enabled | `h264`, `hevc`, `vp9`, `av01` | Disabled video codecs are excluded. Enabled codecs earlier in the list win among candidates with the same resolution and frame rate. |
| `audio_codec_preferences` | array | all enabled | `aac`, `opus`, `eac3`, `ac3`, `flac`, `other` | Disabled audio codecs are excluded. Enabled codecs earlier in the list win among candidates with similar audio quality. `other` covers unrecognized audio codecs. |
| `sources` | array | `[]` | source objects | TVBox source groups shown by the client. |

## Kodi Payload Fields

| Field | Type | Default | Allowed values | Tooltip |
| --- | --- | --- | --- | --- |
| `root` | object | omitted | Kodi root metadata object | Optional Kodi root node metadata passed through to the adapter. |
| `sources` | array | `[]` | URL or folder items | Kodi top-level items shown by the add-on. |

## Source And Item Fields

TVBox sources use source groups, and Kodi sources can place URL or folder items at the root.

| Field | Applies to | Type | Required | Tooltip |
| --- | --- | --- | --- | --- |
| `source.id` | TVBox source | string | yes | Stable source identifier. Must be unique inside the subscription. |
| `source.name` | TVBox source | string | yes | Source group display name. |
| `source.items` | TVBox source | array | no | Items inside this source group. |
| `item.id` | URL or folder item | string | recommended | Stable item identifier. Must be unique inside the containing subscription/source tree. |
| `item.url` | URL item | string | yes | HTTP(S) video, playlist, channel, or supported yt-dlp search URL. |
| `item.title` | URL item | string | no | Optional display title override. |
| `item.name` | folder item | string | yes | Folder display name. URL items must use `title` instead. |
| `item.items` | folder item | array | yes | Child items inside this folder. |
| `item.pic` | URL or folder item | string | no | Optional poster or thumbnail URL. |
| `item.remarks` | URL or folder item | string | no | Optional short note shown by supported clients. |

An item must contain either `url` or `items`, never both.
