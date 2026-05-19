# dashbox

`dashbox` 是一个基于 `yt-dlp` 的 TVBox / CatVodSpider 网关原型。

它提供 TVBox 订阅、内置 Spider JS，以及 `home/category/search/detail/play` 接口。播放接口会调用 `yt-dlp` 解析 URL，优先返回可直接播放的地址；遇到音视频分离格式时，会尝试合成 `data:application/dash+xml;base64,...` MPD。

当前播放策略：

- 默认播放优先级是 HLS、progressive 直链、DASH；yt-dlp 返回可构造直接 DASH 的音视频分离格式时，可返回 `data:application/dash+xml;base64,...` MPD，让播放器直接访问媒体链接。
- 开启 `proxy_dash_media_url` 后，播放优先级改为 DASH、HLS、progressive；可分片的音视频分离格式会生成本地 `/media/{token}/manifest.mpd`，并由网关代理分片。代理分片遇到上游 URL 过期返回 `403/404/410` 时，会尝试重新解析并刷新 DASH session。
- 没有可代理 DASH 分片时，回退到原始 manifest URL、HLS 或 progressive 直链。
- 简单 `SegmentBase` 格式仍可生成 base64 MPD。

## 启动

构建 TVBox Spider：

```bash
pnpm install
pnpm run build:spider
pnpm run build:admin
```

前端和 Spider JS 使用 pnpm workspace 管理：

```text
apps/admin   # Vue 管理后台
apps/tvbox   # TVBox / CatVodSpider JS 适配器
```

常用 Node 侧命令：

```bash
pnpm run dev             # 启动 admin 开发服务
pnpm run build           # 构建 admin 和 TVBox Spider
pnpm run typecheck       # 检查所有 TS workspace 包
pnpm run test            # 运行所有前端 / Spider 单测
pnpm run test:admin      # 运行 admin 前端单测
pnpm run test:tvbox      # 运行 TVBox Spider 单测
```

从源码运行时使用项目内 `.venv`：

```bash
uv sync
uv run dashbox --data-dir data --port 18990
```

从源码开发时额外安装测试依赖：

```bash
uv sync --extra dev
uv run dashbox --data-dir data --port 18990
uv run pytest
```

源码环境里的依赖版本由 `uv.lock` 固定。需要升级源码环境里的 `yt-dlp` stable 通道时，重新解析锁文件并同步：

```bash
uv lock --upgrade-package yt-dlp
uv sync
```

需要更快获取 `yt-dlp` 修复时，可以让锁文件解析 nightly 通道：

```bash
uv lock --upgrade-package yt-dlp --prerelease allow
uv sync
```

从 PyPI 安装适合稳定部署，会安装到 `uv` 管理的全局隔离工具环境：

```bash
uv tool install dashbox
dashbox --host 0.0.0.0 --port 18990
```

升级 `dashbox`：

```bash
uv tool upgrade dashbox
```

`dashbox` 默认依赖 `yt-dlp[default,curl-cffi]`。站点解析失效时，可以强制重装 `uv tool install` 管理的独立环境，并刷新其中的 `yt-dlp` 版本。

默认使用 stable 通道：

```bash
uv tool install --force dashbox --upgrade-package yt-dlp
```

需要更快获取 `yt-dlp` 修复时使用 nightly 通道：

```bash
uv tool install --force dashbox --upgrade-package yt-dlp --prerelease allow
```

发布前需要先构建 TVBox Spider，确保带 hash 的 `dashbox/assets/dashbox.<hash>.js` 已更新。Kodi 插件源码作为包内运行期资源发布，服务启动和 `/repo/` 不依赖仓库根目录。

TVBox 订阅地址：

```text
http://你的网关地址:18990/sub
```

健康检查：

```text
http://你的网关地址:18990/healthz
```

内置管理界面：

```text
http://你的网关地址:18990/admin
```

Admin UI 需要以 `--data-dir data`、`DASHBOX_DATA_DIR=data`、`--config config.json` 或 `DASHBOX_CONFIG=config.json` 启动后才能保存配置。使用 data dir 启动时，服务会读取 `data/config.json`，文件不存在时自动生成最小配置。首次访问时，服务会生成一次性 `admin_setup_code`；指定 data dir 时写入 data dir，否则写入配置文件同目录。使用该 setup code 设置 admin access code 后登录；后续登录使用 admin access code。前端只编辑配置文件字段，`public_base_url`、`image_proxy_mode`、`upstream_timeout` 会作为只读运行态设置显示。

`/sub` 会返回带指纹的 Spider URL，例如：

```text
http://你的网关地址:18990/spider/dashbox.<hash>.js
```

## 配置

推荐使用 data dir 启动；`config.json` 不存在时会自动生成最小配置：

```bash
uv run dashbox --data-dir data --port 18990
```

也可以复制 `config.example.json` 后通过显式配置文件启动：

```bash
uv run dashbox -c config.json --port 18990
```

常用字段：

### 顶层配置

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `proxy_media_idle_ttl_seconds` | `21600` | DASH 媒体代理 session 在没有有效 manifest 或分片请求后保留多久，范围 `1..604800`，单位秒。 |
| `proxy_dash_media_url` | `false` | 是否让 dashbox 优先使用本地 DASH 媒体代理。关闭时播放优先级是 HLS、progressive 直链、DASH；开启时播放优先级是 DASH、HLS、progressive。DASH 代理可在分片上游 URL 过期时尝试重新解析刷新；这个开关不代理 progressive 单文件直链，也不表示全流量代理。 |
| `ytdlp_concurrency` | `8` | 阻塞型 yt-dlp 任务并发数，范围 `1..32`。 |
| `log_level` | `info` | dashbox 业务日志和 uvicorn 日志级别，支持 `critical`、`error`、`warning`、`info`、`debug`。 |
| `user_agent` | `""` | 自定义 UA。留空时，dashbox 自己发起的请求会跟随本进程 yt-dlp 的默认 UA；填入非空值时，会同时用于 dashbox 自己的请求和传给 yt-dlp 的全局 `User-Agent`。 |
| `cookies_from_browser` | `{"mode": "disabled"}` | 传给 yt-dlp 的浏览器 cookies 来源配置对象。内置 `mode` 支持 `disabled`、`firefox`、`chrome`、`edge`、`brave`、`chromium`，自定义时使用 `{ "mode": "custom", "value": "firefox:default-release::Work" }`。 |

### 运行环境配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DASHBOX_CONFIG` | `""` | JSON 配置文件路径。留空时只使用内置默认配置。 |
| `DASHBOX_DATA_DIR` | `""` | Dashbox 数据目录。未指定 `DASHBOX_CONFIG` 时会使用 `<data-dir>/config.json`，不存在则自动生成最小配置；admin setup/access code 也写入该目录。 |
| `DASHBOX_HOST` | `0.0.0.0` | 监听地址。 |
| `DASHBOX_PORT` | `18990` | 监听端口，范围 `1..65535`。 |
| `DASHBOX_PUBLIC_BASE_URL` | `""` | 对外访问基准 URL。反向代理场景下用于生成自引用链接；也可用 `--public-base-url` 设置。 |
| `DASHBOX_RELOAD` | `false` | 是否启用 uvicorn reload。支持 `1/0`、`true/false`、`yes/no`、`on/off`。 |
| `DASHBOX_UPSTREAM_TIMEOUT` | `30` | dashbox 访问上游站点和 yt-dlp socket 的默认超时时间，范围 `1..300`，单位秒。 |
| `DASHBOX_UNSAFE_IMAGE_PROXY_MODE` | `known` | 图片代理模式，支持 `off`、`known`、`all`。 |

命令行参数 `-c/--config`、`--data-dir`、`--host`、`--port`、`--public-base-url`、`--reload` 会覆盖对应环境变量。配置文件优先级为 `--config`、`DASHBOX_CONFIG`、`--data-dir/config.json`、`DASHBOX_DATA_DIR/config.json`。

TVBox 的搜索和列表配置只放在 `subs[].tvbox` 里；省略时使用内置默认值。

### TVBox 订阅配置

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `subs[].tvbox.site_key` | 必填 | TVBox 订阅的站点 key；多个 TVBox 订阅必须唯一。 |
| `subs[].tvbox.site_name` | `Dashbox` | TVBox 订阅的站点展示名。 |
| `subs[].tvbox.locale` | `zh-CN` | TVBox 端内置文案语言，支持 `zh-CN` 和 `en-US`。 |
| `subs[].tvbox.search_provider` | `ytdlp` | 当前 TVBox 订阅使用的搜索源，支持 `ytdlp` 和 `bilibili`。 |
| `subs[].tvbox.ytdlp_search_prefix` | `{"mode": "youtube"}` | 当前 TVBox 订阅的 yt-dlp 搜索前缀配置对象。内置 `mode` 支持 `youtube`、`soundcloud`；自定义时使用 `{ "mode": "custom", "value": "nicosearchdate" }`。 |
| `subs[].tvbox.ytdlp_search_limit` | `30` | 当前 TVBox 订阅的 yt-dlp 搜索结果展开条数。范围 `0..200`，设为 `0` 时使用默认限制。 |
| `subs[].tvbox.bilibili_search_limit` | `30` | 当前 TVBox 订阅的 B 站搜索结果展开条数。范围 `0..200`，设为 `0` 时使用默认限制。 |
| `subs[].tvbox.playlist_limit` | `100` | 当前 TVBox 订阅的播放列表和频道页展开条数。范围 `0..1000`，设为 `0` 时使用默认限制。 |
| `subs[].tvbox.bilibili_list_limit` | `100` | 当前 TVBox 订阅的 B 站收藏夹和列表 API 展开条数。范围 `0..1000`，设为 `0` 时使用默认限制。 |
| `subs[].tvbox.video_codec_preferences` | 全部启用 | TVBox 订阅的视频编码偏好。必须包含 `h264`、`hevc`、`vp9`、`av01` 各一次；顺序表示优先级，`enabled` 表示是否参与播放选择。 |
| `subs[].tvbox.audio_codec_preferences` | 全部启用 | TVBox 订阅的音频编码偏好。必须包含 `aac`、`opus`、`eac3`、`ac3`、`flac`、`other` 各一次；`other` 表示未列出的音频编码。 |
| `subs[].tvbox.max_video_height` | `0` | TVBox 订阅播放时允许的最高视频高度，`0` 表示不限制。 |
| `subs[].tvbox.max_video_fps` | `0` | TVBox 订阅播放时允许的最高视频帧率，`0` 表示不限制。 |
| `subs[].tvbox.youtube_subtitles` | `false` | YouTube 字幕总开关。开启后，TVBox 优先选择匹配 `locale` 的手动字幕；没有手动字幕时，回退到自动生成的原文字幕。自动翻译字幕不会下发。 |
| `subs[].tvbox.vod_style` | `list` | TVBox 订阅默认展示样式，支持 `list`、`landscape` 和 `portrait`。 |
| `subs[].tvbox.sources` | `[]` | 服务端定义的视频源分类和条目。TV 端首页展示 `sources[].name`，进入分类后展示 `sources[].items`。条目分为 URL 内容入口和文件夹两种。 |

### Kodi 订阅配置

Kodi 对接仍在开发中。配置层已预留 `subs[].kodi`，并复用 TVBox 相同的
`sources` 结构和搜索/列表资源限制解析逻辑。Kodi 不使用 TVBox 专属的
`site_key`、`site_name`、`locale`、`vod_style` 字段；Kodi 客户端语言后续由
请求传给服务端，播放编码、分辨率和帧率偏好由 Kodi 插件端按设备配置后在
播放请求中传入。

Kodi 插件的最低适配基线是 Kodi 20 Nexus，主要测试版本是 Kodi 21 Omega。
插件依赖应使用 `xbmc.python` `3.0.0`，不以 Kodi 22 alpha/beta 的新增 API
作为设计基线。

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `subs[].kodi.search_provider` | `ytdlp` | 当前 Kodi 订阅使用的搜索源，支持 `ytdlp` 和 `bilibili`。 |
| `subs[].kodi.ytdlp_search_prefix` | `{"mode": "youtube"}` | 当前 Kodi 订阅的 yt-dlp 搜索前缀配置对象。内置 `mode` 支持 `youtube`、`soundcloud`；自定义时使用 `{ "mode": "custom", "value": "nicosearchdate" }`。 |
| `subs[].kodi.ytdlp_search_limit` | `30` | 当前 Kodi 订阅的 yt-dlp 搜索结果展开条数。范围 `0..200`，设为 `0` 时使用默认限制。客户端不可覆盖。 |
| `subs[].kodi.bilibili_search_limit` | `30` | 当前 Kodi 订阅的 B 站搜索结果展开条数。范围 `0..200`，设为 `0` 时使用默认限制。客户端不可覆盖。 |
| `subs[].kodi.playlist_limit` | `100` | 当前 Kodi 订阅的播放列表和频道页展开条数。范围 `0..1000`，设为 `0` 时使用默认限制。客户端不可覆盖。 |
| `subs[].kodi.bilibili_list_limit` | `100` | 当前 Kodi 订阅的 B 站收藏夹和列表 API 展开条数。范围 `0..1000`，设为 `0` 时使用默认限制。客户端不可覆盖。 |
| `subs[].kodi.sources` | `[]` | 服务端定义的 Kodi 首页条目。顶层可直接配置 URL 内容入口，也可配置文件夹；文件夹结构与 TVBox 的 `sources[].items` 相同。 |

Kodi 的 `sources` 顶层不是 TVBox tab；它就是 Kodi 首页目录本身。因此：

- TVBox 顶层必须是 `Source`，也就是带 `id` / `name` 的 named folder。
- Kodi 顶层直接接受 `items[]` 同构条目：`UrlItem` 或 `FolderItem`。

### 订阅认证

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `subs[].auth_mode` | 必填 | 支持 `anonymous` 和 `access_code`。`access_code` 会保护 `/tvbox/{sub_id}/...` 协议 API，并要求配置 bcrypt `access_code_hash`；不要在配置里写明文访问码。 |

本地局域网直接用时，外部地址可以不配置；如果 TVBox 通过反向代理访问，建议用 `DASHBOX_PUBLIC_BASE_URL` 或 `--public-base-url` 设置外部地址，例如 `http://192.168.6.10:18990` 或 HTTPS 域名。

### 减少客户端直连外站

如果 TVBox 客户端不方便直连外站，可以组合使用三类设置：

- 设置运行环境的 `HTTP_PROXY` / `HTTPS_PROXY`，让 dashbox 服务端自己的出站请求走代理，包括 yt-dlp、站点元数据、图片代理抓图和 DASH 分片代理。
- 设置运行环境的 `DASHBOX_UNSAFE_IMAGE_PROXY_MODE=all`，让封面/缩略图尽量通过 dashbox 本地 `/image` 入口返回给客户端。默认模式是 `known`，只代理已知需要特殊请求头的图片域名；`all` 会把返回给客户端的 HTTP(S) 外部图片 URL 都改写到 `/image?url=...`，会增加服务器流量和缓存压力，只适合可信 URL 来源，不承诺抵御 DNS rebinding 等完整 SSRF 绕过，不建议把服务暴露给不可信用户当作通用图片代理使用。也可以设为 `off` 禁用 `/image` 入口。
- 设置 `proxy_dash_media_url` 为 `true`，让可本地代理的 DASH 媒体分片通过 dashbox 返回给客户端。

`/image` 代理使用进程内缓存和预取队列：默认最多缓存 `64 MiB`，单张图片最多 `2 MiB`，缓存 TTL 为 `24` 小时；目录页最多登记 `32` 张预取图片，预取并发为 `8`，上游抓图队列并发为 `12`。这些是当前内部固定值，不是配置文件字段。

PowerShell 示例：

```powershell
$env:HTTP_PROXY = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
$env:DASHBOX_UNSAFE_IMAGE_PROXY_MODE = "all"
uv run dashbox -c config.json --port 18990
```

`HTTP_PROXY` / `HTTPS_PROXY` 只影响 dashbox 服务器访问上游站点这一段，不会自动改变 TVBox 客户端直连的外部 URL。progressive 单文件直链、外部 HLS 和未代理的外部媒体 URL 仍可能由客户端直接访问。

TVBox 订阅示例：

```json
{
  "subs": [
    {
      "id": "main",
      "type": "tvbox",
      "auth_mode": "anonymous",
      "tvbox": {
        "site_key": "dashbox",
        "site_name": "Dashbox",
        "locale": "zh-CN",
        "video_codec_preferences": [
          { "codec": "h264", "enabled": true },
          { "codec": "hevc", "enabled": true },
          { "codec": "vp9", "enabled": true },
          { "codec": "av01", "enabled": true }
        ],
        "audio_codec_preferences": [
          { "codec": "aac", "enabled": true },
          { "codec": "opus", "enabled": true },
          { "codec": "eac3", "enabled": true },
          { "codec": "ac3", "enabled": true },
          { "codec": "flac", "enabled": true },
          { "codec": "other", "enabled": true }
        ],
        "youtube_subtitles": false,
        "vod_style": "list",
        "sources": [
          {
            "id": "bilibili",
            "name": "Bilibili",
            "items": [
              {
                "url": "https://www.bilibili.com/video/BVxxxx",
                "title": "可选标题覆盖",
                "pic": "",
                "remarks": "合集"
              },
              {
                "name": "手动分组",
                "items": [
                  {
                    "url": "https://www.bilibili.com/bangumi/play/ss2493",
                    "title": "番剧 season"
                  }
                ]
              }
            ]
          }
        ]
      }
    },
    {
      "id": "alt",
      "type": "tvbox",
      "auth_mode": "anonymous",
      "tvbox": {
        "site_key": "dashbox-alt",
        "site_name": "Dashbox Alt",
        "locale": "en-US",
        "video_codec_preferences": [
          { "codec": "vp9", "enabled": true },
          { "codec": "h264", "enabled": true },
          { "codec": "hevc", "enabled": true },
          { "codec": "av01", "enabled": true }
        ],
        "audio_codec_preferences": [
          { "codec": "aac", "enabled": true },
          { "codec": "other", "enabled": true },
          { "codec": "opus", "enabled": false },
          { "codec": "eac3", "enabled": false },
          { "codec": "ac3", "enabled": false },
          { "codec": "flac", "enabled": false }
        ],
        "sources": [
          {
            "id": "youtube",
            "name": "YouTube",
            "items": [
              {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
              }
            ]
          }
        ]
      }
    }
  ]
}
```

`items[]` 只接受对象：

- URL 项必须有 `url`，可选 `title`、`pic`、`remarks`。没有 `title` 时会尽量从站点元数据解析标题。
- 文件夹项必须有 `name` 和 `items`，用于手动分组。
- 同一个条目不能同时有 `url` 和 `items`。
- `name` 只用于分类和文件夹，`title` 只用于 URL 内容入口；订阅本身只需要 `id`。
- B 站多 P、番剧 season、合集和其他站点播放列表都配置成 URL 项；解析出的分集会在详情页的选集里展示，不作为配置文件夹。

Kodi 订阅示例：

```json
{
  "subs": [
    {
      "id": "kodi-main",
      "type": "kodi",
      "auth_mode": "anonymous",
      "kodi": {
        "search_provider": "ytdlp",
        "ytdlp_search_prefix": {
          "mode": "youtube"
        },
        "sources": [
          {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "Pinned Video"
          },
          {
            "name": "YouTube",
            "items": [
              {
                "url": "https://www.youtube.com/@GoogleDevelopers/videos",
                "title": "Google Developers"
              }
            ]
          }
        ]
      }
    }
  ]
}
```

Kodi 顶层 `sources[]` 规则：

- 可以直接放 URL 项，首页会显示为可播放或可展开条目。
- 也可以放文件夹项，用于手动分组。
- 不需要像 TVBox 那样额外包一层 source/tab。

视频编码偏好也可以用别名：

```json
{
  "subs": [
    {
      "id": "main",
      "type": "tvbox",
      "auth_mode": "anonymous",
      "tvbox": {
        "site_key": "dashbox",
        "video_codec_preferences": [
          { "codec": "vp9", "enabled": true },
          { "codec": "h264", "enabled": true },
          { "codec": "hevc", "enabled": true },
          { "codec": "av01", "enabled": true }
        ],
        "sources": []
      }
    }
  ]
}
```

上面会归一化为 `["vp9", "h264", "hevc", "av01"]`。音频编码偏好里的 `other` 可以放在任意位置；放得越靠前，未列出的音频编码优先级越高。

访问码订阅示例：

```json
{
  "subs": [
    {
      "id": "private",
      "type": "tvbox",
      "auth_mode": "access_code",
      "access_code_hash": "$2b$12$...",
      "tvbox": {
        "site_key": "private",
        "sources": []
      }
    }
  ]
}
```

访问码只能是 4 到 12 位 ASCII 数字；服务端只接受 `$2a$`、`$2b$` 或 `$2y$` 前缀的 bcrypt 哈希。`/sub/{sub_id}` 仍是公开的薄 bootstrap 文档，不包含 `sources`、访问码哈希或真实媒体 URL；实际目录、搜索、详情和播放 API 会要求 token。

### TVBox 字幕返回

TVBox 播放接口返回字幕时：

- `subs` 是完整字幕列表。
- `subs[].ext` 保留原始短格式名，例如 `vtt`、`srt`、`ass`。
- `subs[].format` 使用 MIME，例如 `text/vtt`、`application/x-subrip`、`text/x-ssa`、`application/ttml+xml`，便于客户端按 MIME 判断字幕类型。

## YouTube 支持情况

YouTube 普通视频、Shorts、播放列表、搜索页、频道页和频道 tab 都可以作为 URL 项配置。播放列表、搜索页、频道视频页、频道 Shorts/直播/播放列表 tab 会作为目录展开；单个视频进入详情后播放。

YouTube Kids 支持普通视频、频道页和频道 videos tab。Kids 的首页、搜索、feed、hashtag、watchitagain、`playlist?list=...`、频道 streams/playlists tab、clip、live_stream embed 等入口没有作为稳定目录入口覆盖；其中 feed、playlist 和部分频道 tab 在网页上会回到 Kids 主页或由 yt-dlp 按 `youtube.com/...` 处理。

已识别为目录的 YouTube 特殊入口：

- `https://www.youtube.com/`：YouTube 首页推荐。yt-dlp 会转到 `feed/recommended`。
- `https://www.youtube.com/feed/recommended`：推荐 feed。
- `https://www.youtube.com/feed/subscriptions`：订阅更新，需要账号 cookies。
- `https://www.youtube.com/feed/history`：观看历史，需要账号 cookies。
- `https://www.youtube.com/feed/watch_later`：稍后观看 feed，需要账号 cookies。
- `https://www.youtube.com/playlist?list=LL`：喜欢的视频，需要账号 cookies。
- `https://www.youtube.com/playlist?list=WL`：稍后观看列表，需要账号 cookies。
- `https://www.youtube.com/hashtag/<tag>`：hashtag 聚合页，例如 `https://www.youtube.com/hashtag/cctv9`。

也支持 yt-dlp 的 YouTube 快捷入口，配置时会归一化到对应 URL：

- `:ytrec`、`:ytrecommended` -> `https://www.youtube.com/feed/recommended`
- `:ytsubs`、`:ytsubscriptions` -> `https://www.youtube.com/feed/subscriptions`
- `:ythis`、`:ythistory` -> `https://www.youtube.com/feed/history`
- `:ytfav`、`:ytfavorites` -> `https://www.youtube.com/playlist?list=LL`
- `:ytwatchlater` -> `https://www.youtube.com/playlist?list=WL`

账号态入口依赖 `cookies_from_browser`。例如：

```json
{
  "cookies_from_browser": {
    "mode": "firefox"
  }
}
```

推荐 feed 里可能混入 `RD...`、`RDMM...` 这类 YouTube Mix。dashbox 按普通条目处理这些 Mix，不把它们当子目录展开。`https://www.youtube.com/feed/trending` 当前在本机测试会被 YouTube 重定向到首页，并被 yt-dlp 判定为不存在，因此没有作为稳定入口覆盖。

YouTube 字幕选择规则：

- 优先返回与客户端语言偏好最接近的手动字幕。
- 同一语言下优先更通用的字幕格式；TVBox 返回时会把字幕 `format` 规范化成 MIME。
- TVBox 在没有命中手动字幕时，只会回退到自动生成的原文字幕，不会下发自动翻译字幕。
- Kodi 会保留全部手动字幕，并把匹配 UI 语言的字幕排在前面；只有没有手动字幕时才回退到自动生成的原文字幕。
