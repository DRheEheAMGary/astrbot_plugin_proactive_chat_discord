"""Discord 目标与会话标识解析（纯逻辑，便于单测）。

上游使用 AstrBot UMO：``platform:MessageType:target``。
Discord 私聊的真实 UMO 第三段是 **DM 频道 ID**（不是用户 ID），
因此这里负责把用户配置的「裸用户 ID / 裸频道 ID / discord UMO」解析成
可被上游调度器使用的规范 UMO。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DISCORD_PLATFORM_ID = "discord"
FRIEND_MESSAGE = "FriendMessage"
GROUP_MESSAGE = "GroupMessage"

_SNOWFLAKE_RE = re.compile(r"^\d{15,21}$")
_UMO_RE = re.compile(
    r"^(?P<platform>[^:]+):(?P<msg_type>FriendMessage|PrivateMessage|GroupMessage|GuildMessage):(?P<target>.+)$",
    re.IGNORECASE,
)
_PREFIX_RE = re.compile(r"^(?P<prefix>user|channel|discord):(?P<rest>.+)$", re.IGNORECASE)


def looks_like_snowflake(value: object) -> bool:
    """是否为 Discord snowflake（15~21 位纯数字）。"""
    return bool(_SNOWFLAKE_RE.fullmatch(str(value or "").strip()))


def is_discord_umo(umo: object) -> bool:
    text = str(umo or "").strip()
    match = _UMO_RE.match(text)
    return bool(match and match.group("platform").lower() == DISCORD_PLATFORM_ID)


def parse_discord_umo(umo: object) -> tuple[str, str, str] | None:
    """解析 discord UMO，返回 ``(platform, message_type, target)``。"""
    text = str(umo or "").strip()
    match = _UMO_RE.match(text)
    if not match:
        return None
    if match.group("platform").lower() != DISCORD_PLATFORM_ID:
        return None
    return (
        match.group("platform"),
        match.group("msg_type"),
        match.group("target").strip(),
    )


@dataclass(frozen=True)
class DiscordTarget:
    """一个 Discord 目标配置项。"""

    raw: str
    """原始配置值（日志/状态展示用）。"""

    kind: str
    """dm_user / dm_channel / group_channel / discord_umo。"""

    target_id: str
    """裸用户 ID 或频道 ID。"""

    message_type: str
    """FriendMessage / GroupMessage。"""

    platform_id: str = DISCORD_PLATFORM_ID

    @property
    def is_friend(self) -> bool:
        return self.message_type in {FRIEND_MESSAGE, "PrivateMessage"}

    @property
    def is_group(self) -> bool:
        return self.message_type in {GROUP_MESSAGE, "GuildMessage"}


def parse_target(raw: object, default_message_type: str = FRIEND_MESSAGE) -> DiscordTarget | None:
    """解析目标配置项。

    支持：
    - ``123456789012345678``（裸 ID，按 default_message_type 视为用户或频道）
    - ``user:123...`` / ``channel:123...``
    - ``discord:FriendMessage:<用户ID或DM频道ID>``
    - ``discord:GroupMessage:<频道ID>``
    返回 None 表示不是 Discord 目标（交给上游原有逻辑处理）或格式非法。
    """
    text = str(raw or "").strip()
    if not text:
        return None

    # 已是 UMO
    parsed = _UMO_RE.match(text)
    if parsed:
        platform = parsed.group("platform")
        if platform.lower() != DISCORD_PLATFORM_ID:
            return None
        msg_type = parsed.group("msg_type")
        target_id = parsed.group("target").strip()
        if not looks_like_snowflake(target_id):
            return None
        canonical_type = (
            GROUP_MESSAGE
            if msg_type.lower() in {"groupmessage", "guildmessage"}
            else FRIEND_MESSAGE
        )
        kind = "discord_umo"
        if canonical_type == GROUP_MESSAGE:
            kind = "group_channel"
        return DiscordTarget(
            raw=text,
            kind=kind,
            target_id=target_id,
            message_type=canonical_type,
        )

    # user:/channel: 前缀
    prefix_match = _PREFIX_RE.match(text)
    if prefix_match:
        prefix = prefix_match.group("prefix").lower()
        target_id = prefix_match.group("rest").strip()
        if not looks_like_snowflake(target_id):
            return None
        if prefix == "user":
            return DiscordTarget(text, "dm_user", target_id, FRIEND_MESSAGE)
        if prefix == "channel":
            return DiscordTarget(text, "group_channel", target_id, GROUP_MESSAGE)
        # discord: 前缀但缺少消息类型：按默认类型处理
        kind = "dm_user" if default_message_type == FRIEND_MESSAGE else "group_channel"
        return DiscordTarget(text, kind, target_id, default_message_type)

    # 裸 ID
    if looks_like_snowflake(text):
        if default_message_type == FRIEND_MESSAGE:
            return DiscordTarget(text, "dm_user", text, FRIEND_MESSAGE)
        return DiscordTarget(text, "group_channel", text, GROUP_MESSAGE)

    return None


def canonical_umo(message_type: str, target_id: str, platform_id: str = DISCORD_PLATFORM_ID) -> str:
    """拼接规范 UMO。"""
    return f"{platform_id}:{message_type}:{target_id}"
