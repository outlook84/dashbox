# 支持的网站

Dashbox 的媒体播放解析委托给 `yt-dlp`。除通用的 `yt-dlp` 解析外，Dashbox
还在 `dashbox/sites/` 下提供专属站点适配器，用于解析目录、列表、频道、搜索、
播放列表，以及弹幕、字幕和图片代理等站点特性。

部分 URL 需要在 Dashbox 配置中提供对应 Cookie 才能正常解析，例如 YouTube 的
稍后观看列表。

## YouTube

| 项目 | 支持情况 |
| --- | --- |
| 域名 | `youtube.com`, `music.youtube.com`, `youtubekids.com` |
| 视频 | 标准播放页 `https://www.youtube.com/watch?v={video_id}`、短链接 `https://youtu.be/{video_id}`、嵌入播放页、Shorts 和 YouTube Kids 频道视频 |
| 列表和频道 | 播放列表、频道主页、`/videos`、`/shorts`、`/streams`、`/playlists`、`/podcasts` |
| 搜索 | `https://www.youtube.com/results?search_query={keyword}` 和 YouTube Music 搜索 |
| 快捷入口 | `:ytrec`, `:ytrecommended`, `:ytsub`, `:ytsubs`, `:ytsubscription`, `:ytsubscriptions`, `:ythis`, `:ythistory`, `:ytfav`, `:ytfavs`, `:ytfavorite`, `:ytfavorites`, `:ytwatchlater` |
| 附加能力 | YouTube 字幕。自动翻译字幕暂不支持 |

`:ytfav`、`:ytfavs`、`:ytfavorite`、`:ytfavorites` 和 `:ytwatchlater` 需要配置
登录 Cookie 或凭据。

## Bilibili

| 项目 | 支持情况 |
| --- | --- |
| 域名 | `bilibili.com`, `b23.tv`，支持短链接重定向解析 |
| 视频 | BV/AV 视频页、`player.bilibili.com` 嵌入页、动态、专栏/Opus、节日活动页 |
| 直播和音频 | `https://live.bilibili.com/{room_id}`、`/blanc/{room_id}`、单音频 `/audio/au...`、音频歌单 `/audio/am...` |
| 专业内容 | 番剧/影视集数、番剧季度、番剧媒体详情、课堂课程集数和课程季度 |
| 用户内容 | 稍后观看、个人收藏夹、播单、用户空间投稿 `https://space.bilibili.com/{mid}`、`/{mid}/video`、`/{mid}/upload/video`、用户空间合集、用户空间系列、用户空间音频投稿 `/{mid}/audio`、`/{mid}/upload/audio` |
| 搜索和分区 | 哔哩哔哩搜索页，以及主分区和子分区 `/v/{category}/{subcategory}` |
| 附加能力 | 自动获取弹幕并转换为客户端支持的格式 |

## Twitch

| 项目 | 支持情况 |
| --- | --- |
| 域名 | `twitch.tv`, `clips.twitch.tv`, `player.twitch.tv` |
| 直播 | `https://twitch.tv/{channel_name}` 和 `https://player.twitch.tv/?channel={channel_name}` |
| 录像 | `https://twitch.tv/videos/{video_id}`、`/v/{video_id}`、`/video/{video_id}` |
| 剪辑和合集 | `https://clips.twitch.tv/{clip_id}`、频道剪辑 `/clip/{clip_id}`、合集 `/collections/{collection_id}` |
| 频道页面 | 频道录像页 `/videos`、简介 `/profile`、剪辑 `/clips` |

## Pornhub

| 项目 | 支持情况 |
| --- | --- |
| 域名 | `pornhub.com`, `pornhub.net`, `pornhub.org`, `pornhubpremium.com`，以及官方 Onion 域名 |
| 视频 | `/view_video.php?viewkey={id}`、`/video/show?viewkey={id}`、嵌入播放 `/embed/{id}` |
| 发现入口 | 搜索 `/video/search?search={keyword}`、分类 `/categories/{name}`、HD 分区 `/hd`、旁白解说视频 `/described-video` |
| 创作者内容 | 模特 `/model/{name}`、演员 `/pornstar/{name}`、用户 `/users/{name}`、频道 `/channels/{name}` |
| 播放列表 | `/playlist/{id}` |
| 附加能力 | 代理 `phncdn.com` 视频预览图，并自动附加正确 Referer 请求头 |

## SpankBang

| 项目 | 支持情况 |
| --- | --- |
| 域名 | `spankbang.com` |
| 视频和列表 | 标准视频播放详情页，以及 `https://spankbang.com/{id}/playlist/{slug}` 或 `/playlist/...` 播放列表 |
| 附加能力 | 代理 `sb-cd.com` 封面图，并自动携带正确 Referer 请求头 |

## XVideos

| 项目 | 支持情况 |
| --- | --- |
| 域名 | `xvideos.com`, `xvideos2.com`, `xvideos.es` |
| 视频 | 视频播放页路径、嵌入页 `/embedframe/`、Quickies 路径 `quickies/a/...` |
| 播放列表 | 用户收藏夹页面 `/favorite/{id}` |

## 通用备用解析

未匹配以上专属适配器的有效 HTTP/HTTPS 链接会交给 `yt-dlp` 通用解析。
