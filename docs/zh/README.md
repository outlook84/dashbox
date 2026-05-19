# Dashbox 中文文档

[English](../../README.md)

Dashbox 是一个面向 TVBox 与 Kodi 的由 `yt-dlp` 驱动的媒体服务。它可以统一管理
视频源，并把内容提供给 TVBox 订阅和 Kodi 插件使用。

- [安装与启动](installation.md)：从 PyPI 安装、从源码运行、启动服务、升级
  Dashbox 和 yt-dlp、使用管理界面。
- [TVBox 与 Kodi 客户端配置](client-setup.md)：把 TVBox 订阅和 Kodi 插件连到
  Dashbox 服务。
- [配置字段](config-fields.md)：JSON 配置结构、环境变量和前端 tooltip 短说明。
- [开发](development.md)：仓库结构、构建、测试和生成资产。

## 项目概览

Dashbox 服务端会调用 `yt-dlp` 解析视频页面、频道、播放列表、搜索结果和部分
站点专属列表，并向客户端返回目录、详情和播放信息。

当前能力包括：

- TVBox 订阅和内置 Spider JS。
- Kodi 插件和内置 repository 入口。
- Vue 管理界面，用于编辑持久化配置。
- HLS、progressive 直链、DASH manifest 和可选 DASH 分片代理。
- 图片代理、YouTube 字幕、Bilibili 弹幕/字幕辅助能力。

推荐先阅读 [安装与启动](installation.md)，启动后进入 `/admin` 配置订阅，再按
[客户端配置](client-setup.md) 接入 TVBox 或 Kodi。
