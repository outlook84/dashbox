# 安装与启动

Dashbox 需要 Python 3.11 或更新版本。从源码开发还需要 Node.js 22.13 或更新版本
以及 `pnpm` 10.33.4。

启动 Dashbox 时请显式设置 `--public-base-url`，值为客户端实际访问 Dashbox 的
完整地址，例如 `http://192.168.6.10:18990` 或反向代理后的 HTTPS 域名。
Dashbox 会用它生成 TVBox Spider URL、媒体辅助 URL、Kodi repository 元数据和其他
自引用链接；未设置或设置成服务端内部地址时，客户端可能无法访问这些链接。

## 从 PyPI 安装

稳定部署推荐使用 PyPI 包：

```bash
uv tool install dashbox --prerelease=allow
dashbox --data-dir data --host 0.0.0.0 --port 18990 --public-base-url http://192.168.6.10:18990
```

升级 Dashbox：

```bash
uv tool upgrade dashbox --prerelease=allow
```

Dashbox 默认依赖 `yt-dlp[default,curl-cffi]`。站点解析失效时，可以强制重装
`uv tool` 管理的独立环境并刷新 `yt-dlp`：

```bash
uv tool install --force dashbox --upgrade-package yt-dlp --prerelease=allow
```

## 从源码运行

从源码运行、构建前端资源、执行测试和更新源码环境依赖，见 [开发](development.md)。

## 数据目录和管理界面

推荐以 data dir 方式启动：

```bash
dashbox --data-dir data --host 0.0.0.0 --port 18990 --public-base-url http://192.168.6.10:18990
```

此时 Dashbox 会读取 `data/config.json`；文件不存在时自动生成最小配置。管理界面：

```text
http://<server>:18990/admin
```

首次使用时，服务会在数据目录生成 admin setup code。用它设置 admin access code
后，后续登录使用 admin access code。

也可以使用显式配置文件启动：

```bash
dashbox -c config.json --host 0.0.0.0 --port 18990 --public-base-url http://192.168.6.10:18990
```

`DASHBOX_UPSTREAM_TIMEOUT`、`DASHBOX_UNSAFE_IMAGE_PROXY_MODE` 等其他运行参数见
[配置字段](config-fields.md)。

## 反向代理或局域网访问

如果客户端访问 Dashbox 的地址和服务端内部看到的地址不同，请设置公开访问基准
URL：

```bash
dashbox --data-dir data --public-base-url http://192.168.6.10:18990
```

也可以使用 `DASHBOX_PUBLIC_BASE_URL`。
