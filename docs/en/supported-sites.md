# Supported Websites

Dashbox delegates media playback resolution to `yt-dlp`. In addition to generic `yt-dlp` parsing, Dashbox includes specialized site adapters under `dashbox/sites/` to parse directory hierarchies, lists, channels, searches, and playlists, and to handle other features like danmaku (弹幕), subtitles, and image proxying.

Some URLs (such as YouTube's Watch Later) require cookies to be configured in the Dashbox options to resolve properly.

Below is the detailed list of supported websites, their URL formats, and other features.

---

## 1. YouTube

- **Domains**: `youtube.com`, `music.youtube.com`, `youtubekids.com`
- **Supported URL Formats**:
  - **Single Video**: 
    - Standard: `https://www.youtube.com/watch?v={video_id}`
    - Shortened: `https://youtu.be/{video_id}`
    - Embeds, Shorts (`/shorts/{video_id}`), and YouTube Kids channel videos.
  - **Playlists**: `https://www.youtube.com/playlist?list={playlist_id}`
  - **Channel Tabs**: Channel homepages, `/videos`, `/shorts`, `/streams`, `/playlists`, and `/podcasts` tabs.
  - **Search Queries**: `https://www.youtube.com/results?search_query={keyword}` and YouTube Music searches.
  - **Dashbox Shortcuts (Pseudo-URLs)**:
    - `:ytrec` / `:ytrecommended` — Recommended feed
    - `:ytsub` / `:ytsubs` / `:ytsubscription` / `:ytsubscriptions` — Subscriptions feed
    - `:ythis` / `:ythistory` — Playback history
    - `:ytfav` / `:ytfavs` / `:ytfavorite` / `:ytfavorites` — Liked videos (requires configured auth/cookies)
    - `:ytwatchlater` — Watch Later playlist (requires configured auth/cookies)
- **Subtitles**: Support for displaying video subtitles on clients. Note that auto-translated subtitles are currently not supported.

---

## 2. Bilibili (哔哩哔哩)

- **Domains**: `bilibili.com`, `b23.tv` (shortened link resolution)
- **Supported URL Formats**:
  - **Single Video**: BV/AV video pages (e.g. `https://www.bilibili.com/video/BV...`), player embeds (`player.bilibili.com`), dynamics (`t.bilibili.com/{id}`), articles (`/opus/{id}`), and festival/event pages.
  - **Live Streams**: `https://live.bilibili.com/{room_id}` and `/blanc/{room_id}`.
  - **Audio**: Single audio track (`/audio/au...`) and audio albums (`/audio/am...`).
  - **Professional Content**: Bangumi episodes (`/bangumi/play/ep...`), Bangumi seasons (`/bangumi/play/ss...`), Bangumi media details (`/bangumi/media/md...`), Cheese (courses) episodes (`/cheese/play/ep...`), and Cheese seasons (`/cheese/play/ss...`).
  - **User Playlists & Feeds**:
    - Watch Later (`/watchlater`, `/list/watchlater`, `/medialist/play/watchlater`).
    - Favorites (`/medialist/detail/ml...` or user space favlist query).
    - Medialists (`/medialist/play/ml...`, `/list/...`).
    - User Space Collections (`/channel/collectiondetail?sid=...` or `/lists/...`).
    - User Space Series (`/channel/seriesdetail?sid=...` or `/lists/...` with type=series).
    - Space Audio uploads (`/space.bilibili.com/{mid}/audio`).
  - **Search Queries**: Bilibili search pages (e.g. `https://search.bilibili.com/all?keyword={keyword}`).
  - **Taxonomies**: Main categories and sub-categories (`/v/{category}/{subcategory}`).
- **Danmaku (弹幕)**: Automatic retrieval of danmaku and conversion to client-friendly format.

---

## 3. Twitch

- **Domains**: `twitch.tv`, `clips.twitch.tv`, `player.twitch.tv`
- **Supported URL Formats**:
  - **Live Streams**: `https://twitch.tv/{channel_name}` or player `https://player.twitch.tv/?channel={channel_name}`
  - **VODs (Videos)**: `https://twitch.tv/videos/{video_id}`, `/v/{video_id}`, or `/video/{video_id}` paths.
  - **Clips**: `https://clips.twitch.tv/{clip_id}` or channel clips `/clip/{clip_id}`.
  - **Collections**: `https://twitch.tv/collections/{collection_id}`.
  - **Channel Video Tabs**: Channel videos page (`/videos`), profile (`/profile`), and clips (`/clips`).

---

## 4. Pornhub

- **Domains**: `pornhub.com`, `pornhub.net`, `pornhub.org`, `pornhubpremium.com`, and the official Onion domain `pornhubvybmsymdol4iibwgwtkpwmeyd6luq2gxajgjzfjvotyt5zhyd.onion`.
- **Supported URL Formats**:
  - **Single Video**: `/view_video.php?viewkey={id}`, `/video/show?viewkey={id}`, or `/embed/{id}` embeds.
  - **Search Queries**: `/video/search?search={keyword}`.
  - **Categories**: `/categories/{name}`.
  - **Creators/Models**: Models (`/model/{name}`), pornstars (`/pornstar/{name}`), users (`/users/{name}`), and channels (`/channels/{name}`).
  - **Playlists**: `/playlist/{id}`.
  - **Others**: HD section (`/hd`) and Described videos (`/described-video`).
- **Image Proxying**: Proxies preview images from `phncdn.com` using correct referer headers.

---

## 5. SpankBang

- **Domains**: `spankbang.com`
- **Supported URL Formats**:
  - **Playlists**: `https://spankbang.com/{id}/playlist/{slug}` or `/playlist/...`
  - **Single Videos**: Standard video detail pages.
- **Image Proxying**: Proxies cover images from `sb-cd.com` using correct referers.

---

## 6. XVideos

- **Domains**: `xvideos.com`, `xvideos2.com`, `xvideos.es`
- **Supported URL Formats**:
  - **Single Video**: Video details path (e.g. `/video...`), embeds `/embedframe/`, or Quickies paths `quickies/a/...`.
  - **Favorites Playlists**: User favorite pages `/favorite/{id}`.

---

## 7. Generic Fallback

- **Domains**: Any valid HTTP/HTTPS URL not matched by the adapters above.
- **Supported URL Formats**: URLs supported by `yt-dlp`.
