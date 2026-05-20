# TVBox and Kodi Client Setup

Dashbox serves different client protocols from the same source configuration.
Use `type: "tvbox"` subscriptions for TVBox/CatVodSpider clients, and
`type: "kodi"` subscriptions for the Kodi add-on.

## Kodi

Dashbox exposes a Kodi repository package at:

```text
http://<server>:18990/repo.zip
```

Install that repository package in Kodi, then install the Dashbox video add-on
from the repository.

Configure the add-on settings:

- Server URL: `http://<server>:18990`
- Subscription id: the `id` of a `type: "kodi"` subscription
- Access code: only needed when the subscription uses access-code auth

If Dashbox's public base URL changes after the repository has been installed,
reinstall the Dashbox repository package from the new `/repo.zip` URL and update
the add-on's Server URL setting manually.

The Kodi add-on calls Dashbox's `/api/v1/subs/<sub-id>/...` endpoints. Kodi-side
playback settings such as video height, frame rate, codec preference, danmaku,
and YouTube subtitles are sent with playback requests.

## TVBox

The following TVBox app shells have been tested:

- [takagen99/Box](https://github.com/takagen99/Box)
- [FongMi/TV](https://github.com/FongMi/TV)

Create or edit a TVBox subscription in the admin UI, then add this URL to the
TVBox client:

```text
http://<server>:18990/sub/<tvbox-sub-id>
```

For example:

```text
http://192.168.6.10:18990/sub/main
```

The subscription response points the client at Dashbox's built-in spider bundle
and passes the matching server endpoint in the spider `ext` payload.

If the subscription uses `auth_mode: "access_code"`, the TVBox spider prompts
for the access code inside the client. 
