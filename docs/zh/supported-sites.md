# 支持的网站

Dashbox 的媒体播放解析委托给 `yt-dlp` 进行。除了通用的 `yt-dlp` 解析外，Dashbox 还在 `dashbox/sites/` 下包含了一系列专属的网站适配器（Site Adapters），用于解析目录结构、列表、频道、搜索和播放列表，并支持弹幕、字幕与图片代理等功能。

部分 URL（例如 YouTube 的“稍后观看”列表）需要先在 Dashbox 的配置中设置对应的 Cookie，方可正常解析。

以下是支持的网站列表、URL 匹配格式及其它功能的详细说明。

---

## 1. YouTube

- **匹配域名**：`youtube.com`, `music.youtube.com`, `youtubekids.com`
- **支持的 URL 格式**：
  - **单视频**：
    - 标准播放页：`https://www.youtube.com/watch?v={video_id}`
    - 短链接：`https://youtu.be/{video_id}`
    - 嵌入播放页、Shorts 短视频 (`/shorts/{video_id}`) 以及 YouTube Kids 频道视频。
  - **播放列表**：`https://www.youtube.com/playlist?list={playlist_id}`
  - **频道标签页**：频道主页、`/videos`、`/shorts`、`/streams`、`/playlists` 和 `/podcasts` 标签页。
  - **搜索查询**：`https://www.youtube.com/results?search_query={keyword}` 以及 YouTube Music 搜索。
  - **Dashbox 快捷入口 (伪 URL)**：
    - `:ytrec` / `:ytrecommended` —— 推荐视频流
    - `:ytsub` / `:ytsubs` / `:ytsubscription` / `:ytsubscriptions` —— 订阅视频流
    - `:ythis` / `:ythistory` —— 播放历史记录
    - `:ytfav` / `:ytfavs` / `:ytfavorite` / `:ytfavorites` —— 我喜欢的视频（需在配置中携带登录 Cookie/凭据）
    - `:ytwatchlater` —— 稍后观看列表（需在配置中携带登录 Cookie/凭据）
- **字幕支持**：支持在客户端上获取并显示视频字幕。目前尚不支持自动翻译的字幕。

---

## 2. Bilibili (哔哩哔哩)

- **匹配域名**：`bilibili.com`, `b23.tv`（支持短链接重定向解析）
- **支持的 URL 格式**：
  - **单视频**：BV/AV 视频页面（如 `https://www.bilibili.com/video/BV...`）、嵌入播放页 (`player.bilibili.com`)、动态 (`t.bilibili.com/{id}`)、专栏/Opus 页面 (`/opus/{id}`) 以及节日活动页面。
  - **直播**：`https://live.bilibili.com/{room_id}` 和 `/blanc/{room_id}`。
  - **音频**：单音频 (`/audio/au...`) 及音频歌单 (`/audio/am...`)。
  - **专业及影视内容**：番剧/影视集数 (`/bangumi/play/ep...`)、番剧季度 (`/bangumi/play/ss...`)、番剧媒体详情页 (`/bangumi/media/md...`)、课堂课程集数 (`/cheese/play/ep...`) 以及课程季度 (`/cheese/play/ss...`)。
  - **用户播放列表与订阅**：
    - 稍后观看（`/watchlater`、`/list/watchlater`、`/medialist/play/watchlater`）。
    - 个人收藏夹（`/medialist/detail/ml...` 或用户空间收藏夹列表）。
    - 播单（`/medialist/play/ml...`、`/list/...`）。
    - 用户空间合集（`/channel/collectiondetail?sid=...` 或 `/lists/...`）。
    - 用户空间系列（`/channel/seriesdetail?sid=...` 或 `/lists/...` 且参数 type=series）。
    - 用户空间音频投稿（`/space.bilibili.com/{mid}/audio`）。
  - **搜索查询**：哔哩哔哩搜索页面（如 `https://search.bilibili.com/all?keyword={keyword}`）。
  - **分区索引**：主分区与子分区（`/v/{category}/{subcategory}`）。
- **弹幕**：自动获取弹幕并转换为客户端支持的格式。

---

## 3. Twitch

- **匹配域名**：`twitch.tv`, `clips.twitch.tv`, `player.twitch.tv`
- **支持的 URL 格式**：
  - **直播**：`https://twitch.tv/{channel_name}` 或嵌入式播放器 `https://player.twitch.tv/?channel={channel_name}`
  - **录像 (VOD)**：`https://twitch.tv/videos/{video_id}`、`/v/{video_id}` 或 `/video/{video_id}` 路径。
  - **剪辑 (Clips)**：`https://clips.twitch.tv/{clip_id}` 或频道剪辑 `/clip/{clip_id}`。
  - **合集 (Collections)**：`https://twitch.tv/collections/{collection_id}`。
  - **频道视频标签页**：频道录像页 (`/videos`)、简介 (`/profile`) 和剪辑 (`/clips`)。

---

## 4. Pornhub

- **匹配域名**：`pornhub.com`, `pornhub.net`, `pornhub.org`, `pornhubpremium.com` 及官方 Onion 域名 `pornhubvybmsymdol4iibwgwtkpwmeyd6luq2gxajgjzfjvotyt5zhyd.onion`。
- **支持的 URL 格式**：
  - **单视频**：`/view_video.php?viewkey={id}`、`/video/show?viewkey={id}` 或嵌入播放 `/embed/{id}`。
  - **搜索查询**：`/video/search?search={keyword}`。
  - **分类**：`/categories/{name}`。
  - **创作者/模特**：模特 (`/model/{name}`)、演员 (`/pornstar/{name}`)、用户 (`/users/{name}`) 和频道 (`/channels/{name}`)。
  - **播放列表**：`/playlist/{id}`。
  - **其他**：HD 分区 (`/hd`) 以及旁白解说视频 (`/described-video`)。
- **图片代理**：代理 `phncdn.com` 的视频预览图，自动附加 correct referer 请求头。

---

## 5. SpankBang

- **匹配域名**：`spankbang.com`
- **支持的 URL 格式**：
  - **播放列表**：`https://spankbang.com/{id}/playlist/{slug}` 或 `/playlist/...`
  - **单视频**：标准视频播放详情页。
- **图片代理**：代理 `sb-cd.com` 的封面图，自动携带正确的 Referer 头。

---

## 6. XVideos

- **匹配域名**：`xvideos.com`, `xvideos2.com`, `xvideos.es`
- **支持的 URL 格式**：
  - **单视频**：视频播放页路径（如 `/video...`）、嵌入页 `/embedframe/`以及 Quickies 路径 `quickies/a/...`。
  - **个人收藏夹**：用户收藏夹页面 `/favorite/{id}`。

---

## 7. 通用备用解析 (Generic Fallback)

- **匹配域名**：未匹配以上专属适配器的任何有效 HTTP/HTTPS 链接。
- **支持的 URL 格式**：被 `yt-dlp` 支持的网站。
