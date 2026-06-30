"""
MeshIdentity CLI - 命令行接口

提供用户友好的命令行工具：
1. 初始化身份（init）
2. 同步记忆（sync）
3. 切换场景（scene）
4. 查看状态（status）
5. 解决冲突（conflict）
6. 修改密码（change-password）
7. 迁移旧版私钥（migrate）

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
        self.parser = argparse.ArgumentParser(
            prog="mesh-id",
            description="MeshIdentity - 本地Agent多终端统一身份与记忆同步",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
示例:
  mesh-id init --name "MyAgent" --password "mypass"    # 初始化身份（密码加密）
  mesh-id sync --push                                   # 推送记忆到NAS
  mesh-id sync --pull                                   # 从NAS拉取记忆
  mesh-id scene set work                                # 切换到工作场景
  mesh-id status                                        # 查看同步状态
  mesh-id conflict list                                 # 查看待解决冲突
  mesh-id change-password --old-password "old" --new-password "new"  # 改密
  mesh-id migrate --password "mypass"                   # 迁移旧版明文私钥
            """
        )
        
        subparsers = self.parser.add_subparsers(dest="command", help="可用命令")
        
        # init命令
        init_parser = subparsers.add_parser("init", help="初始化DID身份（私钥加密存储）")
        init_parser.add_argument("--name", help="Agent名称")
        init_parser.add_argument("--password", required=True,
                                help="私钥加密密码（必填，不可遗忘！）")
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
                                help="双向同步")
        sync_parser.add_argument("--terminal", default="nyx-windows",
                                help="终端标识（默认: nyx-windows）")
        sync_parser.add_argument("--storage", default="Z:/qclaw/memory_vault",
                                help="记忆存储路径")
        
        # scene命令
        scene_parser = subparsers.add_parser("scene", help="场景管理")
        scene_parser.add_argument("action", choices=["set", "get", "list"],
                                help="场景操作")
        scene_parser.add_argument("scene_type", nargs="?",
                                choices=["work", "personal", "dev"],
                                help="场景类型")
        scene_parser.add_argument("--storage", default="Z:/qclaw/scene_config",
                                help="场景配置路径")
        
        # status命令
        status_parser = subparsers.add_parser("status", help="查看同步状态")
        status_parser.add_argument("--storage", default="Z:/qclaw/memory_vault",
                                help="记忆存储路径")
        status_parser.add_argument("--terminal", default="nyx-windows",
                                help="终端标识")
        
        # conflict命令
        conflict_parser = subparsers.add_parser("conflict", help="冲突管理")
        conflict_parser.add_argument("action", choices=["list", "resolve", "status"],
                                    help="冲突操作")
        conflict_parser.add_argument("--id", dest="conflict_id",
                                    help="冲突ID")
        conflict_parser.add_argument("--strategy", default="lww",
                                    choices=["lww", "manual"],
                                    help="解决策略")
        conflict_parser.add_argument("--storage", default="Z:/qclaw/memory_vault",
                                    help="记忆存储路径")
        
        # change-password命令
        pwd_parser = subparsers.add_parser("change-password", help="修改私钥加密密码")
        pwd_parser.add_argument("--old-password", required=True, help="当前密码")
        pwd_parser.add_argument("--new-password", required=True, help="新密码")
        pwd_parser.add_argument("--storage", default="Z:/qclaw/did", help="DID存储路径")
        
        # migrate命令
        mig_parser = subparsers.add_parser("migrate", help="从旧版明文私钥迁移到加密存储")
        mig_parser.add_argument("--password", required=True, help="用于加密的新密码")
        mig_parser.add_argument("--storage", default="Z:/qclaw/did", help="DID存储路径")
        
        # version命令
        subparsers.add_parser("version", help="显示版本信息")
    
    def run(self, args=None):
        """运行CLI"""
        args = self.parser.parse_args(args)
        
        if args.command is None:
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
        elif args.command == "change-password":
            self.cmd_change_password(args)
        elif args.command == "migrate":
            self.cmd_migrate(args)
        elif args.command == "version":
            self.cmd_version(args)
        else:
            self.parser.print_help()
    
    def cmd_init(self, args):
        """处理init命令（加密存储版）"""
        print("正在初始化DID身份（私钥加密存储）...")
        
        try:
            manager = DIDManager(args.storage)
            
            # 检查是否已存在
            existing = manager.load_did()
            if existing and not args.force:
                print("错误: DID已存在。使用--force强制重新生成（会丢失现有身份）")
                return
            
            # 生成DID（带密码加密）
            result = manager.generate_did(password=args.password, force=args.force)
            
            print("\n✅ DID身份已生成（私钥已加密存储）:")
            print(f"  DID: {result['did']}")
            print(f"  存储路径: {args.storage}")
            print(f"  加密私钥: {result['encrypted_key_path']}")
            print(f"  警告: 私钥已加密存储，请牢记密码！遗忘后无法恢复。\n")
            
            # 计算soul_anchor
            print("正在计算soul_anchor...")
            anchor = manager.compute_soul_anchor()
            print(f"  ✅ soul_anchor: {anchor[:16]}...{anchor[-16:]}\n")
            
            # 验证加密
            print("正在验证密码加密...")
            verify = manager.load_did(password=args.password)
            if verify and verify.get("private_key_loaded"):
                print("  ✅ 密码加密验证通过\n")
            print("✅ DID初始化完成。可以使用 `mesh-id status` 查看状态。")
            
        except Exception as e:
            print(f"❌ 错误: {e}")
            sys.exit(1)
    
    def cmd_change_password(self, args):
        """修改私钥加密密码"""
        print("正在修改私钥加密密码...")
        try:
            manager = DIDManager(args.storage)
            result = manager.change_password(args.old_password, args.new_password)
            print(f"  ✅ {result['message']}")
        except ValueError as e:
            print(f"❌ 错误: {e}")
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"❌ 错误: {e}")
            sys.exit(1)
    
    def cmd_migrate(self, args):
        """从旧版明文私钥迁移到加密存储"""
        print("正在从旧版明文私钥迁移到加密存储...")
        try:
            manager = DIDManager(args.storage)
            result = manager.migrate_from_plaintext(args.password)
            print(f"  ✅ {result['message']}")
        except FileNotFoundError as e:
            print(f"❌ 错误: {e}")
            sys.exit(1)
    
    def cmd_sync(self, args):
        """处理sync命令"""
        print("正在同步记忆...")
        
        try:
            engine = MemorySyncEngine(terminal_id=args.terminal)
            
            if args.push and not args.pull:
                # 只推送
                result = engine.push_memory()
                print(f"✅ 已推送: {result.get('pushed', 0)} 条记忆")
            elif args.pull and not args.push:
                # 只拉取
                result = engine.pull_memory()
                print(f"✅ 已拉取: {result.get('pulled', 0)} 条记忆")
            else:
                # 双向同步
                result = engine.sync()
                push_count = result.get("push", {}).get("pushed", 0)
                pull_count = result.get("pull", {}).get("pulled", 0)
                print(f"✅ 双向同步完成")
                print(f"  推送: {push_count} 条")
                print(f"  拉取: {pull_count} 条")
            
            # 检查冲突
            conflicts = engine.detect_conflicts()
            if conflicts:
                print(f"⚠️  检测到 {len(conflicts)} 个冲突，使用 `mesh-id conflict` 处理")
            
        except Exception as e:
            print(f"❌ 同步失败: {e}")
            sys.exit(1)
    
    def cmd_scene(self, args):
        """处理scene命令"""
        try:
            adapter = SceneAdapter(args.storage)
            
            if args.action == "set" and args.scene_type:
                scene = SceneType(args.scene_type)
                config = adapter.activate_scene(scene)
                print(f"✅ 已切换到 {scene.value} 场景")
                print(f"  配置: {json.dumps(config, indent=2, ensure_ascii=False)}")
            
            elif args.action == "get":
                current = adapter.get_current_scene()
                if current:
                    print(f"当前场景: {current.name} ({current.value})")
                else:
                    print("未设置场景")
            
            elif args.action == "list":
                scenes = SceneType.__members__
                print("可用场景:")
                for name, scene in scenes.items():
                    print(f"  - {name}: {scene.value}")
        
        except Exception as e:
            print(f"❌ 场景操作失败: {e}")
            sys.exit(1)
    
    def cmd_status(self, args):
        """处理status命令"""
        print("========== MeshIdentity 状态 ==========")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"终端: {args.terminal}\n")
        
        try:
            # DID状态
            manager = DIDManager()
            did_data = manager.load_did()
            if did_data:
                print(f"🔑 DID: {did_data['did'][:30]}...")
                print(f"  DID文档: {did_data.get('did_document', {}).get('id', 'N/A')}")
                print(f"  私钥: {'✅ 已加密' if did_data.get('encrypted_key_path') else '❌ 未找到'}\n")
            else:
                print("🔑 DID: ❌ 未初始化\n")
            
            # 同步状态
            try:
                engine = MemorySyncEngine(args.terminal)
                sync_status = engine.get_sync_status()
                print(f"🔄 同步状态:")
                print(f"  本地记忆: {sync_status.get('local_count', 'N/A')} 条")
                print(f"  NAS同步: {'✅ 正常' if sync_status.get('nas_connected') else '❌ 断开'}")
                print(f"  向量时钟: {sync_status.get('vector_clock', '未知')}\n")
            except Exception:
                print("🔄 同步状态: 无法检测\n")
            
            # 场景状态
            try:
                adapter = SceneAdapter()
                current_scene = adapter.get_current_scene()
                print(f"🎯 当前场景: {current_scene.value if current_scene else '未设置'}\n")
            except Exception:
                print("🎯 当前场景: 无法检测\n")
            
            # 最近同步
            print(f"📋 最近同步: {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            print(f"❌ 状态获取失败: {e}")
    
    def cmd_conflict(self, args):
        """处理conflict命令"""
        try:
            resolver = ConflictResolver(ConflictStrategy(args.strategy))
            
            if args.action == "list":
                conflicts = resolver.list_conflicts()
                if conflicts:
                    print(f"检测到 {len(conflicts)} 个冲突:")
                    for conflict in conflicts:
                        print(f"  - [{conflict['id']}] {conflict['description']}")
                        print(f"    本地: {conflict['local_version']}")
                        print(f"    NAS: {conflict['nas_version']}")
                else:
                    print("✅ 无待解决冲突")
            
            elif args.action == "resolve":
                if not args.conflict_id:
                    print("❌ 请指定冲突ID（--id）")
                    return
                
                result = resolver.resolve(args.conflict_id)
                if result.get("resolved"):
                    print(f"✅ 冲突 {args.conflict_id} 已解决")
                else:
                    print(f"⚠️  冲突 {args.conflict_id} 需人工审核")
                    print(f"  详细信息: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            elif args.action == "status":
                status = resolver.resolver_status()
                print(f"冲突解决器状态:")
                print(f"  策略: {status.get('strategy', 'N/A')}")
                print(f"  待处理: {status.get('pending', 0)}")
                print(f"  已解决: {status.get('resolved', 0)}")
        
        except Exception as e:
            print(f"❌ 冲突操作失败: {e}")
            sys.exit(1)
    
    def cmd_version(self, args):
        """显示版本信息"""
        print(f"MeshIdentity v0.1.0")
        print(f"MIT License")
        print(f"2026 silicon-civilization-kb")


def main():
    """入口函数"""
    cli = MeshIdentityCLI()
    cli.run()


if __name__ == "__main__":
    main()
