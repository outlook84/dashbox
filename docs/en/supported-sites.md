# Supported Websites

Dashbox delegates media playback resolution to `yt-dlp`. In addition to generic
`yt-dlp` extraction, Dashbox includes site adapters under `dashbox/sites/` for
site-specific directories, lists, channels, searches, playlists, danmaku,
subtitles, and image proxying.

Some URLs require matching cookies in the Dashbox configuration before they can
be resolved, such as YouTube's Watch Later playlist.

## YouTube

| Area | Support |
| --- | --- |
| Domains | `youtube.com`, `music.youtube.com`, `youtubekids.com` |
| Videos | Standard watch pages `https://www.youtube.com/watch?v={video_id}`, short links `https://youtu.be/{video_id}`, embeds, Shorts, and YouTube Kids channel videos |
| Lists and channels | Playlists, channel homepages, `/videos`, `/shorts`, `/streams`, `/playlists`, `/podcasts` |
| Search | `https://www.youtube.com/results?search_query={keyword}` and YouTube Music search |
| Shortcuts | `:ytrec`, `:ytrecommended`, `:ytsub`, `:ytsubs`, `:ytsubscription`, `:ytsubscriptions`, `:ythis`, `:ythistory`, `:ytfav`, `:ytfavs`, `:ytfavorite`, `:ytfavorites`, `:ytwatchlater` |
| Extra features | YouTube subtitles. Auto-translated subtitles are not currently supported |

`:ytfav`, `:ytfavs`, `:ytfavorite`, `:ytfavorites`, and `:ytwatchlater` require
configured login cookies or credentials.

## Bilibili

| Area | Support |
| --- | --- |
| Domains | `bilibili.com`, `b23.tv`, with shortened link resolution |
| Videos | BV/AV video pages, `player.bilibili.com` embeds, dynamics, articles/Opus pages, and festival/event pages |
| Live and audio | `https://live.bilibili.com/{room_id}`, `/blanc/{room_id}`, single audio `/audio/au...`, audio albums `/audio/am...` |
| Professional content | Bangumi episodes, Bangumi seasons, Bangumi media details, Cheese course episodes, and Cheese seasons |
| User content | Watch Later, favorites, medialists, user space video uploads `https://space.bilibili.com/{mid}`, `/{mid}/video`, `/{mid}/upload/video`, user space collections, user space series, and space audio uploads `/{mid}/audio`, `/{mid}/upload/audio` |
| Search and categories | Bilibili search pages, main categories, and sub-categories `/v/{category}/{subcategory}` |
| Extra features | Automatic danmaku retrieval and conversion to a client-friendly format |

## Twitch

| Area | Support |
| --- | --- |
| Domains | `twitch.tv`, `clips.twitch.tv`, `player.twitch.tv` |
| Live streams | `https://twitch.tv/{channel_name}` and `https://player.twitch.tv/?channel={channel_name}` |
| VODs | `https://twitch.tv/videos/{video_id}`, `/v/{video_id}`, `/video/{video_id}` |
| Clips and collections | `https://clips.twitch.tv/{clip_id}`, channel clips `/clip/{clip_id}`, collections `/collections/{collection_id}` |
| Channel pages | Channel videos `/videos`, profile `/profile`, clips `/clips` |

## Pornhub

| Area | Support |
| --- | --- |
| Domains | `pornhub.com`, `pornhub.net`, `pornhub.org`, `pornhubpremium.com`, and the official Onion domain |
| Videos | `/view_video.php?viewkey={id}`, `/video/show?viewkey={id}`, embeds `/embed/{id}` |
| Discovery | Search `/video/search?search={keyword}`, categories `/categories/{name}`, HD section `/hd`, described videos `/described-video` |
| Creator content | Models `/model/{name}`, pornstars `/pornstar/{name}`, users `/users/{name}`, channels `/channels/{name}` |
| Playlists | `/playlist/{id}` |
| Extra features | Proxies preview images from `phncdn.com` with the correct Referer request header |

## SpankBang

| Area | Support |
| --- | --- |
| Domains | `spankbang.com` |
| Videos and lists | Standard video detail pages, plus `https://spankbang.com/{id}/playlist/{slug}` or `/playlist/...` playlists |
| Extra features | Proxies cover images from `sb-cd.com` with the correct Referer request header |

## XVideos

| Area | Support |
| --- | --- |
| Domains | `xvideos.com`, `xvideos2.com`, `xvideos.es` |
| Videos | Video detail paths, embeds `/embedframe/`, Quickies paths `quickies/a/...` |
| Playlists | User favorite pages `/favorite/{id}` |

## Generic Fallback

Any valid HTTP/HTTPS URL not matched by the adapters above is handled by generic
`yt-dlp` extraction.
