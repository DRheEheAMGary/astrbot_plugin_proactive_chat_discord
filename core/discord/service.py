"""Discord Bot 选择、DM 通道解析、发送与目标映射服务。

这是本 Discord 衍生版相对上游新增的适配层，负责：

1. 从 AstrBot 已注册平台实例中选择 Discord Bot（不新建账号/token）；
2. 把配置里的裸用户 ID / 裸频道 ID / ``discord:...`` UMO 解析为
   AstrBot 可用的规范 UMO（私聊第三段为 DM 频道 ID）；
3. 发送消息链（优先复用 AstrBot 的 event.send / send_by_session 路径，
   由 SenderService 编排；本服务提供必要的 Discord client 直发兜底）；
4. 缓存「配置值 -> 规范 UMO」映射，供调度器/配置匹配同步查询。

本模块不依赖 discord.py 的具体类型，全部使用鸭子类型，便于 fake client 测试。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .targets import (
    DISCORD_PLATFORM_ID,
    FRIEND_MESSAGE,
    GROUP_MESSAGE,
    DiscordTarget,
    canonical_umo,
    is_discord_umo,
    parse_discord_umo,
    parse_target,
)

CACHE_FILENAME = "discord_targets.json"


def _meta_id(platform: Any) -> str:
    meta = getattr(platform, "meta", None)
    if callable(meta):
        try:
            metadata = meta()
        except Exception:
            metadata = None
        if metadata is not None:
            value = getattr(metadata, "id", None)
            if value:
                return str(value).strip()
    config = getattr(platform, "config", {}) or {}
    return str(config.get("id") or "").strip()


def _platform_type(platform: Any) -> str:
    config = getattr(platform, "config", {}) or {}
    return str(config.get("type") or "").lower()


def _client_is_discord(client: Any) -> bool:
    if client is None:
        return False
    return client.__class__.__name__ in {"DiscordBotClient", "Bot", "Client"}


def _client_ready(client: Any) -> bool:
    if getattr(client, "user", None) is None:
        return False
    is_ready = getattr(client, "is_ready", None)
    if callable(is_ready):
        try:
            return bool(is_ready())
        except Exception:
            return True
    return True


def _is_dm_channel(channel: Any) -> bool:
    """鸭子类型判断是否为 Discord 私聊频道。"""
    if channel is None:
        return False
    if getattr(channel, "guild", None) is not None:
        return False
    return callable(getattr(channel, "send", None))


def chain_to_text(components: list[Any]) -> str:
    """把 AstrBot 消息链组件转成 Discord 文本（非文本组件跳过并告警）。"""
    parts: list[str] = []
    skipped: list[str] = []
    for component in components or []:
        text = getattr(component, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
            continue
        skipped.append(component.__class__.__name__)
    if skipped:
        logger.debug(
            "[主动消息] Discord 直发暂不支持的消息组件已跳过喵: %s",
            ", ".join(sorted(set(skipped))),
        )
    return "".join(parts).strip()


class DiscordTargetService:
    """Discord 目标解析与发送适配服务。"""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self._umo_map: dict[str, str] = {}
        """原始配置值 -> 规范 UMO。"""

        self._raw_by_umo: dict[str, list[str]] = {}
        self._user_by_umo: dict[str, str] = {}
        # 已解析的频道对象缓存（DM/频道）。真实 Discord client 会缓存 DMChannel，
        # 这里缓存对象可在 fetch 失败时仍复用；发送失败由调用方重排期。
        self._channel_cache: dict[str, Any] = {}
        self._cache_path: Path = Path(plugin.data_dir) / CACHE_FILENAME
        self._last_send_at: dict[str, float] = {}
        self._skipped: dict[str, str] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # 配置 / 缓存
    # ------------------------------------------------------------------
    @property
    def settings(self) -> dict:
        value = self.plugin.config.get("discord_settings", {})
        return value if isinstance(value, dict) else {}

    def _configured_platform_id(self) -> str:
        return str(self.settings.get("platform_id") or "").strip()

    def _rate_limit_seconds(self) -> float:
        try:
            return max(0.0, float(self.settings.get("dm_rate_limit_seconds", 1)))
        except (TypeError, ValueError):
            return 1.0

    def _max_send_chars(self) -> int:
        try:
            return max(100, int(self.settings.get("max_send_chars", 1800)))
        except (TypeError, ValueError):
            return 1800

    def _load_cache(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            if not self._cache_path.exists():
                return
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            entries = data.get("targets") if isinstance(data, dict) else None
            if isinstance(entries, dict):
                for raw, item in entries.items():
                    if isinstance(item, dict) and item.get("umo"):
                        self._record(raw, str(item["umo"]), str(item.get("user_id") or ""))
        except Exception as exc:
            logger.warning(f"[主动消息] 读取 Discord 目标缓存失败喵: {exc}")

    def _save_cache(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "updated_at": time.time(),
                "targets": {
                    raw: {
                        "umo": umo,
                        "user_id": self._user_by_umo.get(umo, ""),
                        "updated_at": time.time(),
                    }
                    for raw, umo in self._umo_map.items()
                },
            }
            tmp = self._cache_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._cache_path)
        except Exception as exc:
            logger.warning(f"[主动消息] 写入 Discord 目标缓存失败喵: {exc}")

    def _record(self, raw: str, umo: str, user_id: str = "") -> None:
        self._umo_map[raw] = umo
        self._raw_by_umo.setdefault(umo, [])
        for candidate in {raw, umo}:
            if candidate not in self._raw_by_umo[umo]:
                self._raw_by_umo[umo].append(candidate)
        if user_id:
            self._user_by_umo[umo] = user_id

    # ------------------------------------------------------------------
    # Bot 选择
    # ------------------------------------------------------------------
    def _iter_discord_platforms(self) -> list[tuple[str, Any, Any]]:
        manager = getattr(getattr(self.plugin, "context", None), "platform_manager", None)
        instances = getattr(manager, "platform_insts", None)
        if instances is None:
            getter = getattr(manager, "get_insts", None)
            try:
                instances = getter() if callable(getter) else []
            except Exception:
                instances = []
        result: list[tuple[str, Any, Any]] = []
        seen_clients: set[int] = set()
        for platform in instances or []:
            client = getattr(platform, "client", None)
            if client is None or id(client) in seen_clients:
                continue
            platform_type = _platform_type(platform)
            if "discord" not in platform_type and not _client_is_discord(client):
                continue
            platform_id = _meta_id(platform) or DISCORD_PLATFORM_ID
            if not _client_ready(client):
                continue
            seen_clients.add(id(client))
            result.append((platform_id, platform, client))
        return result

    def select_platform(self) -> tuple[str, Any, Any] | None:
        """选择 Discord 平台；配置了 platform_id 时绝不回退到其他 bot。"""
        platforms = self._iter_discord_platforms()
        if not platforms:
            logger.warning("[主动消息] 未找到已就绪的 Discord 平台实例喵。")
            return None
        configured = self._configured_platform_id()
        if not configured:
            return platforms[0]
        for platform_id, platform, client in platforms:
            if platform_id == configured:
                return platform_id, platform, client
        available = ", ".join(item[0] for item in platforms)
        logger.warning(
            "[主动消息] discord_settings.platform_id=%r 未找到已就绪的 Discord bot"
            "（当前可用: %s），本轮跳过且不会误用其他 bot 喵。",
            configured,
            available,
        )
        return None

    def selected_platform_id(self) -> str:
        selected = self.select_platform()
        return selected[0] if selected else ""

    def ready_platform_ids(self) -> list[str]:
        return [item[0] for item in self._iter_discord_platforms()]

    # ------------------------------------------------------------------
    # UMO 解析
    # ------------------------------------------------------------------
    @staticmethod
    def parse_config_target(raw: Any, message_type: str = FRIEND_MESSAGE) -> DiscordTarget | None:
        return parse_target(raw, message_type)

    def is_discord_session(self, session_id: Any) -> bool:
        text = str(session_id or "").strip()
        if not text:
            return False
        if is_discord_umo(text):
            return True
        return text in self._raw_by_umo or text in self._umo_map.values()

    def mapped_umo(self, raw: Any) -> str | None:
        """查询配置值对应的规范 UMO（未解析则返回 None）。"""
        text = str(raw or "").strip()
        if not text:
            return None
        return self._umo_map.get(text)

    def canonical_umo_for(self, message_type: str, target_id: str) -> str | None:
        """同步查询规范 UMO（供上游 resolve_full_umo 使用）。"""
        target = str(target_id or "").strip()
        if not target:
            return None
        for raw, umo in self._umo_map.items():
            parsed = parse_discord_umo(umo)
            if parsed and parsed[2] == target and (
                (message_type in {FRIEND_MESSAGE, "PrivateMessage"} and parsed[1] in {FRIEND_MESSAGE, "PrivateMessage"})
                or (message_type in {GROUP_MESSAGE, "GuildMessage"} and parsed[1] in {GROUP_MESSAGE, "GuildMessage"})
            ):
                return umo
        if message_type in {GROUP_MESSAGE, "GuildMessage"}:
            return canonical_umo(GROUP_MESSAGE, target)
        return None

    def raw_keys_for_umo(self, umo: str) -> list[str]:
        return list(self._raw_by_umo.get(str(umo or "").strip(), []))

    # ------------------------------------------------------------------
    # 启动解析
    # ------------------------------------------------------------------
    async def prepare_startup_targets(self) -> None:
        """解析已启用私聊/群聊配置中的 Discord 目标并缓存映射。

        其他平台 UMO 由上游逻辑处理，这里只处理 Discord 目标。
        """
        self._load_cache()
        friend_settings = self.plugin.config.get("friend_settings", {}) or {}
        group_settings = self.plugin.config.get("group_settings", {}) or {}
        tasks: list[tuple[str, Any]] = []
        if friend_settings.get("enable", False):
            for raw in friend_settings.get("session_list", []) or []:
                tasks.append((FRIEND_MESSAGE, raw))
        if group_settings.get("enable", False):
            for raw in group_settings.get("session_list", []) or []:
                tasks.append((GROUP_MESSAGE, raw))

        if not tasks:
            logger.info("[主动消息] 没有需要解析的 Discord 目标喵。")
            return

        selected = self.select_platform()
        if selected is None:
            return
        platform_id, _platform, client = selected
        resolved = 0
        for message_type, raw in tasks:
            target = self.parse_config_target(raw, message_type)
            if target is None:
                if is_discord_umo(raw):
                    logger.warning(
                        "[主动消息] Discord 目标格式非法，已跳过喵: %r", raw
                    )
                continue
            umo = await self._resolve_target(client, platform_id, raw, target)
            if umo:
                resolved += 1
                logger.info(
                    "[主动消息] 已解析 Discord 目标 %r -> %s 喵", raw, umo
                )
            else:
                self._skipped[str(raw)] = "无法解析目标（用户/频道不存在或 DM 无法创建）"
        self._save_cache()
        logger.info(
            "[主动消息] Discord 目标解析完成：成功 %d / 共 %d（跳过 %d）喵。",
            resolved,
            len(tasks),
            len(self._skipped),
        )

    async def _resolve_target(
        self,
        client: Any,
        platform_id: str,
        raw: Any,
        target: DiscordTarget,
    ) -> str | None:
        text = str(raw).strip()
        if target.is_group:
            channel = await self._get_channel(client, target.target_id)
            if channel is None:
                logger.warning(
                    "[主动消息] Discord 频道 %s 不存在或 Bot 无权访问，已跳过喵。",
                    target.target_id,
                )
                return None
            umo = canonical_umo(GROUP_MESSAGE, str(getattr(channel, "id", target.target_id)), platform_id)
            self._record(text, umo)
            self._channel_cache[umo] = channel
            return umo

        # 私聊：目标第三段可能是 DM 频道 ID，也可能是用户 ID
        channel = await self._get_channel(client, target.target_id)
        if _is_dm_channel(channel):
            umo = canonical_umo(FRIEND_MESSAGE, str(getattr(channel, "id", target.target_id)), platform_id)
            self._record(text, umo)
            self._channel_cache[umo] = channel
            return umo

        # 当作 Discord 用户 ID：fetch_user -> create_dm
        return await self._resolve_user_dm(client, platform_id, text, target.target_id)

    async def _resolve_user_dm(
        self,
        client: Any,
        platform_id: str,
        raw: str,
        user_id: str,
    ) -> str | None:
        user = None
        try:
            user = client.get_user(int(user_id))
        except Exception:
            user = None
        if user is None:
            fetch_user = getattr(client, "fetch_user", None)
            if callable(fetch_user):
                try:
                    user = await fetch_user(int(user_id))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "[主动消息] fetch_user(%s) 失败，无法创建 DM 喵: %s",
                        user_id,
                        exc,
                    )
                    return None
        if user is None:
            logger.warning("[主动消息] 找不到 Discord 用户 %s，已跳过喵。", user_id)
            return None

        channel = getattr(user, "dm_channel", None)
        if channel is None:
            creator = getattr(user, "create_dm", None)
            if not callable(creator):
                logger.warning(
                    "[主动消息] Discord 用户 %s 无法创建 DM 通道，已跳过喵。", user_id
                )
                return None
            try:
                channel = await creator()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "[主动消息] create_dm(%s) 失败，已跳过喵: %s", user_id, exc
                )
                return None
        if channel is None:
            return None
        umo = canonical_umo(FRIEND_MESSAGE, str(getattr(channel, "id", user_id)), platform_id)
        self._record(raw, umo, user_id=user_id)
        self._channel_cache[umo] = channel
        return umo

    async def _get_channel(self, client: Any, channel_id: str) -> Any:
        getter = getattr(client, "get_channel", None)
        if callable(getter):
            try:
                channel = getter(int(channel_id))
                if channel is not None:
                    return channel
            except Exception:
                pass
        fetcher = getattr(client, "fetch_channel", None)
        if callable(fetcher):
            try:
                return await fetcher(int(channel_id))
            except asyncio.CancelledError:
                raise
            except Exception:
                return None
        return None

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------
    async def send_chain(self, session_id: str, components: list[Any]) -> bool:
        """Discord 直发消息链；成功返回 True，失败返回 False。"""
        if not self.plugin.is_plugin_enabled():
            logger.debug("[主动消息] 插件未启用，跳过 Discord 发送喵。")
            return False

        parsed = parse_discord_umo(session_id)
        if parsed is None:
            return False
        platform_id, message_type, target_id = parsed
        selected = self.select_platform()
        if selected is None:
            return False
        selected_platform_id, _platform, client = selected
        if platform_id and selected_platform_id != platform_id:
            logger.warning(
                "[主动消息] 会话平台 %s 与选择的 Discord bot %s 不一致，跳过发送喵。",
                platform_id,
                selected_platform_id,
            )
            return False

        channel = self._channel_cache.get(session_id)
        if channel is None:
            channel = await self._get_channel(client, target_id)
        if channel is None and message_type in {FRIEND_MESSAGE, "PrivateMessage"}:
            # 兼容旧状态里存的是用户 ID 的情况
            fallback_user_id = self._user_by_umo.get(session_id, target_id)
            channel = await self._dm_channel_for_user(client, fallback_user_id)
        if channel is not None and callable(getattr(channel, "send", None)):
            self._channel_cache[session_id] = channel
        if channel is None:
            logger.warning(
                "[主动消息] 找不到 Discord 会话 %s 的频道，发送失败喵。", session_id
            )
            return False

        text = chain_to_text(components)
        if not text:
            logger.warning("[主动消息] Discord 消息为空，跳过发送喵。")
            return False

        await self._respect_rate_limit(session_id)
        try:
            for chunk in self._split_text(text):
                await channel.send(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[主动消息] Discord 发送失败喵: %s", exc)
            return False
        self._last_send_at[session_id] = time.monotonic()
        logger.info(
            "[主动消息] 已通过 Discord bot %s 发送到 %s 喵。",
            selected_platform_id,
            session_id,
        )
        return True

    async def _dm_channel_for_user(self, client: Any, user_id: str) -> Any:
        user = None
        try:
            user = client.get_user(int(user_id))
        except Exception:
            user = None
        if user is None:
            fetch_user = getattr(client, "fetch_user", None)
            if callable(fetch_user):
                try:
                    user = await fetch_user(int(user_id))
                except Exception:
                    return None
        if user is None:
            return None
        channel = getattr(user, "dm_channel", None)
        if channel is None:
            creator = getattr(user, "create_dm", None)
            if callable(creator):
                try:
                    channel = await creator()
                except Exception:
                    return None
        return channel

    def _split_text(self, text: str) -> list[str]:
        limit = self._max_send_chars()
        if len(text) <= limit:
            return [text]
        return [text[i : i + limit] for i in range(0, len(text), limit)]

    async def _respect_rate_limit(self, session_id: str) -> None:
        limit = self._rate_limit_seconds()
        if limit <= 0:
            return
        last = self._last_send_at.get(session_id)
        if last is None:
            return
        wait = limit - (time.monotonic() - last)
        if wait > 0:
            await asyncio.sleep(wait)

    # ------------------------------------------------------------------
    # 状态展示
    # ------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        return {
            "platform_id": self._configured_platform_id(),
            "available_platform_ids": self.ready_platform_ids(),
            "resolved_targets": dict(self._umo_map),
            "skipped_targets": dict(self._skipped),
        }
