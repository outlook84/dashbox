# 开发

Dashbox 是 Python 与 TypeScript 混合仓库。

## 目录结构

- `dashbox/`：Python 包和运行时代码。
- `dashbox/server/`：FastAPI app、CLI、静态路由、认证、媒体/图片代理和 Kodi
  repository 入口。
- `dashbox/core/`：共享的来源导航、详情、搜索和播放流程。
- `dashbox/adapters/`：TVBox 和 Kodi 协议适配。
- `dashbox/media/`：yt-dlp 集成、DASH/HLS 处理、媒体缓存和播放选择。
- `dashbox/config/`：配置模型、解析、序列化、校验和管理界面 schema。
- `dashbox/kodi/`：随 Python 包发布的 Kodi 插件源码。
- `apps/admin/`：Vue/Vite 管理界面。
- `apps/tvbox/`：TypeScript TVBox/CatVodSpider runtime。
- `tests/`：Python 测试。
- `scripts/`：构建、打包和审计脚本。

## 初始化

```bash
uv sync --extra dev
pnpm install
```

本地启动后端：

```bash
uv run dashbox --data-dir data --port 18990
```

启动管理界面开发服务：

```bash
pnpm run dev
```

## 构建

```bash
pnpm run build:spider
pnpm run build:admin
pnpm run build
```

生成的管理界面写入 `dashbox/assets/admin`。生成的 TVBox Spider 写入
`dashbox/assets/dashbox.<hash>.js`。

打包 Kodi 插件：

```bash
uv run python scripts/package_kodi_plugin.py
```

## 检查

```bash
uv run pytest
pnpm run lint
pnpm run typecheck
pnpm run test
```

常用聚焦检查：

```bash
uv run pytest tests/config/test_config_items.py
pnpm run test:admin
pnpm run test:tvbox
pnpm run typecheck:admin
pnpm run typecheck:tvbox
pnpm run lint:admin
pnpm run lint:tvbox
```

## 更新源码环境里的 yt-dlp

源码环境依赖版本由 `uv.lock` 固定。升级 stable 通道：

```bash
uv lock --upgrade-package yt-dlp
uv sync
```

允许 yt-dlp 预发布修复：

```bash
uv lock --upgrade-package yt-dlp --prerelease allow
uv sync
```
