# 第三方组件与许可证

本插件主体遵循 AGPL-3.0（见 `LICENSE`）。以下为随附或运行时依赖的第三方组件说明。

## 随附资源

| 组件 | 位置 | 许可证 | 说明 |
| --- | --- | --- | --- |
| Outfit 字体（Outfit Thin/Light/Regular/Medium/SemiBold/Bold/ExtraBold） | `admin/fonts/` | SIL Open Font License 1.1 (OFL-1.1) | 由 Smartsheet / Rodrigo Fuenzalida 设计；OFL 允许随软件嵌入/打包，需保留版权与许可声明。上游仓库未附 OFL 文本，本衍生版在此补充声明。 |
| 上游 logo | `logo.png` | 随上游仓库 AGPL-3.0 | 来源于上游仓库，保留原样。 |

> 注：Outfit 字体的 OFL 文本可在 https://openfontlicense.org 获取；如再分发本插件，请一并保留本声明与 OFL 链接。

## 运行时依赖（requirements.txt）

| 依赖 | 用途 | 许可证 |
| --- | --- | --- |
| `apscheduler` | 持久化定时任务 | MIT |
| `aiofiles` | 异步状态文件读写 | Apache-2.0 |
| `fastapi` | 插件自带 WebUI | MIT |
| `uvicorn` | WebUI ASGI 服务 | BSD-3-Clause |
| `tomli`（Python < 3.11） | TOML 解析 | MIT |

上述许可证均与 AGPL-3.0 兼容，不构成额外分发限制。AstrBot 本体及其自带依赖（discord.py/pycord、aiohttp 等）遵循其各自许可证。

## 前端外部资源

`admin/index.html` 通过 CDN 加载 React / Material UI 等前端资源（与上游一致），这些资源遵循各自开源许可证；离线环境需自行镜像。若需完全离线部署，可将相关资源本地化后使用。
