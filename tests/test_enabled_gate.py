"""总开关默认关闭 / 上游调度 GATE 的回归测试（容器内执行）。"""

from __future__ import annotations

import asyncio
import importlib.util
from types import SimpleNamespace

import pytest

ASTRBOT_AVAILABLE = importlib.util.find_spec("astrbot") is not None
pytestmark = pytest.mark.skipif(
    not ASTRBOT_AVAILABLE, reason="需要 AstrBot 运行环境（容器内执行）"
)

from astrbot_plugin_proactive_chat_discord.core.adapters.event_handlers import (  # noqa: E402
    EventHandlers,
)
from astrbot_plugin_proactive_chat_discord.core.pipeline.flow_orchestrator import (  # noqa: E402
    FlowOrchestrator,
)
from astrbot_plugin_proactive_chat_discord.core.services.scheduler_service import (  # noqa: E402
    SchedulerService,
)
from astrbot_plugin_proactive_chat_discord.core.services.sender_service import (  # noqa: E402
    SenderService,
)


class FakePlugin:
    def __init__(self, *, enabled: bool = False) -> None:
        self.config = {"enabled": enabled}
        self._terminating = False

    def is_plugin_enabled(self) -> bool:
        return bool(self.config.get("enabled", False))


class FakeEvent:
    def __init__(self) -> None:
        self.called = 0

    def get_messages(self):
        self.called += 1
        return []


def test_scheduler_skips_when_disabled() -> None:
    plugin = FakePlugin(enabled=False)
    scheduler = SchedulerService(plugin)

    async def scenario() -> None:
        await scheduler.setup_auto_trigger("discord:FriendMessage:123456789012345678")
        await scheduler.setup_auto_triggers_for_enabled_sessions()
        await scheduler.init_jobs_from_data()
        await scheduler.schedule_next_chat_and_save(
            "discord:FriendMessage:123456789012345678"
        )

    asyncio.run(scenario())


def test_gate_blocks_when_plugin_disabled() -> None:
    plugin = FakePlugin(enabled=False)
    orchestrator = FlowOrchestrator(plugin)

    async def scenario() -> None:
        allowed, reason = await orchestrator.is_chat_allowed(
            "discord:FriendMessage:123456789012345678"
        )
        assert allowed is False
        assert reason == "plugin_disabled"

    asyncio.run(scenario())


def test_event_handlers_return_early_when_disabled() -> None:
    plugin = FakePlugin(enabled=False)
    handlers = EventHandlers(plugin)
    event = FakeEvent()

    async def scenario() -> None:
        await handlers.on_friend_message(event)
        await handlers.on_group_message(event)
        assert event.called == 0  # 未进入消息处理逻辑

    asyncio.run(scenario())


def test_sender_refuses_when_disabled() -> None:
    plugin = FakePlugin(enabled=False)
    sender = SenderService(plugin)

    async def scenario() -> None:
        ok = await sender.send_chain_direct(
            "discord:FriendMessage:123456789012345678",
            [SimpleNamespace(text="hello")],
        )
        assert ok is False

    asyncio.run(scenario())


def test_main_module_smoke_import() -> None:
    """确认整套上游代码在 AstrBot 4.29.4 下可导入并注册插件类。"""
    module = importlib.import_module(
        "astrbot_plugin_proactive_chat_discord.main"
    )
    assert hasattr(module, "ProactiveChatDiscordPlugin")
    assert hasattr(module.ProactiveChatDiscordPlugin, "is_plugin_enabled")


def test_discord_umo_mapping_patches() -> None:
    """验证 Discord 映射接入上游 session/config 服务。"""
    from astrbot_plugin_proactive_chat_discord.core.adapters.event_handlers import (  # noqa: F401
        EventHandlers,
    )
    from astrbot_plugin_proactive_chat_discord.core.services.config_service import (
        ConfigService,
    )
    from astrbot_plugin_proactive_chat_discord.core.services.session_service import (
        SessionService,
    )

    umo = "discord:FriendMessage:999999999999999999"
    raw_user = "1408751508585058384"

    class StubDiscordService:
        def canonical_umo_for(self, message_type, target_id):
            if str(target_id) == raw_user and "Friend" in message_type:
                return umo
            return None

        def raw_keys_for_umo(self, subject):
            return [raw_user] if subject == umo else []

        def is_discord_session(self, subject):
            return subject == umo

    class Plugin:
        def __init__(self):
            self.config = {
                "friend_settings": {
                    "enable": True,
                    "session_list": [raw_user],
                    "schedule_settings": {"max_unanswered_times": 4},
                }
            }
            self.discord_target_service = StubDiscordService()

        def is_plugin_enabled(self):
            return False

    plugin = Plugin()
    plugin.session_service = SessionService(plugin)
    plugin.config_service = ConfigService(plugin)

    resolved = plugin.session_service.resolve_full_umo(
        raw_user, "FriendMessage", "discord"
    )
    assert resolved == umo
    session_config = plugin.config_service.get_session_config(umo)
    assert session_config is not None
    assert session_config["_session_type"] == "friend"
