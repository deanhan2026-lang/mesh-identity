"""
NAS Storage Abstraction - NAS存储抽象层

提供统一的NAS存储访问接口，支持：
1. SMB/NFS协议抽象
2. 文件锁机制（防止多终端同时写入冲突）
3. 健康检查和故障转移
4. 路径标准化

默认使用SMB协议（Windows环境），可通过配置切换。
"""

import os
import json
import time
import fcntl
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class NASStorage:
    """NAS存储抽象类"""
    
    def __init__(self, base_path: str = "Z:/qclaw"):
        """
        初始化NAS存储
        
        Args:
            base_path: NAS挂载路径（如 Z:/qclaw）
        """
        self.base_path = Path(base_path)
        if not self.base_path.exists():
            raise FileNotFoundError(f"NAS路径不存在: {base_path}")
        
        # 子目录
        self.did_path = self.base_path / "did"
        self.memory_path = self.base_path / "memory_vault"
        self.scene_path = self.base_path / "scene_config"
        self.lock_path = self.base_path / "lock"
        
        # 创建目录
        for path in [self.did_path, self.memory_path, 
                     self.scene_path, self.lock_path]:
            path.mkdir(parents=True, exist_ok=True)
    
    def read_file(self, relative_path: str) -> str:
        """
        读取文件内容
        
        Args:
            relative_path: 相对路径（相对于base_path）
            
        Returns:
            文件内容（文本）
        """
        full_path = self.base_path / relative_path
        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {full_path}")
        
        return full_path.read_text(encoding='utf-8')
    
    def write_file(self, relative_path: str, content: str, 
                   atomic: bool = True) -> bool:
        """
        写入文件内容
        
        Args:
            relative_path: 相对路径（相对于base_path）
            content: 文件内容
            atomic: 是否使用原子写入（临时文件+重命名）
            
        Returns:
            是否成功
        """
        full_path = self.base_path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        if atomic:
            # 原子写入：先写临时文件，再重命名
            temp_path = full_path.with_suffix('.tmp')
            temp_path.write_text(content, encoding='utf-8')
            temp_path.rename(full_path)
        else:
            full_path.write_text(content, encoding='utf-8')
        
        return True
    
    def list_files(self, relative_dir: str, pattern: str = "*") -> List[str]:
        """
        列出目录中的文件
        
        Args:
            relative_dir: 相对目录路径
            pattern: 文件模式（如 *.json）
            
        Returns:
            文件路径列表（相对路径）
        """
        full_dir = self.base_path / relative_dir
        if not full_dir.exists():
            return []
        
        files = list(full_dir.glob(pattern))
        # 返回相对路径
        return [str(f.relative_to(self.base_path)) for f in files]
    
    def file_exists(self, relative_path: str) -> bool:
        """检查文件是否存在"""
        return (self.base_path / relative_path).exists()
    
    def get_file_hash(self, relative_path: str) -> str:
        """计算文件的SHA-256哈希值"""
        import hashlib
        full_path = self.base_path / relative_path
        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {full_path}")
        
        content = full_path.read_bytes()
        return hashlib.sha256(content).hexdigest()
    
    def acquire_lock(self, lock_name: str, timeout: int = 30) -> bool:
        """
        获取文件锁（防止多终端同时写入）
        
        Args:
            lock_name: 锁名称（如 "memory_sync"）
            timeout: 超时时间（秒）
            
        Returns:
            是否成功获取锁
        """
        lock_file = self.lock_path / f"{lock_name}.lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 简化版锁机制：创建锁文件（包含主机名和时间戳）
        if lock_file.exists():
            # 检查锁是否过期（超过timeout秒）
            lock_content = lock_file.read_text()
            try:
                lock_time = datetime.fromisoformat(lock_content.split("|")[1])
                if (datetime.now() - lock_time).seconds > timeout:
                    # 锁已过期，强制释放
                    lock_file.unlink()
                else:
                    return False  # 锁被其他终端持有
            except:
                lock_file.unlink()  # 格式错误，删除锁
        
        # 创建锁
        lock_content = f"{os.environ.get('COMPUTERNAME', 'unknown')}|{datetime.now().isoformat()}"
        lock_file.write_text(lock_content)
        return True
    
    def release_lock(self, lock_name: str):
        """释放文件锁"""
        lock_file = self.lock_path / f"{lock_name}.lock"
        if lock_file.exists():
            lock_file.unlink()
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态字典
        """
        status = {
            "path_exists": self.base_path.exists(),
            "readable": False,
            "writable": False,
            "latency_ms": None,
            "timestamp": datetime.now().isoformat()
        }
        
        if not status["path_exists"]:
            return status
        
        # 测试读取
        try:
            test_file = self.base_path / "health_check.tmp"
            test_content = "health_check"
            self.write_file("health_check.tmp", test_content)
            read_content = self.read_file("health_check.tmp")
            status["readable"] = (read_content == test_content)
            
            # 测试写入
            status["writable"] = True
            
            # 计算延迟
            start = time.time()
            self.write_file("health_check.tmp", test_content)
            end = time.time()
            status["latency_ms"] = int((end - start) * 1000)
            
            # 清理
            test_file.unlink(missing_ok=True)
        except Exception as e:
            status["error"] = str(e)
        
        return status
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        import shutil
        
        total, used, free = shutil.disk_usage(self.base_path)
        return {
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "usage_percent": round(used / total * 100, 2)
        }


class MemoryVaultStorage(NASStorage):
    """Memory Vault专用存储类"""
    
    def __init__(self, base_path: str = "Z:/qclaw"):
        super().__init__(base_path)
        self.entries_path = self.memory_path / "entries"
        self.index_path = self.memory_path / "index.json"
        self.entries_path.mkdir(parents=True, exist_ok=True)
    
    def save_entry(self, entry_id: str, entry_data: Dict) -> bool:
        """
        保存MemoryEntry
        
        Args:
            entry_id: 条目ID
            entry_data: 条目数据
            
        Returns:
            是否成功
        """
        # 添加到条目文件
        entry_file = self.entries_path / f"{entry_id}.json"
        self.write_file(
            str(entry_file.relative_to(self.base_path)),
            json.dumps(entry_data, indent=2, ensure_ascii=False)
        )
        
        # 更新索引
        self._update_index(entry_id, entry_data)
        return True
    
    def load_entry(self, entry_id: str) -> Optional[Dict]:
        """加载MemoryEntry"""
        entry_file = self.entries_path / f"{entry_id}.json"
        if not entry_file.exists():
            return None
        
        content = self.read_file(str(entry_file.relative_to(self.base_path)))
        return json.loads(content)
    
    def list_entries(self, category: str = None) -> List[str]:
        """
        列出所有条目ID
        
        Args:
            category: 按分类过滤（可选）
            
        Returns:
            条目ID列表
        """
        if not self.index_path.exists():
            return []
        
        index = json.loads(self.read_file(str(self.index_path.relative_to(self.base_path))))
        if category:
            return [eid for eid, meta in index.get("entries", {}).items() 
                    if meta.get("category") == category]
        else:
            return list(index.get("entries", {}).keys())
    
    def _update_index(self, entry_id: str, entry_data: Dict):
        """更新索引文件"""
        if self.index_path.exists():
            index = json.loads(self.read_file(str(self.index_path.relative_to(self.base_path))))
        else:
            index = {"entries": {}, "last_updated": None}
        
        # 更新条目元数据
        index["entries"][entry_id] = {
            "category": entry_data.get("category"),
            "priority": entry_data.get("priority"),
            "created_at": entry_data.get("created_at"),
            "updated_at": datetime.now().isoformat()
        }
        index["last_updated"] = datetime.now().isoformat()
        
        # 保存索引
        self.write_file(
            str(self.index_path.relative_to(self.base_path)),
            json.dumps(index, indent=2, ensure_ascii=False)
        )


def main():
    """测试存储层"""
    storage = NASStorage("Z:/qclaw")
    
    # 健康检查
    health = storage.health_check()
    print("健康检查:", json.dumps(health, indent=2, ensure_ascii=False))
    
    # 存储统计
    stats = storage.get_storage_stats()
    print("存储统计:", json.dumps(stats, indent=2, ensure_ascii=False))
    
    # 测试锁
    if storage.acquire_lock("test_lock"):
        print("锁获取成功")
        storage.release_lock("test_lock")
        print("锁释放成功")
    else:
        print("锁已被持有")


if __name__ == "__main__":
    main()
