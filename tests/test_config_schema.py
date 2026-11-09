"""配置默认值与 fork 元数据检查（纯 JSON/YAML 文本，无 AstrBot 依赖）。"""

from __future__ import annotations

import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _schema() -> dict:
    return json.loads((PLUGIN_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))


def test_default_safe_no_auto_messages() -> None:
    schema = _schema()
    assert schema["enabled"]["type"] == "bool"
    assert schema["enabled"]["default"] is False
    assert schema["friend_settings"]["items"]["enable"]["default"] is False
    assert schema["group_settings"]["items"]["enable"]["default"] is False
    # 隐私相关默认关闭
    assert schema["telemetry_config"]["items"]["enabled"]["default"] is False
    assert schema["notification_settings"]["items"]["enabled"]["default"] is False
    assert schema["friend_settings"]["items"]["tts_settings"]["items"]["enable_tts"]["default"] is False


def test_discord_settings_schema() -> None:
    settings = _schema()["discord_settings"]["items"]
    assert settings["platform_id"]["type"] == "string"
    assert settings["platform_id"]["default"] == ""
    assert settings["dm_rate_limit_seconds"]["type"] == "int"
    assert settings["max_send_chars"]["type"] == "int"
    assert settings["resolve_targets_on_startup"]["type"] == "bool"


def test_upstream_core_config_preserved() -> None:
    schema = _schema()
    friend = schema["friend_settings"]["items"]
    schedule = friend["schedule_settings"]["items"]
    assert schedule["min_interval_minutes"]["default"] == 30
    assert schedule["max_interval_minutes"]["default"] == 600
    assert schedule["quiet_hours"]["default"] == "1-7"
    assert schedule["max_unanswered_times"]["default"] == 4
    assert "proactive_prompt" in friend
    assert friend["context_settings"]["items"]["source_mode"]["options"] == [
        "conversation_history",
        "platform_message_history",
        "hybrid",
    ]
    assert schema["web_admin"]["items"]["host"]["default"] == "127.0.0.1"
    assert schema["web_admin"]["items"]["port"]["default"] == 4100


def test_metadata_fork_identity_and_license() -> None:
    metadata = (PLUGIN_ROOT / "metadata.yaml").read_text(encoding="utf-8")
    assert 'name: "astrbot_plugin_proactive_chat_discord"' in metadata
    assert "DBJD-CR" in metadata  # 保留上游作者归属
    assert "discord" in metadata
    assert (PLUGIN_ROOT / "LICENSE").exists()
    license_text = (PLUGIN_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3" in license_text


def test_upstream_and_third_party_docs_exist() -> None:
    upstream = (PLUGIN_ROOT / "UPSTREAM.md").read_text(encoding="utf-8")
    assert "Pancakes-Labs/astrbot_plugin_proactive_chat" in upstream
    assert "554c5d0" in upstream
    assert "AGPL" in upstream
    third_party = (PLUGIN_ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    assert "Outfit" in third_party
    assert "OFL" in third_party


def test_readme_discord_scope() -> None:
    readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
    assert "fetch_user" in readme
    assert "create_dm" in readme
    assert "AGPL-3.0" in readme
    assert "默认关闭" in readme
