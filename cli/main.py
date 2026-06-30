"""
MeshIdentity CLI - 命令行接口

提供用户友好的命令行工具：
1. 初始化身份（init）
2. 同步记忆（sync）
3. 切换场景（scene）
4. 查看状态（status）
5. 解决冲突（conflict）

使用: mesh-id <command> [options]
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from did.manager import DIDManager
from sync.engine import MemorySyncEngine
from resolve.conflict import ConflictResolver, ConflictStrategy
from scene.adapter import SceneAdapter, SceneType
from storage.nas_storage import NASStorage


class MeshIdentityCLI:
    """MeshIdentity命令行接口"""
    
    def __init__(self):
        self.parser = self._create_parser()
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """创建命令行解析器"""
        parser = argparse.ArgumentParser(
            prog="mesh-id",
            description="MeshIdentity - 本地Agent多终端统一身份与记忆同步",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
示例:
  mesh-id init --name "MyAgent"           # 初始化身份
  mesh-id sync --push                     # 推送记忆到NAS
  mesh-id sync --pull                     # 从NAS拉取记忆
  mesh-id scene set work                  # 切换到工作场景
  mesh-id status                          # 查看同步状态
  mesh-id conflict list                   # 查看待解决冲突
            """
        )
        
        subparsers = parser.add_subparsers(dest="command", help="可用命令")
        
        # init命令
        init_parser = subparsers.add_parser("init", help="初始化DID身份")
        init_parser.add_argument("--name", help="Agent名称")
        init_parser.add_argument("--storage", default="Z:/qclaw/did",
                                help="DID存储路径")
        init_parser.add_argument("--force", action="store_true",
                                help="强制重新生成（会丢失现有身份）")
        
        # sync命令
        sync_parser = subparsers.add_parser("sync", help="同步记忆")
        sync_parser.add_argument("--push", action="store_true",
                                help="推送本地记忆到NAS")
        sync_parser.add_argument("--pull", action="store_true",
                                help="从NAS拉取记忆")
        sync_parser.add_argument("--bidirectional", action="store_true",
                                help="双向同步（默认）")
        sync_parser.add_argument("--terminal", help="终端ID")
        
        # scene命令
        scene_parser = subparsers.add_parser("scene", help="场景管理")
        scene_subparsers = scene_parser.add_subparsers(dest="scene_command")
        
        scene_set = scene_subparsers.add_parser("set", help="切换场景")
        scene_set.add_argument("scene_name", help="场景名称（work/personal/development/自定义）")
        
        scene_get = scene_subparsers.add_parser("get", help="查看当前场景")
        scene_get.add_argument("--key", help="查看特定配置项")
        
        scene_list = scene_subparsers.add_parser("list", help="列出所有场景")
        
        scene_create = scene_subparsers.add_parser("create", help="创建自定义场景")
        scene_create.add_argument("name", help="场景名称")
        scene_create.add_argument("--description", help="场景描述")
        scene_create.add_argument("--behavior", help="行为配置（JSON格式）")
        
        # status命令
        status_parser = subparsers.add_parser("status", help="查看状态")
        status_parser.add_argument("--json", action="store_true",
                                  help="以JSON格式输出")
        
        # conflict命令
        conflict_parser = subparsers.add_parser("conflict", help="冲突管理")
        conflict_subparsers = conflict_parser.add_subparsers(dest="conflict_command")
        
        conflict_list = conflict_subparsers.add_parser("list", help="列出待解决冲突")
        conflict_resolve = conflict_subparsers.add_parser("resolve", help="解决冲突")
        conflict_resolve.add_argument("conflict_id", help="冲突ID")
        conflict_resolve.add_argument("resolution", choices=["local", "remote"],
                                     help="解决方式")
        
        # version命令
        subparsers.add_parser("version", help="查看版本")
        
        return parser
    
    def run(self, args=None):
        """运行CLI"""
        args = self.parser.parse_args(args)
        
        if not args.command:
            self.parser.print_help()
            return
        
        # 分发到对应处理函数
        if args.command == "init":
            self.cmd_init(args)
        elif args.command == "sync":
            self.cmd_sync(args)
        elif args.command == "scene":
            self.cmd_scene(args)
        elif args.command == "status":
            self.cmd_status(args)
        elif args.command == "conflict":
            self.cmd_conflict(args)
        elif args.command == "version":
            self.cmd_version(args)
        else:
            self.parser.print_help()
    
    def cmd_init(self, args):
        """处理init命令"""
        print("正在初始化DID身份...")
        
        try:
            manager = DIDManager(args.storage)
            
            # 检查是否已存在
            if manager.load_did() and not args.force:
                print("错误: DID已存在。使用--force强制重新生成（会丢失现有身份）")
                return
            
            # 生成DID
            result = manager.generate_did(force=args.force)
            
            print("✅ DID身份已生成:")
            print(f"  DID: {result['did']}")
            print(f"  存储路径: {args.storage}")
            print(f"  私钥路径: {result['private_key_path']}")
            print("")
            print("⚠️  警告: 私钥已保存到本地，请妥善保管！丢失后无法恢复身份。")
            
            # 计算soul_anchor
            print("正在计算soul_anchor...")
            anchor = manager.compute_soul_anchor()
            print(f"✅ soul_anchor: {anchor}")
            
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)
    
    def cmd_sync(self, args):
        """处理sync命令"""
        print("正在同步记忆...")
        
        try:
            engine = MemorySyncEngine(terminal_id=args.terminal)
            
            if args.push and not args.pull:
                # 只推送
                result = engine.push_memory()
                self._print_sync_result("推送", result)
            elif args.pull and not args.push:
                # 只拉取
                result = engine.pull_memory()
                self._print_sync_result("拉取", result)
            else:
                # 双向同步（默认）
                result = engine.sync()
                self._print_sync_result("推送", result["push"])
                self._print_sync_result("拉取", result["pull"])
            
            print(f"✅ 同步完成")
            
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)
    
    def _print_sync_result(self, action: str, result: Dict):
        """打印同步结果"""
        if not result:
            return
        
        print(f"\n{action}结果:")
        print(f"  成功: {result.get('pushed', result.get('pulled', 0))}")
        print(f"  跳过: {result.get('skipped', 0)}")
        print(f"  冲突: {result.get('conflicts', 0)}")
        
        if result.get("errors"):
            print(f"  错误: {len(result['errors'])}")
            for err in result["errors"][:5]:  # 只显示前5个错误
                print(f"    - {err}")
    
    def cmd_scene(self, args):
        """处理scene命令"""
        if not args.scene_command:
            print("需要子命令: set/get/list/create")
            return
        
        try:
            adapter = SceneAdapter()
            
            if args.scene_command == "set":
                config = adapter.set_scene(args.scene_name)
                print(f"✅ 已切换到场景: {config['name']}")
                print(f"  描述: {config['description']}")
                print(f"  语气: {config['behavior']['tone']}")
                print(f"  详细程度: {config['behavior']['verbosity']}")
                
            elif args.scene_command == "get":
                if args.key:
                    value = adapter.get_behavior(args.key)
                    print(f"{args.key}: {value}")
                else:
                    config = adapter.get_current_scene()
                    print(json.dumps(config, indent=2, ensure_ascii=False))
                    
            elif args.scene_command == "list":
                scenes = adapter.list_scenes()
                print("预定义场景:")
                for s in scenes["preset"]:
                    print(f"  - {s}")
                print("自定义场景:")
                for s in scenes["custom"]:
                    print(f"  - {s}")
                    
            elif args.scene_command == "create":
                # 解析behavior JSON
                if args.behavior:
                    behavior = json.loads(args.behavior)
                else:
                    behavior = {}
                    print("请输入行为配置（JSON格式，输入空行结束）:")
                    while True:
                        line = sys.stdin.readline().strip()
                        if not line:
                            break
                        key, value = line.split(":", 1)
                        behavior[key.strip()] = value.strip()
                
                config = adapter.create_custom_scene(
                    args.name, 
                    args.description or "", 
                    behavior
                )
                print(f"✅ 自定义场景已创建: {args.name}")
                
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)
    
    def cmd_status(self, args):
        """处理status命令"""
        print("正在获取状态...")
        
        try:
            # 收集状态信息
            status = {
                "timestamp": datetime.now().isoformat(),
                "did": None,
                "sync": None,
                "scene": None,
                "storage": None
            }
            
            # DID状态
            manager = DIDManager()
            did_data = manager.load_did()
            if did_data:
                status["did"] = {
                    "exists": True,
                    "did": did_data["did"],
                    "has_private_key": Path(did_data["private_key_path"]).exists()
                }
            else:
                status["did"] = {"exists": False}
            
            # 同步状态
            engine = MemorySyncEngine()
            state = engine.state
            status["sync"] = {
                "last_sync": state.get("last_sync"),
                "last_push": state.get("last_push"),
                "last_pull": state.get("last_pull"),
                "vector_clock": state.get("vector_clock", {})
            }
            
            # 场景状态
            adapter = SceneAdapter()
            scene = adapter.get_current_scene()
            status["scene"] = {
                "current": scene["scene_name"],
                "name": scene["name"],
                "is_preset": scene["is_preset"]
            }
            
            # 存储状态
            storage = NASStorage()
            health = storage.health_check()
            status["storage"] = health
            
            # 输出
            if args.json:
                print(json.dumps(status, indent=2, ensure_ascii=False))
            else:
                self._print_status_human(status)
                
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)
    
    def _print_status_human(self, status: Dict):
        """以人类可读格式打印状态"""
        print("=" * 50)
        print("MeshIdentity 状态")
        print("=" * 50)
        
        # DID状态
        print("\n[身份]")
        if status["did"]["exists"]:
            print(f"  DID: {status['did']['did'][:50]}...")
            print(f"  私钥: {'✅ 存在' if status['did']['has_private_key'] else '❌ 缺失'}")
        else:
            print("  ❌ DID未初始化")
        
        # 同步状态
        print("\n[同步]")
        sync = status["sync"]
        print(f"  上次同步: {sync['last_sync'] or '从未'}")
        print(f"  上次推送: {sync['last_push'] or '从未'}")
        print(f"  上次拉取: {sync['last_pull'] or '从未'}")
        if sync["vector_clock"]:
            print(f"  向量时钟: {sync['vector_clock']}")
        
        # 场景状态
        print("\n[场景]")
        scene = status["scene"]
        print(f"  当前: {scene['current']} ({scene['name']})")
        print(f"  类型: {'预定义' if scene['is_preset'] else '自定义'}")
        
        # 存储状态
        print("\n[存储]")
        storage = status["storage"]
        if storage["path_exists"]:
            print(f"  路径: 存在 ✅")
            print(f"  可读: {'✅' if storage['readable'] else '❌'}")
            print(f"  可写: {'✅' if storage['writable'] else '❌'}")
            if storage["latency_ms"]:
                print(f"  延迟: {storage['latency_ms']}ms")
        else:
            print(f"  路径: 不存在 ❌")
        
        print("\n" + "=" * 50)
    
    def cmd_conflict(self, args):
        """处理conflict命令"""
        if not args.conflict_command:
            print("需要子命令: list/resolve")
            return
        
        try:
            resolver = ConflictResolver()
            
            if args.conflict_command == "list":
                pending = resolver.list_pending_conflicts()
                print(f"待解决冲突: {len(pending)}")
                for c in pending:
                    print(f"  - ID: {c['conflict_id']}")
                    print(f"    条目: {c['conflict']['entry_id']}")
                    print(f"    检测时间: {c['created_at']}")
                    print()
                    
            elif args.conflict_command == "resolve":
                success = resolver.resolve_manual_conflict(
                    args.conflict_id, 
                    args.resolution
                )
                if success:
                    print(f"✅ 冲突已解决: {args.conflict_id}")
                    print(f"  解决方式: {args.resolution}")
                else:
                    print(f"❌ 解决失败: 冲突不存在或已解决")
                    
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)
    
    def cmd_version(self, args):
        """处理version命令"""
        version = {
            "mesh-identity": "0.1.0",
            "python": sys.version,
            "author": "Nyx (硅基文明数据库项目)"
        }
        print(json.dumps(version, indent=2, ensure_ascii=False))


def main():
    """入口函数"""
    cli = MeshIdentityCLI()
    cli.run()


if __name__ == "__main__":
    main()
