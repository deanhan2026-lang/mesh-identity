"""
多实例 DID 绑定模块

实现一个主DID绑定多个终端实例的核心能力：
1. 为主DID绑定多个终端实例
2. 为每个实例生成子DID (delegated DID)
3. 管理实例生命周期 (注册/撤销/查询)
4. W3C DID Document扩展支持

遵循W3C DID规范，兼容现有DIDManager。
"""

import os
import json
import hashlib
import importlib.util
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# 动态导入DIDManager，避免相对导入问题
def _import_did_manager():
    """动态导入DIDManager类"""
    manager_py = Path(__file__).parent / "manager.py"
    
    # 读取manager.py内容并修改导入语句
    with open(manager_py, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # 移除相对导入（NASStorage实际上未使用）
    code = code.replace(
        "from ..storage.nas_storage import NASStorage",
        "# from ..storage.nas_storage import NASStorage  # 已移除相对导入"
    )
    
    # 创建临时模块
    spec = importlib.util.spec_from_file_location("did_manager", manager_py)
    manager_module = importlib.util.module_from_spec(spec)
    
    # 执行修改后的代码
    exec(compile(code, str(manager_py), 'exec'), manager_module.__dict__)
    
    return manager_module.DIDManager

DIDManager = _import_did_manager()


class MultiInstanceDIDManager:
    """
    多实例DID绑定管理器
    
    核心能力:
    - 为主DID绑定多个终端实例
    - 为每个实例生成子DID (delegated DID)
    - 管理实例生命周期 (注册/撤销/查询)
    """
    
    def __init__(self, storage_path: str = "Z:/qclaw/did"):
        """
        初始化多实例DID管理器
        
        Args:
            storage_path: DID凭证存储路径（NAS共享目录）
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 继承DIDManager
        self._did_manager = DIDManager(storage_path)
        
        # 实例存储目录
        self._instances_base = self.storage_path / "instances"
        self._instances_base.mkdir(parents=True, exist_ok=True)
    
    def _get_primary_did_hash(self, primary_did: str) -> str:
        """
        计算主DID的哈希（用于存储路径）
        
        Args:
            primary_did: 主DID
            
        Returns:
            主DID的SHA256前16位16进制字符
        """
        did_hash = hashlib.sha256(primary_did.encode('utf-8')).hexdigest()
        return did_hash[:16]
    
    def _get_instance_storage_path(self, primary_did: str) -> Path:
        """
        获取主DID对应的实例存储路径
        
        Args:
            primary_did: 主DID
            
        Returns:
            实例存储目录路径
        """
        did_hash = self._get_primary_did_hash(primary_did)
        return self._instances_base / did_hash
    
    def _get_registry_path(self, primary_did: str) -> Path:
        """
        获取实例注册表文件路径
        
        Args:
            primary_did: 主DID
            
        Returns:
            注册表文件路径
        """
        return self._get_instance_storage_path(primary_did) / "registry.json"
    
    def _get_did_document_path(self, primary_did: str, instance_id: str) -> Path:
        """
        获取实例DID文档路径
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            
        Returns:
            DID文档路径
        """
        did_hash = self._get_primary_did_hash(primary_did)
        return self._instances_base / did_hash / "did_documents" / f"{instance_id}.json"
    
    def _load_registry(self, primary_did: str) -> Dict:
        """
        加载实例注册表
        
        Args:
            primary_did: 主DID
            
        Returns:
            注册表字典，如果不存在返回空注册表
        """
        registry_path = self._get_registry_path(primary_did)
        
        if not registry_path.exists():
            return {
                "primary_did": primary_did,
                "instances": {},
                "updated_at": datetime.now().isoformat()
            }
        
        return json.loads(registry_path.read_text(encoding='utf-8'))
    
    def _save_registry(self, primary_did: str, registry: Dict):
        """
        保存实例注册表
        
        Args:
            primary_did: 主DID
            registry: 注册表字典
        """
        registry_path = self._get_registry_path(primary_did)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        registry["updated_at"] = datetime.now().isoformat()
        registry_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
    
    def _save_instance_did_document(self, primary_did: str, instance_id: str, did_document: Dict):
        """
        保存实例DID文档
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            did_document: DID文档
        """
        doc_path = self._get_did_document_path(primary_did, instance_id)
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        
        doc_path.write_text(
            json.dumps(did_document, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
    
    def _load_instance_did_document(self, primary_did: str, instance_id: str) -> Optional[Dict]:
        """
        加载实例DID文档
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            
        Returns:
            DID文档字典，如果不存在返回None
        """
        doc_path = self._get_did_document_path(primary_did, instance_id)
        
        if not doc_path.exists():
            return None
        
        return json.loads(doc_path.read_text(encoding='utf-8'))
    
    def generate_primary_did(self, password: str, force: bool = False) -> Dict:
        """
        生成主DID (委托给DIDManager)
        
        Args:
            password: 用于加密私钥的密码
            force: 是否强制重新生成
            
        Returns:
            {"did": "...", "pubkey": "...", "soul_anchor": "..."}
            
        Raises:
            RuntimeError: 缺少依赖库
            FileExistsError: DID已存在且force=False
        """
        result = self._did_manager.generate_did(password, force)
        
        # 提取需要的信息
        did_document = result["did_document"]
        did = did_document["id"]
        pubkey = did_document["publicKey"][0]["publicKeyHex"]
        
        # 计算soul_anchor
        try:
            soul_anchor = self._did_manager.compute_soul_anchor()
        except FileNotFoundError:
            soul_anchor = None
        
        return {
            "did": did,
            "pubkey": pubkey,
            "soul_anchor": soul_anchor,
            "did_document": did_document
        }
    
    def register_instance(
        self,
        primary_did: str,
        instance_id: str,
        platform: str,
        instance_pubkey: str = None
    ) -> Dict:
        """
        注册实例子身份
        
        Args:
            primary_did: 主DID
            instance_id: 实例唯一标识符 (如 "nyx-windows", "nyx-mac", "kronos-heng")
            platform: 平台描述 (如 "QClaw (Windows)")
            instance_pubkey: 实例的公钥 (可选，默认继承主DID密钥)
        
        Returns:
            {
                "instance_did": "{primary_did}/instance/{instance_id}",
                "registered_at": ISO时间戳,
                "status": "active"
            }
        
        Raises:
            ValueError: 实例已存在 / 主DID不存在
        """
        # 验证主DID是否存在
        did_data = self._did_manager.load_did()
        if did_data is None:
            raise ValueError("主DID未找到")
        
        if did_data["did"] != primary_did:
            raise ValueError(f"主DID不匹配: 本地={did_data['did']}, 提供={primary_did}")
        
        # 加载注册表
        registry = self._load_registry(primary_did)
        
        # 检查实例是否已存在
        if instance_id in registry["instances"]:
            instance_info = registry["instances"][instance_id]
            if instance_info.get("status") == "active":
                raise ValueError(f"实例已注册: {instance_id}")
            # 如果实例已撤销，允许重新注册（更新状态）
            elif instance_info.get("status") == "revoked":
                # 重新激活实例
                pass
        
        # 生成实例子DID
        instance_did = f"{primary_did}/instance/{instance_id}"
        
        # 获取主DID的公钥（如果没有提供实例公钥）
        if instance_pubkey is None:
            instance_pubkey = self._did_manager.export_public_key()
        
        # 注册时间
        registered_at = datetime.now().isoformat()
        
        # 创建实例信息
        instance_info = {
            "instance_id": instance_id,
            "instance_did": instance_did,
            "platform": platform,
            "instance_pubkey": instance_pubkey,
            "registered_at": registered_at,
            "status": "active"
        }
        
        # 更新注册表
        registry["instances"][instance_id] = instance_info
        self._save_registry(primary_did, registry)
        
        # 创建实例DID文档（W3C DID Document扩展）
        did_document = self._create_instance_did_document(
            primary_did, instance_id, platform, instance_pubkey, registered_at
        )
        self._save_instance_did_document(primary_did, instance_id, did_document)
        
        return {
            "instance_did": instance_did,
            "registered_at": registered_at,
            "status": "active",
            "did_document": did_document
        }
    
    def _create_instance_did_document(
        self,
        primary_did: str,
        instance_id: str,
        platform: str,
        instance_pubkey: str,
        registered_at: str
    ) -> Dict:
        """
        创建实例子DID的W3C DID Document
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            platform: 平台描述
            instance_pubkey: 实例公钥
            registered_at: 注册时间
            
        Returns:
            DID文档字典
        """
        instance_did = f"{primary_did}/instance/{instance_id}"
        
        return {
            "@context": "https://w3id.org/did/v1",
            "id": f"{primary_did}#instance/{instance_id}",
            "controller": primary_did,
            "instance_of": primary_did,
            "type": "AgentInstance",
            "platform": platform,
            "registered_at": registered_at,
            "status": "active",
            "publicKey": [{
                "id": f"{primary_did}#instance/{instance_id}/signing-key",
                "type": "Ed25519VerificationKey2018",
                "controller": primary_did,
                "publicKeyHex": instance_pubkey
            }],
            "authentication": [f"{primary_did}#instance/{instance_id}/signing-key"],
            "alsoKnownAs": [instance_did]
        }
    
    def list_instances(self, primary_did: str) -> List[Dict]:
        """
        列出主DID下所有注册实例
        
        Args:
            primary_did: 主DID
            
        Returns:
            [{"instance_id": "...", "instance_did": "...", "platform": "...", 
              "registered_at": "...", "status": "active"}]
        
        Raises:
            ValueError: 主DID不存在
        """
        # 验证主DID是否存在
        did_data = self._did_manager.load_did()
        if did_data is None:
            raise ValueError("主DID未找到")
        
        if did_data["did"] != primary_did:
            raise ValueError(f"主DID不匹配: 本地={did_data['did']}, 提供={primary_did}")
        
        # 加载注册表
        registry = self._load_registry(primary_did)
        
        # 返回所有实例信息
        instances = []
        for instance_id, instance_info in registry["instances"].items():
            instances.append({
                "instance_id": instance_id,
                "instance_did": instance_info["instance_did"],
                "platform": instance_info["platform"],
                "registered_at": instance_info["registered_at"],
                "status": instance_info.get("status", "active")
            })
        
        return instances
    
    def revoke_instance(self, primary_did: str, instance_id: str) -> bool:
        """
        撤销实例子身份
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            
        Returns:
            True if successful
            
        Raises:
            ValueError: 主DID不存在 / 实例不存在
        """
        # 验证主DID是否存在
        did_data = self._did_manager.load_did()
        if did_data is None:
            raise ValueError("主DID未找到")
        
        if did_data["did"] != primary_did:
            raise ValueError(f"主DID不匹配: 本地={did_data['did']}, 提供={primary_did}")
        
        # 加载注册表
        registry = self._load_registry(primary_did)
        
        # 检查实例是否存在
        if instance_id not in registry["instances"]:
            raise ValueError(f"实例未注册: {instance_id}")
        
        # 更新实例状态
        registry["instances"][instance_id]["status"] = "revoked"
        registry["instances"][instance_id]["revoked_at"] = datetime.now().isoformat()
        
        # 保存注册表
        self._save_registry(primary_did, registry)
        
        # 更新DID文档状态
        did_document = self._load_instance_did_document(primary_did, instance_id)
        if did_document:
            did_document["status"] = "revoked"
            did_document["revoked_at"] = datetime.now().isoformat()
            self._save_instance_did_document(primary_did, instance_id, did_document)
        
        return True
    
    def get_instance_did(self, primary_did: str, instance_id: str) -> str:
        """
        获取实例子DID
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            
        Returns:
            实例子DID，格式: {primary_did}/instance/{instance_id}
            
        Raises:
            ValueError: 主DID不存在 / 实例不存在
        """
        # 验证主DID是否存在
        did_data = self._did_manager.load_did()
        if did_data is None:
            raise ValueError("主DID未找到")
        
        if did_data["did"] != primary_did:
            raise ValueError(f"主DID不匹配: 本地={did_data['did']}, 提供={primary_did}")
        
        # 加载注册表
        registry = self._load_registry(primary_did)
        
        # 检查实例是否存在
        if instance_id not in registry["instances"]:
            raise ValueError(f"实例未注册: {instance_id}")
        
        return registry["instances"][instance_id]["instance_did"]
    
    def verify_instance(self, instance_did: str) -> Dict:
        """
        验证实例子DID是否合法且在有效期
        
        Args:
            instance_did: 实例子DID
            
        Returns:
            {
                "valid": True/False,
                "primary_did": "...",
                "instance_id": "...",
                "status": "active"/"revoked"
            }
        """
        # 解析instance_did
        # 格式: {primary_did}/instance/{instance_id}
        try:
            parts = instance_did.split("/instance/")
            if len(parts) != 2:
                return {"valid": False, "error": "无效的实例DID格式"}
            
            primary_did = parts[0]
            instance_id = parts[1]
        except Exception:
            return {"valid": False, "error": "无法解析实例DID"}
        
        # 验证主DID是否存在
        try:
            did_data = self._did_manager.load_did()
            if did_data is None:
                return {"valid": False, "error": "主DID未找到"}
            
            if did_data["did"] != primary_did:
                return {"valid": False, "error": "主DID不匹配"}
        except Exception as e:
            return {"valid": False, "error": str(e)}
        
        # 加载注册表
        try:
            registry = self._load_registry(primary_did)
        except Exception:
            return {"valid": False, "error": "无法加载实例注册表"}
        
        # 检查实例是否存在
        if instance_id not in registry["instances"]:
            return {"valid": False, "error": f"实例未注册: {instance_id}"}
        
        instance_info = registry["instances"][instance_id]
        status = instance_info.get("status", "active")
        
        return {
            "valid": status == "active",
            "primary_did": primary_did,
            "instance_id": instance_id,
            "status": status,
            "platform": instance_info.get("platform"),
            "registered_at": instance_info.get("registered_at")
        }
    
    def get_instance_info(self, primary_did: str, instance_id: str) -> Optional[Dict]:
        """
        获取实例详细信息
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            
        Returns:
            实例信息字典，如果不存在返回None
        """
        registry = self._load_registry(primary_did)
        
        if instance_id not in registry["instances"]:
            return None
        
        return registry["instances"][instance_id]
    
    def export_instance_did_document(self, primary_did: str, instance_id: str) -> Optional[Dict]:
        """
        导出实例DID文档
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            
        Returns:
            DID文档字典，如果不存在返回None
        """
        return self._load_instance_did_document(primary_did, instance_id)


def main():
    """命令行测试"""
    import argparse
    
    parser = argparse.ArgumentParser(description="多实例DID绑定管理")
    parser.add_argument("action", choices=["generate", "register", "list", "revoke", "verify", "get-did"],
                        help="操作类型")
    parser.add_argument("--storage", default="Z:/qclaw/did",
                        help="DID存储路径")
    parser.add_argument("--password", default=None,
                        help="私钥加密密码")
    parser.add_argument("--force", action="store_true",
                        help="强制重新生成")
    parser.add_argument("--primary-did", default=None,
                        help="主DID")
    parser.add_argument("--instance-id", default=None,
                        help="实例ID")
    parser.add_argument("--platform", default=None,
                        help="平台描述")
    
    args = parser.parse_args()
    
    manager = MultiInstanceDIDManager(args.storage)
    
    if args.action == "generate":
        if not args.password:
            print("❌ 错误: 生成DID需要 --password 参数")
            return
        result = manager.generate_primary_did(password=args.password, force=args.force)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    elif args.action == "register":
        if not args.primary_did or not args.instance_id or not args.platform:
            print("❌ 错误: 注册实例需要 --primary-did, --instance-id, --platform 参数")
            return
        try:
            result = manager.register_instance(args.primary_did, args.instance_id, args.platform)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except ValueError as e:
            print(f"❌ {e}")
            
    elif args.action == "list":
        if not args.primary_did:
            print("❌ 错误: 列出实例需要 --primary-did 参数")
            return
        try:
            instances = manager.list_instances(args.primary_did)
            print(json.dumps(instances, indent=2, ensure_ascii=False))
        except ValueError as e:
            print(f"❌ {e}")
            
    elif args.action == "revoke":
        if not args.primary_did or not args.instance_id:
            print("❌ 错误: 撤销实例需要 --primary-did, --instance-id 参数")
            return
        try:
            result = manager.revoke_instance(args.primary_did, args.instance_id)
            print(f"✅ 实例已撤销: {args.instance_id}")
        except ValueError as e:
            print(f"❌ {e}")
            
    elif args.action == "verify":
        if not args.primary_did:
            print("❌ 错误: 验证需要 --primary-did 参数 (实例DID)")
            return
        result = manager.verify_instance(args.primary_did)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    elif args.action == "get-did":
        if not args.primary_did or not args.instance_id:
            print("❌ 错误: 获取实例DID需要 --primary-did, --instance-id 参数")
            return
        try:
            instance_did = manager.get_instance_did(args.primary_did, args.instance_id)
            print(f"实例DID: {instance_did}")
        except ValueError as e:
            print(f"❌ {e}")


if __name__ == "__main__":
    main()
