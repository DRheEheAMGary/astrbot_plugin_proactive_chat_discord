# 上游信息与 Discord 衍生说明

## 上游

- 仓库：https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat
  （原地址 `https://github.com/DBJD-CR/astrbot_plugin_proactive_chat`，GitHub 已重定向）
- 作者：DBJD-CR
- 许可证：GNU Affero General Public License v3.0（见 `LICENSE`）
- 本项目 fork 基线：`main` 分支 commit `554c5d07684258ab5df8b6f9edb5c8e28a7fc2a5`
  （2026-11-06，Merge PR #121），上游版本 `v1.3.0-beta.1`
- 上游文档快照：`docs/upstream/README_EN.md`、`docs/upstream/README_JP.md`
- 本衍生版：`astrbot_plugin_proactive_chat_discord`，版本 `v1.3.0-discord.1`

## AGPL-3.0 义务

- 本目录完整保留上游 `LICENSE`（AGPL-3.0），不得删除或替换。
- 本衍生版继续以 AGPL-3.0 授权；分发或通过网络提供服务时，须向接收者/网络用户提供对应完整源码。
- 保留原作者与来源标注；本文件与 README 即修改说明。

## 本衍生版修改清单（相对上游 commit 554c5d0）

1. **插件身份**：`metadata.yaml` 名称改为 `astrbot_plugin_proactive_chat_discord`，显示名/desc/版本调整；`support_platforms` 仅保留 `discord`；数据目录改为 `plugin_data/astrbot_plugin_proactive_chat_discord`。
2. **默认安全**：新增顶层总开关 `enabled=false`；`friend_settings.enable` 默认改为 `false`（上游为 `true`）；私聊 TTS 默认关闭；通知系统与匿名遥测默认关闭；其余默认值尽量与上游一致。
3. **Discord 目标适配**（新增 `core/discord/`）：
   - 目标解析：裸 Discord 用户 ID / 频道 ID / `discord:FriendMessage|GroupMessage:<ID>`；
   - 私聊目标通过 `fetch_user` → 复用 `dm_channel` 或 `create_dm()` 解析为规范 UMO `discord:FriendMessage:<dm_channel_id>`；
   - 群聊目标解析为 `discord:GroupMessage:<channel_id>`；
   - 目标映射缓存 `discord_targets.json`，启动时预解析，失败的目标跳过并告警，不会误发。
4. **Discord Bot 选择**：新增 `discord_settings.platform_id`，只从 AstrBot 已注册且就绪的 Discord 平台中选择；留空取第一个；配置不存在时跳过，不新建 bot/账号。
5. **Discord 发送层**：在原有 AstrBot `event.send` / `send_by_session` / 核心 API 兜底链路之外，为 Discord 增加 `channel.send` 直发兜底；含限流间隔、字符拆分、文本组件转换（非文本组件跳过并记录）。
6. **总开关热切换**：新增 10 秒配置观察循环，`enabled` 由关到开时恢复调度，由开到关时清理所有 job/计时器（保留持久化状态）。
7. **WebUI**：配置 API 与前端全局配置键新增 `enabled` / `discord_settings`；管理端标题改为 Discord 版；默认仍仅监听 `127.0.0.1:4100`。
8. **文档**：README 重写为 Discord 衍生版说明；新增本文件与 `THIRD_PARTY_LICENSES.md`；上游 EN/JP 文档移入 `docs/upstream/`。
9. **兼容性/测试**：按 AstrBot 4.29.4 做导入与行为冒烟；新增 `tests/`（fake Discord client，不连接真实账号）。

## 未修改 / 保留

- 上游的调度（APScheduler + 随机间隔 + 沉默/自动触发器）、未回复 GATE、上下文/人格、LLM 钩子、工具调用拒绝、状态合并、会话覆写、WebUI 状态页、通知中心与遥测代码均保留。
- 上游 logo 与字体资源保留（字体许可见 THIRD_PARTY_LICENSES.md）。
