## 环境变量

这些值是进程级运行设置，不是 `config.json` 字段。管理页可能会展示 `public_base_url`、`upstream_timeout`、`image_proxy_mode` 的当前运行值，但把这些键写进 `config.json` 不会生效。

| 环境变量 | CLI 参数 | 默认值 | 可选值 | 说明 |
| --- | --- | --- | --- | --- |
| `DASHBOX_CONFIG` | `-c`, `--config` | 空 | 文件路径 | JSON 配置文件路径。 |
| `DASHBOX_DATA_DIR` | `--data-dir` | 空 | 目录路径 | Dashbox 数据目录。未指定显式配置文件时，Dashbox 使用 `<data-dir>/config.json`，文件不存在时自动创建最小配置。 |
| `DASHBOX_HOST` | `--host` | `0.0.0.0` | 监听地址 | 服务监听地址。 |
| `DASHBOX_PORT` | `--port` | `18990` | `1` 到 `65535` | 服务监听端口。 |
| `DASHBOX_PUBLIC_BASE_URL` | `--public-base-url` | 空 | 公开访问绝对 URL | 反向代理场景下生成 Dashbox 自引用链接时使用的公开 URL。 |
| `DASHBOX_RELOAD` | `--reload` | `false` | `1/0`, `true/false`, `yes/no`, `on/off` | 启用 uvicorn reload。 |
| `DASHBOX_UPSTREAM_TIMEOUT` | 无 | `30` | `1` 到 `300` | 上游 HTTP 请求超时时间，单位秒。 |
| `DASHBOX_UNSAFE_IMAGE_PROXY_MODE` | 无 | `known` | `off`, `known`, `all` | 控制 Dashbox 可以代理哪些图片 URL。`all` 为不安全模式。 |

## 配置文件字段

Dashbox 当前会写入 `config.json` 的顶层字段包括：

- `proxy_media_idle_ttl_seconds`
- `proxy_dash_media_url`
- `ytdlp_concurrency`
- `log_level`
- `user_agent`
- `cookies_from_browser`
- `subs`

## 全局字段

| 字段 | 类型 | 默认值 | 可选值 | Tooltip |
| --- | --- | --- | --- | --- |
| `log_level` | string | `info` | `critical`, `error`, `warning`, `info`, `debug` | 控制 Dashbox 服务日志详细程度。 |
| `ytdlp_concurrency` | integer | `8` | `1` 到 `32` | yt-dlp 同时解析任务的最大数量。 |
| `proxy_media_idle_ttl_seconds` | integer | `21600` | `1` 到 `604800` | DASH/内联媒体代理会话空闲后保留的秒数。普通直连媒体 URL 不受影响。 |
| `proxy_dash_media_url` | boolean | `false` | `true`, `false` | 在客户端需要时，经由 Dashbox 代理 DASH 媒体分片 URL。 |
| `user_agent` | string | 空 | 任意字符串 | 上游媒体和元数据请求使用的自定义 User-Agent。留空使用 yt-dlp 默认值。 |
| `cookies_from_browser.mode` | string | `disabled` | `disabled`, `firefox`, `firefox_data_dir`, `chrome`, `edge`, `custom` | 选择 yt-dlp 使用的浏览器 Cookies 来源。`firefox_data_dir` 会读取 `<data-dir>/firefox-profile`。 |
| `cookies_from_browser.value` | string | 空 | yt-dlp cookies-from-browser 语法 | 自定义 Cookies 来源。仅在模式为 `custom` 时有效。 |

## 订阅

`subs` 中每一项定义一个 TVBox 或 Kodi 入口。

| 字段 | 类型 | 必填 | 可选值 | Tooltip |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | 配置 id | 订阅稳定标识，用于 URL 和管理页编辑。必须在所有订阅中唯一。 |
| `type` | string | 是 | `tvbox`, `kodi` | 此订阅对外提供的入口类型。 |
| `auth_mode` | string | 是 | `anonymous`, `access_code` | 控制客户端访问此订阅时是否需要访问码。 |
| `access_code_hash` | string | `auth_mode` 为 `access_code` 时必填 | bcrypt hash | 订阅访问码哈希。访问码仅支持 4 到 12 位数字，管理页会隐藏原值。 |
| `tvbox` | object | `type: tvbox` 时必填 | TVBox 配置对象 | TVBox 专属配置。不能和 `kodi` 同时存在。 |
| `kodi` | object | `type: kodi` 时必填 | Kodi 配置对象 | Kodi 专属配置。不能和 `tvbox` 同时存在。 |

## 订阅通用字段

以下字段同时支持在 `tvbox` 和 `kodi` 配置对象里使用。省略时使用 schema 提供的全局默认值。

| 字段 | 类型 | 默认值 | 可选值 | Tooltip |
| --- | --- | --- | --- | --- |
| `search_provider` | string | `ytdlp` | `ytdlp`, `bilibili` | 此订阅使用的搜索后端。 |
| `ytdlp_search_prefix.mode` | string | `youtube` | `youtube`, `bilibili`, `soundcloud`, `custom` | 搜索后端为 `ytdlp` 时使用的搜索目标。 |
| `ytdlp_search_prefix.value` | string | 空 | 有效 yt-dlp 搜索前缀 | 自定义 yt-dlp 搜索前缀。仅在模式为 `custom` 时有效。 |
| `ytdlp_search_limit` | integer | `30` | `0` 到 `200` | yt-dlp 搜索结果上限。`0` 表示使用内置默认值。 |
| `bilibili_search_limit` | integer | `30` | `0` 到 `200` | Bilibili 搜索结果上限。`0` 表示使用内置默认值。 |
| `playlist_limit` | integer | `100` | `0` 到 `1000` | 通用播放列表加载条目上限。`0` 表示使用内置默认值。 |
| `bilibili_list_limit` | integer | `100` | `0` 到 `1000` | Bilibili 列表加载条目上限。`0` 表示使用内置默认值。 |

## TVBox 配置对象字段

| 字段 | 类型 | 默认值 | 可选值 | Tooltip |
| --- | --- | --- | --- | --- |
| `site_key` | string | `dashbox` | 唯一配置 id | TVBox 站点唯一标识。重复的站点标识会被拒绝。 |
| `site_name` | string | `Dashbox` | 任意非空字符串 | TVBox 客户端展示的站点名称。 |
| `locale` | string | `zh-CN` | `zh-CN`, `en-US` | TVBox 客户端显示语言。 |
| `vod_style` | string | `list` | `list`, `landscape`, `portrait` | TVBox 视频卡片展示样式。 |
| `max_video_height` | integer | `0` | `0`, `480`, `720`, `1080`, `1440`, `2160`, `4320` | 允许的最高视频高度。`0` 表示不限。 |
| `max_video_fps` | integer | `0` | `0`, `24`, `30`, `60`, `120` | 允许的最高视频帧率。`0` 表示不限。 |
| `youtube_subtitles` | boolean | `false` | `true`, `false` | 播放 YouTube 视频时，如有字幕则一并提供。 |
| `video_codec_preferences` | array | 全部启用 | `h264`, `hevc`, `vp9`, `av01` | 未启用的视频编码会被排除；启用项越靠前，在清晰度和帧率相同的候选中越优先。 |
| `audio_codec_preferences` | array | 全部启用 | `aac`, `opus`, `eac3`, `ac3`, `flac`, `other` | 未启用的音频编码会被排除；启用项越靠前，在音质相近的候选中越优先。`other` 用于无法识别的音频编码。 |
| `sources` | array | `[]` | source 对象 | TVBox 客户端显示的来源分组。 |

## Kodi 配置对象字段

| 字段 | 类型 | 默认值 | 可选值 | Tooltip |
| --- | --- | --- | --- | --- |
| `root` | object | 省略 | Kodi 根节点元数据对象 | 透传给适配器的可选 Kodi 根节点元数据。 |
| `sources` | array | `[]` | URL 或文件夹条目 | Kodi 插件显示的顶层条目。 |

## 来源和条目字段

TVBox 使用 source 分组，Kodi 可以直接把 URL 或文件夹条目放在根级。

| 字段 | 适用范围 | 类型 | 必填 | Tooltip |
| --- | --- | --- | --- | --- |
| `source.id` | TVBox source | string | 是 | 来源稳定标识。在当前订阅内必须唯一。 |
| `source.name` | TVBox source | string | 是 | 来源分组显示名称。 |
| `source.items` | TVBox source | array | 否 | 此来源分组下的条目。 |
| `item.id` | URL 或文件夹条目 | string | 建议填写 | 条目稳定标识。在所属订阅或来源树内必须唯一。 |
| `item.url` | URL 条目 | string | 是 | HTTP(S) 视频、播放列表、频道或受支持的 yt-dlp 搜索 URL。 |
| `item.title` | URL 条目 | string | 否 | 可选显示标题覆盖。 |
| `item.name` | 文件夹条目 | string | 是 | 文件夹显示名称。URL 条目应使用 `title`。 |
| `item.items` | 文件夹条目 | array | 是 | 文件夹下的子条目。 |
| `item.pic` | URL 或文件夹条目 | string | 否 | 可选海报或缩略图 URL。 |
| `item.remarks` | URL 或文件夹条目 | string | 否 | 支持的客户端可展示的简短备注。 |

一个条目必须包含 `url` 或 `items` 其中之一，不能同时包含两者。
