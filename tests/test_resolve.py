"""测试冲突解决器"""
import pytest
from datetime import datetime


class MockConflict:
    """模拟冲突"""
    def __init__(self, entry_id, local_ts, remote_ts, local_content, remote_content):
        self.entry_id = entry_id
        self.local_ts = local_ts
        self.remote_ts = remote_ts
        self.local_content = local_content
        self.remote_content = remote_content


class TestLWWStrategy:
    """最后写入优先（LWW）策略测试"""
    
    @staticmethod
    def lww_resolve(conflict: MockConflict) -> dict:
        """LWW 策略：时间戳更晚的胜出"""
        if conflict.local_ts > conflict.remote_ts:
            return {"content": conflict.local_content, "source": "local"}
        else:
            return {"content": conflict.remote_content, "source": "remote"}
    
    def test_local_wins_when_newer(self):
        """本地更新时本地胜出"""
        conflict = MockConflict(
            entry_id="mem_001",
            local_ts=1700000100,
            remote_ts=1700000000,
            local_content="New content",
            remote_content="Old content"
        )
        result = self.lww_resolve(conflict)
        assert result["source"] == "local"
        assert result["content"] == "New content"
    
    def test_remote_wins_when_newer(self):
        """远程更新时远程胜出"""
        conflict = MockConflict(
            entry_id="mem_001",
            local_ts=1700000000,
            remote_ts=1700000100,
            local_content="Old content",
            remote_content="New content"
        )
        result = self.lww_resolve(conflict)
        assert result["source"] == "remote"
        assert result["content"] == "New content"
    
    def test_remote_wins_on_equal_timestamp(self):
        """时间戳相等时远程优先（保守策略）"""
        conflict = MockConflict(
            entry_id="mem_001",
            local_ts=1700000000,
            remote_ts=1700000000,
            local_content="Local same",
            remote_content="Remote same"
        )
        result = self.lww_resolve(conflict)
        assert result["source"] == "remote"
    
    def test_conflict_detection(self):
        """同一条目本地和远程内容不同 = 冲突"""
        entries = {
            "local": {"id": "mem_001", "content": "local version", "ts": 1700000100},
            "remote": {"id": "mem_001", "content": "remote version", "ts": 1700000000}
        }
        is_conflict = (
            entries["local"]["id"] == entries["remote"]["id"]
            and entries["local"]["content"] != entries["remote"]["content"]
        )
        assert is_conflict
    
    def test_no_conflict_when_same_content(self):
        """内容相同时不冲突"""
        entries = {
            "local": {"id": "mem_001", "content": "same content", "ts": 1700000100},
            "remote": {"id": "mem_001", "content": "same content", "ts": 1700000000}
        }
        is_conflict = (
            entries["local"]["id"] == entries["remote"]["id"]
            and entries["local"]["content"] != entries["remote"]["content"]
        )
        assert not is_conflict
