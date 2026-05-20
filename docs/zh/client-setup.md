# TVBox 与 Kodi 客户端配置

Dashbox 使用同一套 source 配置向不同客户端提供协议入口。`type: "tvbox"` 用于
TVBox/CatVodSpider 客户端，`type: "kodi"` 用于 Kodi 插件。

## TVBox

在管理界面创建或编辑 TVBox 订阅后，把下面的地址加入 TVBox 客户端：

```text
http://<server>:18990/sub/<tvbox-sub-id>
```

例如：

```text
http://192.168.6.10:18990/sub/main
```

订阅响应会指向 Dashbox 内置的 Spider JS，并通过 Spider `ext` 传入对应的服务端
接口。

如果订阅使用 `auth_mode: "access_code"`，TVBox Spider 会在客户端内提示输入访问码。

## Kodi

Dashbox 提供 Kodi repository 包：

```text
http://<server>:18990/repo.zip
```

在 Kodi 中安装该 repository 包，然后从 repository 安装 Dashbox 视频插件。

插件设置里填写：

- Server URL：`http://<server>:18990`
- Subscription id：`type: "kodi"` 订阅的 `id`
- Access code：仅在该订阅启用访问码认证时填写

如果安装 repository 后 Dashbox 的公开访问 URL 发生变化，请从新的 `/repo.zip`
重新安装 Dashbox repository 包，并手动更新插件设置里的 Server URL。

Kodi 插件会调用 Dashbox 的 `/api/v1/subs/<sub-id>/...` 接口。Kodi 端的播放设置
例如视频高度、帧率、编码偏好、弹幕和 YouTube 字幕，会在播放请求中传给服务端。
