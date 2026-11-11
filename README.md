# 主动消息 Discord 版（astrbot_plugin_proactive_chat_discord）

[中文](README.md) | [English (upstream)](docs/upstream/README_EN.md) | [日本語 (upstream)](docs/upstream/README_JP.md)

> **这是上游 [Pancakes-Labs/astrbot_plugin_proactive_chat](https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat)（作者 DBJD-CR）的 Discord 衍生版。**
> 上游为 **AGPL-3.0**，本衍生版继续以 **AGPL-3.0** 发布，保留完整 LICENSE、版权与来源说明。
> 详细 fork 信息、上游 commit 与修改清单见 [UPSTREAM.md](UPSTREAM.md)。插件默认关闭，首次安装不会向任何人发消息。

## 功能

在保留上游核心逻辑的基础上，适配 **Discord**：

- **随机间隔 + 沉默触发**：私聊默认 30–600 分钟随机间隔（群聊 90–360），用户发消息后取消任务并重新随机排期；APScheduler 持久化任务，插件重载/重启可恢复。
- **自动触发 / 群沉默计时**：插件加载后 X 分钟无消息、或群/频道沉默 X 分钟后触发（默认关闭）。
- **免打扰 `quiet_hours`**：整点小时区间、支持跨天（如 `1-7`），命中时重排期不发送。
- **连续未回复上限 GATE**：私聊/群聊分别配置 `max_unanswered_times`，达到上限暂停，用户回复后重置。
- **人格**：优先使用该 AstrBot 会话绑定的人格，否则回退 `persona_manager.get_default_persona_v3(umo)` 的默认人格 prompt（插件不单独维护人格配置）。
- **上下文**：AstrBot 对话历史；可选 `conversation_history` / `platform_message_history` / `hybrid` 平台流水注入。
- **LLM**：使用当前会话 provider；`ProviderRequest` + LLM 钩子 + 工具调用拒绝；一次触发一次生成。
- **发送前二次确认**：模型生成期间用户发来新消息则丢弃本次主动消息。
- **发送失败重排期、不存档、不计数**；成功写回对话历史与平台流水。
- **TTS / 分段回复 / 装饰钩子**：保留上游能力（默认关闭，Discord 可分段发送）。
- **状态**：`data/plugin_data/astrbot_plugin_proactive_chat_discord/session_data.json` + 会话 override，持久化恢复。
- **WebUI 管理端**：默认 `127.0.0.1:4100`（容器内），配置密码后启用鉴权；不暴露公网。
- **默认安全**：顶层 `enabled=false`、`friend_settings.enable=false`、`group_settings.enable=false`、TTS/通知/遥测默认关闭。

## Discord 支持范围

| 能力 | 支持情况 |
| --- | --- |
| 私聊（DM）主动消息 | ✅ 支持；`fetch_user` → 复用 `dm_channel` 或 `create_dm()`，**从未私聊过的用户也能发起** |
| 群聊（频道）主动消息 | ✅ 支持按频道 ID 发送；语义是“频道广播”，不等同 QQ 群 @ 场景 |
| 目标配置 | 裸 Discord 用户 ID（私聊）/ 频道 ID（群聊）/ `discord:FriendMessage:<DM频道ID>` / `discord:GroupMessage:<频道ID>` |
| 多 Bot 选择 | `discord_settings.platform_id` 选择 AstrBot 已注册的 Discord 平台（留空=第一个就绪 bot），不会新建账号/token |
| 发送路径 | 优先 AstrBot `event.send` / `send_by_session`，失败后 Discord client 直发（`channel.send`）兜底 |
| 限流保护 | `dm_rate_limit_seconds`（默认 1 秒）与 `max_send_chars`（默认 1800，超出自动拆分） |
| 从未私聊用户 | ✅ `create_dm()`；若用户已屏蔽/关闭 DM 或 Bot 无权限，该目标跳过并告警 |
| 非文本消息 | Discord 直发目前只发送文本；图片/语音等组件会跳过并记录（AstrBot 路径可能仍可用） |

### Discord 配置步骤

1. 在 AstrBot 平台配置里已有可用的 Discord Bot（本插件不会创建新 bot/账号）。
2. 私聊目标：把 **Discord 用户 ID**（如 `1408751508585058384`）填入 `friend_settings.session_list`。
3. 群聊目标：把 **Discord 频道 ID**（如 `1566736267671113740`）填入 `group_settings.session_list`。
4. 视需要开启 `friend_settings.enable` / `group_settings.enable`，最后把顶层 `enabled` 打开。
5. 保存配置（或重载插件）；插件会 `fetch_user → create_dm` 解析目标并在日志中输出规范 UMO。

## 配置项

完整 Schema 见 [_conf_schema.json](_conf_schema.json)。主要项：

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `enabled` | `false` | **总开关**，默认关闭；关闭时不调度、不发送、不监听 |
| `discord_settings.platform_id` | `""` | 选择 AstrBot 已注册的 Discord Bot；留空=第一个就绪 |
| `discord_settings.resolve_targets_on_startup` | `true` | 启动时解析/创建 DM 频道 |
| `discord_settings.dm_rate_limit_seconds` | `1` | 同一 DM 两条消息最小间隔 |
| `discord_settings.max_send_chars` | `1800` | 单条消息最大字符数，超出拆分 |
| `friend_settings.enable` | `false` | 私聊主动消息开关 |
| `friend_settings.session_list` | `[]` | Discord 用户 ID / UMO 列表 |
| `friend_settings.schedule_settings.min_interval_minutes` | `30` | 私聊随机间隔下限 |
| `friend_settings.schedule_settings.max_interval_minutes` | `600` | 私聊随机间隔上限 |
| `friend_settings.schedule_settings.quiet_hours` | `"1-7"` | 免打扰小时区间（可跨天） |
| `friend_settings.schedule_settings.max_unanswered_times` | `4` | 连续未回复上限 |
| `friend_settings.proactive_prompt` | 见 Schema | 主动消息提示词（支持 `{{current_time}}`、`{{unanswered_count}}`） |
| `group_settings.*` | 群聊默认关闭 | 频道主动消息配置 |
| `web_admin.enabled` | `true` | WebUI，默认仅 127.0.0.1 |
| `notification_settings.enabled` | `false` | 通知中心，默认关闭 |
| `telemetry_config.enabled` | `false` | 匿名遥测，默认关闭 |

## 安装（AstrBot）

1. 将本目录放入 `data/plugins/astrbot_plugin_proactive_chat_discord/`；
2. 在 AstrBot Dashboard 插件管理上传 zip 安装或重载插件；
3. 配置 Discord 目标与开关后保存（总开关默认 `false`，不会自动发消息）；
4. WebUI：`http://127.0.0.1:4100`（容器内），可按需设置密码。

## 测试

```bash
# 纯逻辑测试（无 AstrBot 环境时自动跳过集成用例）
python -m pytest tests -q

# 容器内（AstrBot 4.29.4 / Python 3.12）
python -m pytest tests -q
```

测试使用 fake Discord client/channel，不连接真实 Discord，不使用个人账号。

## 回滚

- Dashboard 停用/卸载 `astrbot_plugin_proactive_chat_discord`；
- 删除插件目录后重载；
- 彻底清理：删除 `data/plugin_data/astrbot_plugin_proactive_chat_discord/` 与 `data/config/astrbot_plugin_proactive_chat_discord_config.json`。

## 许可证与归属

- 本插件是 [Pancakes-Labs/astrbot_plugin_proactive_chat](https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat)（DBJD-CR）的衍生作品，遵循 **AGPL-3.0**。
- 完整许可证：[LICENSE](LICENSE)；上游信息与修改清单：[UPSTREAM.md](UPSTREAM.md)。
- 第三方组件（Outfit 字体、依赖库）许可见 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
- 如果你通过网络向用户提供本插件服务，AGPL 要求你向这些用户提供对应源码。
