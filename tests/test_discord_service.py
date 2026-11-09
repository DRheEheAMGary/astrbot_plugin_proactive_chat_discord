"""Discord 适配服务测试（可用 fake client，无需 AstrBot/真实 Discord）。

依赖 AstrBot 的 logger 等导入；如果本机未安装 AstrBot 会自动跳过。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ASTRBOT_AVAILABLE = importlib.util.find_spec("astrbot") is not None
pytestmark = pytest.mark.skipif(
    not ASTRBOT_AVAILABLE, reason="需要 AstrBot 运行环境（容器内执行）"
)

from astrbot_plugin_proactive_chat_discord.core.discord.service import (  # noqa: E402
    DiscordTargetService,
)
from astrbot_plugin_proactive_chat_discord.core.discord.targets import (  # noqa: E402
    FRIEND_MESSAGE,
    GROUP_MESSAGE,
)

USER_ID = "1408751508585058384"
OTHER_USER_ID = "1566740117752651776"
CHANNEL_ID = "1566736267671113740"


class FakeChannel:
    def __init__(self, channel_id: int, *, guild=None, fail: bool = False) -> None:
        self.id = channel_id
        self.guild = guild
        self.fail = fail
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        if self.fail:
            raise RuntimeError("fake discord send failure")
        self.sent.append(text)


class FakeUser:
    def __init__(self, user_id: int, dm_channel: FakeChannel | None = None) -> None:
        self.id = user_id
        self.dm_channel = dm_channel
        self.create_dm_calls = 0

    async def create_dm(self) -> FakeChannel:
        self.create_dm_calls += 1
        if self.dm_channel is None:
            self.dm_channel = FakeChannel(900000000000000000 + self.id)
        return self.dm_channel


class FakeClient:
    def __init__(
        self,
        *,
        users: dict[int, FakeUser] | None = None,
        channels: dict[int, FakeChannel] | None = None,
        ready: bool = True,
    ) -> None:
        self.user = object() if ready else None
        self.users = dict(users or {})
        self.channels = dict(channels or {})

    async def fetch_user(self, user_id: int) -> FakeUser:
        user = self.users.get(user_id)
        if user is None:
            raise LookupError(f"unknown user {user_id}")
        return user

    def get_user(self, user_id: int) -> FakeUser | None:
        return self.users.get(user_id)

    def get_channel(self, channel_id: int) -> FakeChannel | None:
        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id: int) -> FakeChannel:
        channel = self.channels.get(channel_id)
        if channel is None:
            raise LookupError(f"unknown channel {channel_id}")
        return channel

    def is_ready(self) -> bool:
        return self.user is not None


class FakePlatform:
    def __init__(self, client: FakeClient, platform_id: str = "discord") -> None:
        self.client = client
        self.config = {"type": "discord", "id": platform_id}

    def meta(self):
        return SimpleNamespace(id=self.config["id"])


class FakePlugin:
    def __init__(self, config: dict, data_dir: Path, platforms: list[FakePlatform]) -> None:
        self.config = config
        self.data_dir = Path(data_dir)
        self.context = SimpleNamespace(
            platform_manager=SimpleNamespace(platform_insts=platforms)
        )

    def is_plugin_enabled(self) -> bool:
        return bool(self.config.get("enabled", False))


def _config(**overrides) -> dict:
    base = {
        "enabled": True,
        "friend_settings": {"enable": True, "session_list": [USER_ID]},
        "group_settings": {"enable": False, "session_list": []},
        "discord_settings": {
            "platform_id": "",
            "resolve_targets_on_startup": True,
            "dm_rate_limit_seconds": 0,
            "max_send_chars": 1800,
        },
    }
    base.update(overrides)
    return base


def _make_plugin(tmp_path: Path, *, config: dict | None = None, platforms=None) -> FakePlugin:
    if platforms is None:
        user = FakeUser(int(USER_ID))
        client = FakeClient(users={int(USER_ID): user})
        platforms = [FakePlatform(client)]
    return FakePlugin(config or _config(), tmp_path, platforms)


def test_prepare_targets_creates_dm_for_never_dmed_user(tmp_path: Path) -> None:
    plugin = _make_plugin(tmp_path)
    service = DiscordTargetService(plugin)
    user = plugin.context.platform_manager.platform_insts[0].client.users[int(USER_ID)]

    asyncio.run(service.prepare_startup_targets())

    assert user.create_dm_calls == 1
    umo = service.mapped_umo(USER_ID)
    assert umo is not None
    assert umo.startswith("discord:FriendMessage:")
    assert umo.endswith(str(user.dm_channel.id))
    # 缓存文件已写入
    cache = json.loads((tmp_path / "discord_targets.json").read_text(encoding="utf-8"))
    assert USER_ID in cache["targets"]


def test_prepare_targets_reuses_existing_dm_channel(tmp_path: Path) -> None:
    channel = FakeChannel(111111111111111111)
    user = FakeUser(int(USER_ID), dm_channel=channel)
    client = FakeClient(users={int(USER_ID): user})
    plugin = _make_plugin(tmp_path, platforms=[FakePlatform(client)])
    service = DiscordTargetService(plugin)

    asyncio.run(service.prepare_startup_targets())

    assert user.create_dm_calls == 0
    assert service.mapped_umo(USER_ID) == f"discord:FriendMessage:{channel.id}"


def test_prepare_targets_resolves_group_channel(tmp_path: Path) -> None:
    channel = FakeChannel(int(CHANNEL_ID), guild=object())
    client = FakeClient(channels={int(CHANNEL_ID): channel})
    config = _config(
        friend_settings={"enable": False, "session_list": []},
        group_settings={"enable": True, "session_list": [CHANNEL_ID]},
    )
    plugin = _make_plugin(tmp_path, config=config, platforms=[FakePlatform(client)])
    service = DiscordTargetService(plugin)

    asyncio.run(service.prepare_startup_targets())

    assert service.mapped_umo(CHANNEL_ID) == f"discord:GroupMessage:{CHANNEL_ID}"


def test_unknown_user_is_skipped(tmp_path: Path) -> None:
    client = FakeClient(users={})
    plugin = _make_plugin(tmp_path, platforms=[FakePlatform(client)])
    service = DiscordTargetService(plugin)

    asyncio.run(service.prepare_startup_targets())

    assert service.mapped_umo(USER_ID) is None
    assert USER_ID in service.describe()["skipped_targets"]


def test_select_platform_by_id_and_missing(tmp_path: Path) -> None:
    client_a = FakeClient(users={int(USER_ID): FakeUser(int(USER_ID))})
    client_b = FakeClient(users={int(USER_ID): FakeUser(int(USER_ID))})
    platforms = [FakePlatform(client_a, "discord"), FakePlatform(client_b, "discord-b")]
    plugin = _make_plugin(
        tmp_path,
        config=_config(
            discord_settings={
                "platform_id": "discord-b",
                "dm_rate_limit_seconds": 0,
                "max_send_chars": 1800,
            }
        ),
        platforms=platforms,
    )
    service = DiscordTargetService(plugin)
    selected = service.select_platform()
    assert selected is not None and selected[0] == "discord-b"

    plugin.config["discord_settings"]["platform_id"] = "not-exist"
    assert service.select_platform() is None


def test_send_chain_sends_text(tmp_path: Path) -> None:
    channel = FakeChannel(222222222222222222)
    user = FakeUser(int(USER_ID), dm_channel=channel)
    client = FakeClient(users={int(USER_ID): user})
    plugin = _make_plugin(tmp_path, platforms=[FakePlatform(client)])
    service = DiscordTargetService(plugin)

    async def scenario() -> None:
        await service.prepare_startup_targets()
        umo = service.mapped_umo(USER_ID)
        assert umo is not None
        ok = await service.send_chain(umo, [SimpleNamespace(text="你好呀")])
        assert ok is True
        assert channel.sent == ["你好呀"]

    asyncio.run(scenario())


def test_send_chain_respects_disabled_switch(tmp_path: Path) -> None:
    channel = FakeChannel(333333333333333333)
    user = FakeUser(int(USER_ID), dm_channel=channel)
    client = FakeClient(users={int(USER_ID): user})
    plugin = _make_plugin(tmp_path, platforms=[FakePlatform(client)])
    service = DiscordTargetService(plugin)

    async def scenario() -> None:
        await service.prepare_startup_targets()
        umo = service.mapped_umo(USER_ID)
        plugin.config["enabled"] = False
        ok = await service.send_chain(umo, [SimpleNamespace(text="不应发送")])
        assert ok is False
        assert channel.sent == []

    asyncio.run(scenario())


def test_send_chain_splits_long_text(tmp_path: Path) -> None:
    channel = FakeChannel(444444444444444444)
    user = FakeUser(int(USER_ID), dm_channel=channel)
    client = FakeClient(users={int(USER_ID): user})
    config = _config(
        discord_settings={
            "platform_id": "",
            "dm_rate_limit_seconds": 0,
            "max_send_chars": 100,
        }
    )
    plugin = _make_plugin(tmp_path, config=config, platforms=[FakePlatform(client)])
    service = DiscordTargetService(plugin)

    async def scenario() -> None:
        await service.prepare_startup_targets()
        umo = service.mapped_umo(USER_ID)
        text = "a" * 250
        ok = await service.send_chain(umo, [SimpleNamespace(text=text)])
        assert ok is True
        assert [len(item) for item in channel.sent] == [100, 100, 50]
        assert "".join(channel.sent) == text

    asyncio.run(scenario())


def test_send_chain_missing_channel_fails(tmp_path: Path) -> None:
    client = FakeClient(users={}, channels={})
    plugin = _make_plugin(tmp_path, platforms=[FakePlatform(client)])
    service = DiscordTargetService(plugin)

    async def scenario() -> None:
        # 未解析、缓存与 Discord 侧都不存在的频道：发送必须失败而不是误发
        ok = await service.send_chain(
            "discord:FriendMessage:555555555555555555",
            [SimpleNamespace(text="测试")],
        )
        assert ok is False

    asyncio.run(scenario())


def test_cache_reload_across_service_instances(tmp_path: Path) -> None:
    user = FakeUser(int(USER_ID))
    channel = FakeChannel(666666666666666666)
    user.dm_channel = channel
    client = FakeClient(users={int(USER_ID): user})
    plugin = _make_plugin(tmp_path, platforms=[FakePlatform(client)])
    first = DiscordTargetService(plugin)

    async def prepare() -> None:
        await first.prepare_startup_targets()

    asyncio.run(prepare())
    expected = first.mapped_umo(USER_ID)

    second = DiscordTargetService(plugin)
    second._load_cache()
    assert second.mapped_umo(USER_ID) == expected


def test_non_discord_session_not_sent(tmp_path: Path) -> None:
    user = FakeUser(int(USER_ID))
    client = FakeClient(users={int(USER_ID): user})
    plugin = _make_plugin(tmp_path, platforms=[FakePlatform(client)])
    service = DiscordTargetService(plugin)

    async def scenario() -> None:
        ok = await service.send_chain(
            "default:FriendMessage:123456789", [SimpleNamespace(text="x")]
        )
        assert ok is False

    asyncio.run(scenario())
