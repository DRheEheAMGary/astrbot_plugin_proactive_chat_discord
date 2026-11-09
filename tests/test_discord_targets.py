"""Discord 目标解析纯逻辑测试（不依赖 AstrBot）。"""

from __future__ import annotations

import pytest

from astrbot_plugin_proactive_chat_discord.core.discord.targets import (
    FRIEND_MESSAGE,
    GROUP_MESSAGE,
    canonical_umo,
    is_discord_umo,
    looks_like_snowflake,
    parse_discord_umo,
    parse_target,
)

USER_ID = "1408751508585058384"
CHANNEL_ID = "1566736267671113740"


def test_looks_like_snowflake() -> None:
    assert looks_like_snowflake(USER_ID)
    assert not looks_like_snowflake(123)  # int 转字符串后长度不足
    assert not looks_like_snowflake("123")
    assert not looks_like_snowflake("abc")
    assert not looks_like_snowflake(None)


def test_parse_bare_user_id_as_friend() -> None:
    target = parse_target(USER_ID, FRIEND_MESSAGE)
    assert target is not None
    assert target.kind == "dm_user"
    assert target.target_id == USER_ID
    assert target.is_friend and not target.is_group


def test_parse_bare_channel_id_as_group() -> None:
    target = parse_target(CHANNEL_ID, GROUP_MESSAGE)
    assert target is not None
    assert target.kind == "group_channel"
    assert target.is_group


def test_parse_prefixed_ids() -> None:
    assert parse_target(f"user:{USER_ID}").kind == "dm_user"
    assert parse_target(f"channel:{CHANNEL_ID}", FRIEND_MESSAGE).kind == "group_channel"


def test_parse_discord_umo() -> None:
    friend = parse_target(f"discord:FriendMessage:{USER_ID}")
    assert friend is not None and friend.is_friend and friend.kind == "discord_umo"
    group = parse_target(f"discord:GroupMessage:{CHANNEL_ID}")
    assert group is not None and group.is_group
    assert is_discord_umo(f"discord:FriendMessage:{USER_ID}")
    assert parse_discord_umo(f"discord:FriendMessage:{USER_ID}") == (
        "discord",
        "FriendMessage",
        USER_ID,
    )


def test_parse_non_discord_returns_none() -> None:
    assert parse_target("default:FriendMessage:123456789") is None
    assert parse_target("qq:FriendMessage:abc") is None
    assert parse_target("") is None
    assert parse_target("not-an-id") is None


def test_invalid_discord_umo_returns_none() -> None:
    assert parse_target("discord:FriendMessage:abc") is None
    assert parse_target("discord:GroupMessage:short") is None


def test_canonical_umo() -> None:
    assert canonical_umo(FRIEND_MESSAGE, USER_ID) == f"discord:FriendMessage:{USER_ID}"
    assert canonical_umo(GROUP_MESSAGE, CHANNEL_ID) == f"discord:GroupMessage:{CHANNEL_ID}"


def test_parse_discord_umo_requires_discord_platform() -> None:
    assert parse_discord_umo("other:FriendMessage:123456789012345678") is None
    assert not is_discord_umo("other:FriendMessage:123456789012345678")


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
