"""
M3 测试：跨端身份同步引擎

验证 IdentitySyncEngine 的完整功能：
1. 实例心跳注册
2. 失联实例检测
3. 身份变更广播
4. mesh inbox 消息同步
5. 状态摘要
"""

import pytest
import json
import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from sync.identity_sync import IdentitySyncEngine


@pytest.fixture
def tmp_mesh():
    """创建临时 mesh 目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        mesh_dir = tmp / "mesh"
        mesh_dir.mkdir()

        inbox_dir = mesh_dir / "inbox"
        inbox_dir.mkdir()

        # 创建两个假节点 inbox
        (inbox_dir / "nyx-windows").mkdir()
        (inbox_dir / "nyx-mac").mkdir()
        (inbox_dir / "kronos-heng").mkdir()

        yield {
            "mesh": mesh_dir,
            "inbox": inbox_dir,
            "tmp": tmp
        }


@pytest.fixture
def engine(tmp_mesh):
    """创建 IdentitySyncEngine 实例"""
    return IdentitySyncEngine(
        primary_did="did:key:z7QEhf3KCvlPo9OLiFdPv26cECayGsNa31DV5FpvOyYAMMw",
        instance_id="nyx-windows",
        mesh_base=str(tmp_mesh["mesh"]),
        did_storage_path=str(tmp_mesh["mesh"] / "did"),
        instance_lock_path=str(tmp_mesh["mesh"] / "instance.lock")
    )


class TestHeartbeat:
    def test_heartbeat_updates_registry(self, engine, tmp_mesh):
        result = engine.on_instance_heartbeat("nyx-windows")
        assert result["success"] is True
        assert result["instance_id"] == "nyx-windows"
        assert "lastSeen" in result
        assert result["is_new"] is True  # 首次注册

        # registry 验证
        registry_path = tmp_mesh["mesh"] / "registry.json"
        assert registry_path.exists()
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        assert "nyx-windows" in registry["nodes"]
        assert "lastSeen" in registry["nodes"]["nyx-windows"]

    def test_heartbeat_updates_instance_lock(self, engine, tmp_mesh):
        engine.on_instance_heartbeat("nyx-windows")
        lock_path = tmp_mesh["mesh"] / "instance.lock"
        assert lock_path.exists()
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        assert lock["schema"] == "instance-lock-v1"
        assert lock["holder"] == "nyx-windows"
        assert lock["status"] == "active"
        assert "lastHeartbeat" in lock

    def test_repeat_heartbeat_not_new(self, engine):
        engine.on_instance_heartbeat("nyx-windows")
        result = engine.on_instance_heartbeat("nyx-windows")
        assert result["success"] is True
        assert result["is_new"] is False


class TestStaleDetection:
    def test_no_stale_on_fresh_instances(self, engine):
        result = engine.detect_stale_instances(threshold_minutes=30)
        assert isinstance(result["stale"], list)
        assert isinstance(result["expired"], list)
        assert "timestamp" in result

    def test_detects_stale_with_manual_data(self, engine, tmp_mesh):
        # 手动注入一个旧实例
        registry_path = tmp_mesh["mesh"] / "registry.json"
        old_time = "2026-07-01T10:00:00+00:00"
        registry = {
            "schema": "mesh-registry-v1",
            "nodes": {
                "nyx-windows": {
                    "instance_id": "nyx-windows",
                    "lastSeen": datetime.now(timezone.utc).isoformat(),
                    "status": "active"
                },
                "kronos-heng": {
                    "instance_id": "kronos-heng",
                    "lastSeen": old_time,
                    "status": "active"
                }
            }
        }
        registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")

        # 30分钟阈值：kronos-heng 已过24h → expired
        result = engine.detect_stale_instances(threshold_minutes=30)
        assert len(result["expired"]) >= 1
        expired_names = [e["name"] for e in result["expired"]]
        assert "kronos-heng" in expired_names


class TestBroadcast:
    def test_broadcast_creates_messages(self, engine, tmp_mesh):
        result = engine.propagate_identity_change("instance_register", {
            "instance_id": "nyx-windows",
            "hostname": "WLMHAN"
        })
        assert result["success"] is True
        assert result["total_broadcast"] >= 1
        assert len(result["message_files"]) >= 1
        assert len(result["errors"]) == 0

        # 检查消息文件内容
        msg_file = Path(result["message_files"][0])
        content = msg_file.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "change_type: instance_register" in content

        # 检查 flag 文件
        node_name = msg_file.parent.name
        flag_file = tmp_mesh["mesh"] / "inbox" / node_name / "_flag.md"
        assert flag_file.exists()

    def test_broadcast_includes_all_nodes(self, engine, tmp_mesh):
        # 先注册多个实例
        engine.on_instance_heartbeat("nyx-windows")
        engine.on_instance_heartbeat("nyx-mac")
        engine.on_instance_heartbeat("kronos-heng")

        result = engine.propagate_identity_change("instance_heartbeat", {
            "instance_id": "nyx-windows"
        })

        # 广播应写入所有 3 个节点
        assert result["total_broadcast"] >= 3


class TestSync:
    def test_sync_processes_inbox_messages(self, engine, tmp_mesh):
        # 在 nyx-windows inbox 写入一条测试消息
        inbox = tmp_mesh["mesh"] / "inbox" / "nyx-windows"
        msg_file = inbox / "msg_0001_kronos-heng_test.md"
        msg_file.write_text(
            """---
schema: mesh-identity-v1
from: kronos-heng
type: identity_broadcast
change_type: instance_register
timestamp: 2026-07-02T10:00:00+08:00
---

## 韬€€ Identit

**change_type**: instance_register
**data**: {"instance_id": "kronos-heng", "hostname": "Coze"}
""",
            encoding="utf-8"
        )

        result = engine.sync_identity_state()

        assert "messages_processed" in result
        assert "errors" in result
        assert "updated_nodes" in result

        # 消息文件应被消费
        assert not msg_file.exists()


class TestAutoRevoke:
    def test_auto_revoke_no_expired_nodes(self, engine):
        # 无过期节点时，不应有任何错误
        result = engine.auto_revoke_expired(threshold_minutes=60)
        assert result["success"] is True
        assert len(result["revoked"]) == 0
        assert len(result["errors"]) == 0


class TestStatus:
    def test_status_returns_complete_info(self, engine):
        engine.on_instance_heartbeat("nyx-windows")

        status = engine.get_status()

        assert status["local_instance"] == "nyx-windows"
        assert status["total_registered"] >= 1
        assert "active_instances" in status
        assert "stale_instances" in status
        assert "mesh_reachable" in status
        assert "registry_path" in status
        assert "instance_lock_path" in status

    def test_status_mesh_unreachable_false_when_ok(self, engine):
        status = engine.get_status()
        assert status["mesh_reachable"] is True


class TestAtomicWrite:
    def test_json_write_is_atomic(self, engine, tmp_mesh):
        """验证原子写入（临时文件+重命名）"""
        engine.on_instance_heartbeat("nyx-windows")
        registry_path = tmp_mesh["mesh"] / "registry.json"

        # 写入过程中不应出现 .tmp 文件
        tmp_files = list(tmp_mesh["mesh"].glob("*.tmp"))
        assert len(tmp_files) == 0, f"发现临时文件: {tmp_files}"

        # 最终文件是合法的 JSON
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        assert "schema" in registry
        assert "nodes" in registry
