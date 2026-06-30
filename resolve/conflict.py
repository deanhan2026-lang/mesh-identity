"""
Conflict Resolver - 冲突解决器

处理多终端同步时的记忆冲突：
1. 冲突检测（基于向量时钟）
2. 自动解决策略（最后写入优先 LWW）
3. 人工审核接口（高风险冲突）
4. 冲突日志记录

MVP策略：最后写入优先（LWW）+ 冲突日志
未来版本：语义合并、AI辅助解决
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from enum import Enum


class ConflictStrategy(Enum):
    """冲突解决策略"""
    LWW = "last_write_wins"  # 最后写入优先
    MANUAL = "manual_review"  # 人工审核
    SEMANTIC = "semantic_merge"  # 语义合并（未来）


class ConflictResolver:
    """冲突解决器"""
    
    def __init__(self, 
                 strategy: ConflictStrategy = ConflictStrategy.LWW,
                 conflict_log_path: str = "Z:/qclaw/conflicts"):
        """
        初始化冲突解决器
        
        Args:
            strategy: 默认解决策略
            conflict_log_path: 冲突日志目录
        """
        self.strategy = strategy
        self.conflict_log_path = Path(conflict_log_path)
        self.conflict_log_path.mkdir(parents=True, exist_ok=True)
    
    def detect_conflict(self, local_entry: Dict, remote_entry: Dict) -> Optional[Dict]:
        """
        检测两个条目是否冲突
        
        Args:
            local_entry: 本地条目
            remote_entry: 远程条目
            
        Returns:
            如果冲突，返回冲突信息；否则返回None
        """
        # 检查向量时钟
        local_clock = local_entry.get("_vector_clock", {})
        remote_clock = remote_entry.get("_vector_clock", {})
        
        # 简化版冲突检测：比较最后修改时间
        local_time = local_entry.get("_last_modified_at", "")
        remote_time = remote_entry.get("_last_modified_at", "")
        
        if local_time == remote_time:
            return None  # 同时修改，需要解决
        
        # 检查内容是否有实质差异
        local_content = self._extract_content(local_entry)
        remote_content = self._extract_content(remote_entry)
        
        if local_content == remote_content:
            return None  # 内容相同，无冲突
        
        # 有冲突
        return {
            "entry_id": local_entry.get("entry_id"),
            "local": {
                "modified_by": local_entry.get("_last_modified_by"),
                "modified_at": local_time,
                "content_hash": self._hash_content(local_content)
            },
            "remote": {
                "modified_by": remote_entry.get("_last_modified_by"),
                "modified_at": remote_time,
                "content_hash": self._hash_content(remote_content)
            },
            "detected_at": datetime.now().isoformat()
        }
    
    def resolve(self, local_entry: Dict, remote_entry: Dict, 
                strategy: ConflictStrategy = None) -> Dict:
        """
        解决冲突
        
        Args:
            local_entry: 本地条目
            remote_entry: 远程条目
            strategy: 解决策略（None表示使用默认策略）
            
        Returns:
            解决后的条目
        """
        if strategy is None:
            strategy = self.strategy
        
        # 检测冲突
        conflict = self.detect_conflict(local_entry, remote_entry)
        if not conflict:
            return local_entry  # 无冲突，返回本地版本
        
        # 记录冲突
        self._log_conflict(conflict, local_entry, remote_entry)
        
        # 根据策略解决
        if strategy == ConflictStrategy.LWW:
            return self._resolve_lww(local_entry, remote_entry, conflict)
        elif strategy == ConflictStrategy.MANUAL:
            return self._resolve_manual(local_entry, remote_entry, conflict)
        elif strategy == ConflictStrategy.SEMANTIC:
            return self._resolve_semantic(local_entry, remote_entry, conflict)
        else:
            raise ValueError(f"未知策略: {strategy}")
    
    def _resolve_lww(self, local_entry: Dict, remote_entry: Dict, 
                     conflict: Dict) -> Dict:
        """最后写入优先策略"""
        local_time = local_entry.get("_last_modified_at", "")
        remote_time = remote_entry.get("_last_modified_at", "")
        
        # 比较时间戳
        if remote_time > local_time:
            # 远程版本较新，使用远程版本
            resolved = remote_entry.copy()
            resolved["_resolved_by"] = "lww"
            resolved["_resolved_at"] = datetime.now().isoformat()
            return resolved
        else:
            # 本地版本较新或同时，使用本地版本
            resolved = local_entry.copy()
            resolved["_resolved_by"] = "lww"
            resolved["_resolved_at"] = datetime.now().isoformat()
            return resolved
    
    def _resolve_manual(self, local_entry: Dict, remote_entry: Dict, 
                        conflict: Dict) -> Dict:
        """人工审核策略（MVP：标记为待审核，返回本地版本）"""
        # 标记为待审核
        local_entry["_conflict_pending"] = True
        local_entry["_conflict_id"] = conflict["detected_at"]
        
        # 保存冲突详情到日志
        self._save_conflict_for_review(conflict, local_entry, remote_entry)
        
        # 返回本地版本（等待人工审核）
        return local_entry
    
    def _resolve_semantic(self, local_entry: Dict, remote_entry: Dict, 
                          conflict: Dict) -> Dict:
        """语义合并策略（未来版本）"""
        # MVP：回退到LWW
        print("警告: 语义合并尚未实现，使用LWW策略")
        return self._resolve_lww(local_entry, remote_entry, conflict)
    
    def _extract_content(self, entry: Dict) -> str:
        """提取条目内容（用于比较）"""
        # 去掉元数据字段
        meta_fields = {"_vector_clock", "_last_modified_by", "_last_modified_at",
                       "_resolved_by", "_resolved_at", "_conflict_pending", "_conflict_id"}
        
        content = {k: v for k, v in entry.items() if k not in meta_fields}
        return json.dumps(content, sort_keys=True)
    
    def _hash_content(self, content: str) -> str:
        """计算内容哈希"""
        import hashlib
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _log_conflict(self, conflict: Dict, local_entry: Dict, remote_entry: Dict):
        """记录冲突到日志文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.conflict_log_path / f"conflict_{timestamp}.json"
        
        log_data = {
            "conflict": conflict,
            "local_entry": local_entry,
            "remote_entry": remote_entry,
            "resolved": False,
            "resolution": None
        }
        
        log_file.write_text(
            json.dumps(log_data, indent=2, ensure_ascii=False)
        )
    
    def _save_conflict_for_review(self, conflict: Dict, 
                                  local_entry: Dict, remote_entry: Dict):
        """保存待人工审核的冲突"""
        conflict_id = conflict["detected_at"].replace(":", "-")
        review_file = self.conflict_log_path / f"pending_{conflict_id}.json"
        
        review_data = {
            "conflict_id": conflict_id,
            "conflict": conflict,
            "local_entry": local_entry,
            "remote_entry": remote_entry,
            "status": "pending_review",
            "created_at": datetime.now().isoformat()
        }
        
        review_file.write_text(
            json.dumps(review_data, indent=2, ensure_ascii=False)
        )
    
    def list_pending_conflicts(self) -> List[Dict]:
        """列出待审核的冲突"""
        pending = []
        for f in self.conflict_log_path.glob("pending_*.json"):
            data = json.loads(f.read_text())
            pending.append(data)
        return pending
    
    def resolve_manual_conflict(self, conflict_id: str, 
                                resolution: str) -> bool:
        """
        人工解决冲突
        
        Args:
            conflict_id: 冲突ID
            resolution: 解决方式（"local"或"remote"）
            
        Returns:
            是否成功
        """
        review_file = self.conflict_log_path / f"pending_{conflict_id}.json"
        if not review_file.exists():
            return False
        
        data = json.loads(review_file.read_text())
        data["status"] = "resolved"
        data["resolution"] = resolution
        data["resolved_at"] = datetime.now().isoformat()
        
        # 保存解决结果
        review_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )
        
        return True


def main():
    """测试冲突解决器"""
    import argparse
    
    parser = argparse.ArgumentParser(description="冲突解决器")
    parser.add_argument("action", choices=["detect", "resolve", "list", "resolve_manual"],
                        help="操作类型")
    parser.add_argument("--local", help="本地条目文件")
    parser.add_argument("--remote", help="远程条目文件")
    parser.add_argument("--strategy", choices=["lww", "manual"],
                        default="lww", help="解决策略")
    
    args = parser.parse_args()
    
    resolver = ConflictResolver()
    
    if args.action == "detect":
        if not args.local or not args.remote:
            print("需要--local和--remote参数")
            return
        
        local_entry = json.loads(Path(args.local).read_text())
        remote_entry = json.loads(Path(args.remote).read_text())
        
        conflict = resolver.detect_conflict(local_entry, remote_entry)
        if conflict:
            print("检测到冲突:")
            print(json.dumps(conflict, indent=2, ensure_ascii=False))
        else:
            print("无冲突")
    
    elif args.action == "resolve":
        if not args.local or not args.remote:
            print("需要--local和--remote参数")
            return
        
        local_entry = json.loads(Path(args.local).read_text())
        remote_entry = json.loads(Path(args.remote).read_text())
        
        strategy = ConflictStrategy(args.strategy)
        resolved = resolver.resolve(local_entry, remote_entry, strategy)
        
        print("解决结果:")
        print(json.dumps(resolved, indent=2, ensure_ascii=False))
    
    elif args.action == "list":
        pending = resolver.list_pending_conflicts()
        print(f"待审核冲突: {len(pending)}")
        for c in pending:
            print(f"- {c['conflict_id']}: {c['conflict']['entry_id']}")
    
    elif args.action == "resolve_manual":
        if not args.local or not args.remote:
            print("需要--local和--remote参数")
            return
        
        conflict_id = input("输入冲突ID: ")
        resolution = input("选择解决方式 (local/remote): ")
        
        success = resolver.resolve_manual_conflict(conflict_id, resolution)
        if success:
            print("冲突已解决")
        else:
            print("解决失败")


if __name__ == "__main__":
    main()
