"""
Memory Sync Engine - 记忆同步引擎

实现多终端记忆同步的核心功能：
1. 事件触发同步（监听本地记忆变化）
2. 版本控制（向量时钟，防止冲突）
3. 双向同步（推送本地记忆，拉取远程记忆）
4. 冲突检测

MVP使用简化版：轮询 + 最后写入优先（LWW）策略
"""

import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from ..storage.nas_storage import MemoryVaultStorage
from ..resolve.conflict import ConflictResolver


class MemorySyncEngine:
    """记忆同步引擎"""
    
    def __init__(self, 
                 local_path: str = "C:/Users/Administrator/.qclaw/workspace-agent-d9479bde/memory",
                 nas_path: str = "Z:/qclaw/memory_vault",
                 terminal_id: str = None):
        """
        初始化同步引擎
        
        Args:
            local_path: 本地记忆路径
            nas_path: NAS记忆路径
            terminal_id: 终端ID（如 nyx-windows, nyx-mac）
        """
        self.local_path = Path(local_path)
        self.terminal_id = terminal_id or os.environ.get("COMPUTERNAME", "unknown")
        
        # 存储层
        self.local_storage = MemoryVaultStorage(str(self.local_path.parent))
        self.nas_storage = MemoryVaultStorage(nas_path)
        
        # 冲突解决器
        self.resolver = ConflictResolver()
        
        # 同步状态文件
        self.state_file = self.local_path.parent / "sync_state.json"
        self.state = self._load_state()
        
        # 文件监控
        self.observer = None
        
    def _load_state(self) -> Dict:
        """加载同步状态"""
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        else:
            return {
                "terminal_id": self.terminal_id,
                "last_sync": None,
                "last_push": None,
                "last_pull": None,
                "vector_clock": {},  # {terminal_id: sequence_number}
                "sync_history": []
            }
    
    def _save_state(self):
        """保存同步状态"""
        self.state_file.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False)
        )
    
    def _update_vector_clock(self, terminal_id: str = None):
        """更新向量时钟"""
        if terminal_id is None:
            terminal_id = self.terminal_id
        
        if terminal_id not in self.state["vector_clock"]:
            self.state["vector_clock"][terminal_id] = 0
        
        self.state["vector_clock"][terminal_id] += 1
        return self.state["vector_clock"]
    
    def push_memory(self, entry_id: str = None, force: bool = False) -> Dict:
        """
        推送本地记忆到NAS
        
        Args:
            entry_id: 指定推送的条目ID（None表示推送所有新条目）
            force: 是否强制推送（覆盖远程版本）
            
        Returns:
            推送结果统计
        """
        # 获取锁
        if not self.nas_storage.acquire_lock("memory_sync", timeout=30):
            return {"success": False, "error": "无法获取同步锁，其他终端正在同步"}
        
        try:
            result = {
                "pushed": 0,
                "skipped": 0,
                "conflicts": 0,
                "errors": []
            }
            
            # 确定要推送的条目
            if entry_id:
                entry_ids = [entry_id]
            else:
                # 推送所有本地有新变更的条目
                entry_ids = self._get_unsynced_entries()
            
            for eid in entry_ids:
                try:
                    # 加载本地条目
                    local_entry = self.local_storage.load_entry(eid)
                    if not local_entry:
                        result["errors"].append(f"本地条目不存在: {eid}")
                        continue
                    
                    # 检查远程是否有冲突版本
                    remote_entry = self.nas_storage.load_entry(eid)
                    if remote_entry:
                        # 有冲突，需要解决
                        conflict = self.resolver.detect_conflict(local_entry, remote_entry)
                        if conflict:
                            if force:
                                # 强制推送，覆盖远程
                                pass
                            else:
                                # 记录冲突，跳过
                                result["conflicts"] += 1
                                result["errors"].append(f"冲突: {eid}")
                                continue
                    
                    # 更新向量时钟
                    vector_clock = self._update_vector_clock()
                    local_entry["_vector_clock"] = vector_clock
                    local_entry["_last_modified_by"] = self.terminal_id
                    local_entry["_last_modified_at"] = datetime.now().isoformat()
                    
                    # 保存到NAS
                    self.nas_storage.save_entry(eid, local_entry)
                    result["pushed"] += 1
                    
                except Exception as e:
                    result["errors"].append(f"推送失败 {eid}: {str(e)}")
            
            # 更新同步状态
            self.state["last_push"] = datetime.now().isoformat()
            self._save_state()
            
            return result
            
        finally:
            self.nas_storage.release_lock("memory_sync")
    
    def pull_memory(self, entry_id: str = None) -> Dict:
        """
        从NAS拉取记忆到本地
        
        Args:
            entry_id: 指定拉取的条目ID（None表示拉取所有新条目）
            
        Returns:
            拉取结果统计
        """
        result = {
            "pulled": 0,
            "skipped": 0,
            "conflicts": 0,
            "errors": []
        }
        
        # 确定要拉取的条目
        if entry_id:
            entry_ids = [entry_id]
        else:
            # 拉取所有远程有新变更的条目
            entry_ids = self._get_remote_updates()
        
        for eid in entry_ids:
            try:
                # 加载远程条目
                remote_entry = self.nas_storage.load_entry(eid)
                if not remote_entry:
                    result["errors"].append(f"远程条目不存在: {eid}")
                    continue
                
                # 检查本地是否有冲突版本
                local_entry = self.local_storage.load_entry(eid)
                if local_entry:
                    # 有冲突，需要解决
                    conflict = self.resolver.detect_conflict(local_entry, remote_entry)
                    if conflict:
                        # 使用冲突解决策略
                        resolved = self.resolver.resolve(local_entry, remote_entry)
                        local_entry = resolved
                        result["conflicts"] += 1
                
                # 保存到本地
                self.local_storage.save_entry(eid, remote_entry)
                result["pulled"] += 1
                
            except Exception as e:
                result["errors"].append(f"拉取失败 {eid}: {str(e)}")
        
        # 更新同步状态
        self.state["last_pull"] = datetime.now().isoformat()
        self._save_state()
        
        return result
    
    def sync(self, bidirectional: bool = True) -> Dict:
        """
        执行完整同步（推送 + 拉取）
        
        Args:
            bidirectional: 是否双向同步
            
        Returns:
            同步结果统计
        """
        result = {
            "push": None,
            "pull": None,
            "timestamp": datetime.now().isoformat()
        }
        
        if bidirectional:
            result["push"] = self.push_memory()
            result["pull"] = self.pull_memory()
        else:
            # 根据参数决定方向
            pass
        
        # 记录同步历史
        history = self.state["sync_history"]
        history.append(result)
        if len(history) > 100:  # 保留最近100次同步记录
            history.pop(0)
        self.state["sync_history"] = history
        self.state["last_sync"] = result["timestamp"]
        self._save_state()
        
        return result
    
    def _get_unsynced_entries(self) -> List[str]:
        """获取本地未同步的条目列表"""
        # 简化版：比较本地和远程的条目列表，找出本地有但远程没有的
        local_entries = set(self.local_storage.list_entries())
        remote_entries = set(self.nas_storage.list_entries())
        
        # 新增条目
        new_entries = local_entries - remote_entries
        
        # 检查已有条目是否有更新（比较修改时间）
        updated_entries = []
        for eid in local_entries & remote_entries:
            local_entry = self.local_storage.load_entry(eid)
            remote_entry = self.nas_storage.load_entry(eid)
            
            local_time = local_entry.get("_last_modified_at", "")
            remote_time = remote_entry.get("_last_modified_at", "")
            
            if local_time > remote_time:
                updated_entries.append(eid)
        
        return list(new_entries) + updated_entries
    
    def _get_remote_updates(self) -> List[str]:
        """获取远程有更新的条目列表"""
        local_entries = set(self.local_storage.list_entries())
        remote_entries = set(self.nas_storage.list_entries())
        
        # 新增条目
        new_entries = remote_entries - local_entries
        
        # 检查已有条目是否有更新
        updated_entries = []
        for eid in local_entries & remote_entries:
            local_entry = self.local_storage.load_entry(eid)
            remote_entry = self.nas_storage.load_entry(eid)
            
            local_time = local_entry.get("_last_modified_at", "")
            remote_time = remote_entry.get("_last_modified_at", "")
            
            if remote_time > local_time:
                updated_entries.append(eid)
        
        return list(new_entries) + updated_entries
    
    def start_watching(self):
        """开始监听本地记忆变化（事件触发同步）"""
        if self.observer:
            return
        
        event_handler = MemoryChangeHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, str(self.local_path), recursive=True)
        self.observer.start()
        print(f"开始监听本地记忆变化: {self.local_path}")
    
    def stop_watching(self):
        """停止监听"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            print("停止监听本地记忆变化")


class MemoryChangeHandler(FileSystemEventHandler):
    """本地记忆文件变化监听器"""
    
    def __init__(self, sync_engine: MemorySyncEngine):
        self.sync_engine = sync_engine
        self.debounce_timer = None
    
    def on_modified(self, event):
        """文件被修改"""
        if event.is_directory:
            return
        
        # 防抖：等待文件写入完成
        if self.debounce_timer:
            self.debounce_timer.cancel()
        
        self.debounce_timer = threading.Timer(
            2.0,  # 2秒防抖
            self._sync_file,
            args=[event.src_path]
        )
        self.debounce_timer.start()
    
    def _sync_file(self, file_path: str):
        """同步单个文件"""
        try:
            # 提取条目ID
            file_name = os.path.basename(file_path)
            if file_name.endswith(".json"):
                entry_id = file_name[:-5]  # 去掉.json后缀
                self.sync_engine.push_memory(entry_id)
                print(f"自动同步条目: {entry_id}")
        except Exception as e:
            print(f"自动同步失败: {file_path}, 错误: {e}")


def main():
    """测试同步引擎"""
    import argparse
    
    parser = argparse.ArgumentParser(description="记忆同步引擎")
    parser.add_argument("action", choices=["push", "pull", "sync", "watch"],
                        help="操作类型")
    parser.add_argument("--terminal", default=None,
                        help="终端ID")
    
    args = parser.parse_args()
    
    engine = MemorySyncEngine(terminal_id=args.terminal)
    
    if args.action == "push":
        result = engine.push_memory()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.action == "pull":
        result = engine.pull_memory()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.action == "sync":
        result = engine.sync()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.action == "watch":
        engine.start_watching()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            engine.stop_watching()


if __name__ == "__main__":
    main()
