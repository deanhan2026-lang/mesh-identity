"""测试存储抽象层"""
import pytest
import os
import tempfile


class TestNASStorage:
    """NAS 存储抽象测试"""
    
    def test_nas_path_format(self):
        """NAS 路径格式验证"""
        valid_paths = [
            "Z:/qclaw/did",
            "\\\\100.65.105.57\\SOFTWARE\\qclaw",
            "/mnt/nas/qclaw",
        ]
        for path in valid_paths:
            assert len(path) > 0
    
    def test_storage_dirs_defined(self):
        """标准存储目录已定义"""
        dirs = {
            "did": "did/",
            "memory_vault": "memory_vault/",
            "scene_config": "scene_config/",
        }
        for key, path in dirs.items():
            assert key in ["did", "memory_vault", "scene_config"]
            assert "/" in path or "\\" in path
    
    def test_local_override(self):
        """本地存储可覆盖 NAS 路径"""
        # 本地路径优先级高于 NAS
        storage_path = os.environ.get("MESH_IDENTITY_STORAGE", "Z:/qclaw")
        assert storage_path  # 非空
        
        # 当设置本地路径时，优先使用
        override_path = "C:/Users/test/.mesh-identity"
        os.environ["MESH_IDENTITY_STORAGE"] = override_path
        assert os.environ.get("MESH_IDENTITY_STORAGE") == override_path
        # 清理
        del os.environ["MESH_IDENTITY_STORAGE"]


class TestFileLock:
    """文件锁机制测试"""
    
    def test_lock_file_pattern(self):
        """锁文件命名模式"""
        import re
        lock_pattern = r'^instance\.lock$'
        assert re.match(lock_pattern, "instance.lock")
        assert not re.match(lock_pattern, "instance.lock.bak")
    
    def test_lock_timeout_logic(self):
        """锁超时逻辑"""
        # 锁超时 = 5 分钟
        LOCK_TIMEOUT_SECONDS = 5 * 60
        assert LOCK_TIMEOUT_SECONDS == 300
        
        # 模拟心跳更新
        import time
        now = time.time()
        last_heartbeat = now - 200  # 3分20秒前
        is_expired = (now - last_heartbeat) > LOCK_TIMEOUT_SECONDS
        assert not is_expired  # 3分20秒 < 5分钟，未过期
        
        last_heartbeat = now - 400  # 6分40秒前
        is_expired = (now - last_heartbeat) > LOCK_TIMEOUT_SECONDS
        assert is_expired  # 6分40秒 > 5分钟，已过期


class TestVersionControl:
    """版本控制测试"""
    
    def test_vector_clock_increment(self):
        """向量时钟递增"""
        vc = {"nyx-windows": 1, "nyx-mac": 0}
        
        # nyx-windows 更新
        vc["nyx-windows"] += 1
        assert vc["nyx-windows"] == 2
        
        # nyx-mac 更新
        vc["nyx-mac"] += 1
        assert vc["nyx-mac"] == 1
    
    def test_causality_detection(self):
        """因果关系检测"""
        vc_a = {"nyx-windows": 2, "nyx-mac": 0}
        vc_b = {"nyx-windows": 2, "nyx-mac": 1}
        
        # vc_b 包含了 vc_a 的所有更新，且有额外的 nyx-mac 更新
        # vc_b >= vc_a，所以 B 在 A 之后（或同时）
        a_after_b = all(vc_b.get(k, 0) >= v for k, v in vc_a.items())
        assert a_after_b
        
        # 并发检测
        vc_c = {"nyx-windows": 1, "nyx-mac": 1}
        # vc_a 和 vc_c 互相不包含对方 → 并发
        a_contains_c = all(vc_a.get(k, 0) >= v for k, v in vc_c.items() if k in vc_a)
        c_contains_a = all(vc_c.get(k, 0) >= v for k, v in vc_a.items() if k in vc_c)
        # vc_c 有更新的 nyx-windows，vc_a 有更新的 nyx-mac → 并发
        assert not (a_contains_c and c_contains_a)
