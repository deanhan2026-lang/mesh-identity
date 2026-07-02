"""
DID身份鉴权模块

实现基于DID的操作签名鉴权，为MemGuard提供"谁可以干什么"的管控能力。

核心功能:
1. 为操作生成带签名的一次性鉴权令牌
2. 验证令牌合法性（签名 + 有效期 + 权限）
3. 基于权限矩阵的访问控制
"""

import os
import json
import base64
import hashlib
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any


# 动态导入DIDManager和MultiInstanceDIDManager，避免相对导入问题
def _import_did_managers():
    """动态导入DID管理器类"""
    project_root = Path(__file__).parent.parent
    
    # 导入DIDManager
    manager_py = project_root / "did" / "manager.py"
    with open(manager_py, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # 移除相对导入
    code = code.replace(
        "from ..storage.nas_storage import NASStorage",
        "# from ..storage.nas_storage import NASStorage  # 已移除相对导入"
    )
    
    # 创建临时模块
    spec = importlib.util.spec_from_file_location("did_manager", manager_py)
    manager_module = importlib.util.module_from_spec(spec)
    exec(compile(code, str(manager_py), 'exec'), manager_module.__dict__)
    DIDManager = manager_module.DIDManager
    
    # 导入MultiInstanceDIDManager
    multi_instance_py = project_root / "did" / "multi_instance.py"
    with open(multi_instance_py, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # 创建临时模块
    spec = importlib.util.spec_from_file_location("multi_instance", multi_instance_py)
    multi_instance_module = importlib.util.module_from_spec(spec)
    exec(compile(code, str(multi_instance_py), 'exec'), multi_instance_module.__dict__)
    MultiInstanceDIDManager = multi_instance_module.MultiInstanceDIDManager
    
    return DIDManager, MultiInstanceDIDManager


DIDManager, MultiInstanceDIDManager = _import_did_managers()


class DIDAuthenticator:
    """
    DID身份鉴权器
    
    核心能力:
    - 为操作生成带签名的一次性鉴权令牌
    - 验证令牌合法性（签名 + 有效期 + 权限）
    - 基于权限矩阵的访问控制
    """
    
    # 权限矩阵
    PERMISSION_MATRIX = {
        "memory_write": {
            "primary_did_holder": True,
            "registered_instance": True,  # 本人
            "unregistered_instance": False
        },
        "memory_read": {
            "primary_did_holder": True,
            "registered_instance": True,
            "unregistered_instance": True
        },
        "baseline_admin": {
            "primary_did_holder": True,
            "registered_instance": False,
            "unregistered_instance": False
        },
        "instance_register": {
            "primary_did_holder": True,
            "registered_instance": False,
            "unregistered_instance": False
        },
        "instance_revoke": {
            "primary_did_holder": True,
            "registered_instance": False,
            "unregistered_instance": False
        }
    }
    
    def __init__(self, storage_path: str = "Z:/qclaw/did", private_key_obj=None, debug: bool = False):
        """
        初始化DID鉴权器
        
        Args:
            storage_path: DID凭证存储路径（NAS共享目录）
            private_key_obj: 解密后的nacl SigningKey对象
                           如果为None，则需要每次调用create_auth_token时传入密码
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 私钥对象（会话模式）
        self._private_key_obj = private_key_obj
        
        # DID管理器
        self._did_manager = DIDManager(storage_path)
        self._multi_instance_manager = MultiInstanceDIDManager(storage_path)
        
        # 令牌存储目录（防重放）
        self._auth_tokens_path = self.storage_path / "auth_tokens"
        self._auth_tokens_path.mkdir(parents=True, exist_ok=True)
        
        # 调试模式
        self._debug = False  # 关闭调试模式
    
    def _generate_nonce(self) -> str:
        """
        生成随机nonce（防重放攻击）
        
        Returns:
            16字节随机数的hex字符串
        """
        return os.urandom(16).hex()
    
    def _base64url_encode(self, data: bytes) -> str:
        """
        Base64URL编码（无填充）
        
        Args:
            data: 原始字节
            
        Returns:
            Base64URL编码字符串
        """
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')
    
    def _base64url_decode(self, data: str) -> bytes:
        """
        Base64URL解码（无填充）
        
        Args:
            data: Base64URL编码字符串
            
        Returns:
            原始字节
        """
        # 添加填充
        padding = 4 - len(data) % 4
        if padding != 4:
            data += '=' * padding
        return base64.urlsafe_b64decode(data)
    
    def _create_token_header(self) -> Dict:
        """
        创建令牌头
        
        Returns:
            令牌头字典
        """
        return {
            "alg": "Ed25519",
            "typ": "DID-Auth-Token",
            "version": "1.0"
        }
    
    def _create_token_payload(
        self,
        primary_did: str,
        instance_id: str,
        action: str,
        expires_in: int
    ) -> Dict:
        """
        创建令牌负载
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            action: 操作类型
            expires_in: 有效期（秒）
            
        Returns:
            令牌负载字典
        """
        now = datetime.now()
        exp = now + timedelta(seconds=expires_in)
        nonce = self._generate_nonce()
        
        return {
            "did": primary_did,
            "instance_id": instance_id,
            "action": action,
            "iat": int(now.timestamp()),  # issued at
            "exp": int(exp.timestamp()),   # expires
            "nonce": nonce
        }
    
    def _get_signing_key(self, password: str = None):
        """
        获取签名密钥
        
        Args:
            password: 解密私钥的密码（如果未使用会话模式）
            
        Returns:
            nacl.signing.SigningKey对象
        """
        import nacl.signing
        
        if self._private_key_obj is not None:
            return self._private_key_obj
        elif password is not None:
            # 使用密码解密私钥
            did_data = self._did_manager.load_did(password)
            if did_data is None or not did_data.get("private_key_loaded"):
                raise ValueError("无法加载私钥，密码可能错误")
            private_key_bytes = did_data["private_key"]
            return nacl.signing.SigningKey(private_key_bytes)
        else:
            raise ValueError("需要密码或私钥对象才能签名")
    
    def _get_verify_key(self, did: str = None):
        """
        获取验证密钥
        
        Args:
            did: DID标识符（目前未使用，使用本地DID的公钥）
            
        Returns:
            nacl.signing.VerifyKey对象
        """
        import nacl.signing
        
        # 从本地DID文档中获取公钥
        public_key_hex = self._did_manager.export_public_key()
        public_key_bytes = bytes.fromhex(public_key_hex)
        
        return nacl.signing.VerifyKey(public_key_bytes)
    
    def _store_nonce(self, nonce: str, exp_timestamp: int):
        """
        存储nonce（防重放）
        
        Args:
            nonce: 随机数
            exp_timestamp: 过期时间戳
        """
        nonce_file = self._auth_tokens_path / f"{nonce}.json"
        nonce_data = {
            "nonce": nonce,
            "exp": exp_timestamp,
            "created_at": datetime.now().isoformat()
        }
        nonce_file.write_text(
            json.dumps(nonce_data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
    
    def _check_and_consume_nonce(self, nonce: str) -> bool:
        """
        检查并消费nonce（防重放）
        
        Args:
            nonce: 随机数
            
        Returns:
            True if nonce有效且未使用，False if已使用或不存在
        """
        nonce_file = self._auth_tokens_path / f"{nonce}.json"
        
        if not nonce_file.exists():
            return False
        
        # 读取nonce数据
        nonce_data = json.loads(nonce_file.read_text(encoding='utf-8'))
        
        # 检查是否过期
        if datetime.now().timestamp() > nonce_data["exp"]:
            nonce_file.unlink()  # 删除过期nonce
            return False
        
        # 消费nonce（删除文件）
        nonce_file.unlink()
        
        return True
    
    def _cleanup_expired_nonces(self):
        """清理过期的nonce文件"""
        now = datetime.now().timestamp()
        
        for nonce_file in self._auth_tokens_path.glob("*.json"):
            try:
                nonce_data = json.loads(nonce_file.read_text(encoding='utf-8'))
                if now > nonce_data["exp"]:
                    nonce_file.unlink()
            except Exception:
                # 忽略损坏的文件
                pass
    
    def create_auth_token(
        self,
        primary_did: str,
        instance_id: str,
        action: str,
        expires_in: int = 3600,
        password: str = None
    ) -> str:
        """
        生成带签名的临时鉴权令牌
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            action: 操作类型 ("memory_write" | "memory_read" | "baseline_admin" | "instance_register" | "instance_revoke")
            expires_in: 有效期（秒），默认1小时
            password: 解密私钥的密码（如果未使用会话模式）
            
        Returns:
            JWT-like token: "{base64_header}.{base64_payload}.{base64_signature}"
            
        Raises:
            ValueError: 权限不足 / 密码错误 / 无效的action
        """
        # 检查action是否有效
        if action not in self.PERMISSION_MATRIX:
            raise ValueError(f"无效的操作类型: {action}")
        
        # 检查权限
        if not self.check_permission(primary_did, instance_id, action):
            raise ValueError(f"权限不足: DID={primary_did}, instance={instance_id}, action={action}")
        
        # 创建header和payload
        header = self._create_token_header()
        payload = self._create_token_payload(primary_did, instance_id, action, expires_in)
        
        # 序列化header和payload（保持一致的编码）
        header_json = json.dumps(header, separators=(',', ':')).encode('utf-8')
        payload_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        
        header_b64 = self._base64url_encode(header_json)
        payload_b64 = self._base64url_encode(payload_json)
        
        # 待签名数据
        signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        
        # 获取签名密钥
        signing_key = self._get_signing_key(password)
        
        # 签名
        signed = signing_key.sign(signing_input)
        signature = signed.signature
        signature_b64 = self._base64url_encode(signature)
        
        # 存储nonce（防重放）
        self._store_nonce(payload["nonce"], payload["exp"])
        
        # 清理过期nonce
        self._cleanup_expired_nonces()
        
        return f"{header_b64}.{payload_b64}.{signature_b64}"
    
    def verify_token(self, token: str) -> Dict:
        """
        验证鉴权令牌
        
        Args:
            token: JWT-like token字符串
            
        Returns:
            {
                "valid": True/False,
                "did": "...",
                "instance_id": "...",
                "action": "...",
                "reason": None  # 如果valid=False，说明原因
            }
        """
        try:
            # 分割token
            parts = token.split('.')
            if len(parts) != 3:
                return {
                    "valid": False,
                    "reason": "令牌格式错误：应该包含3个部分"
                }
            
            header_b64, payload_b64, signature_b64 = parts
            
            # 解码header和payload
            header_bytes = self._base64url_decode(header_b64)
            payload_bytes = self._base64url_decode(payload_b64)
            
            header = json.loads(header_bytes.decode('utf-8'))
            payload = json.loads(payload_bytes.decode('utf-8'))
            
            # 验证算法
            if header.get("alg") != "Ed25519":
                return {
                    "valid": False,
                    "reason": f"不支持的算法: {header.get('alg')}"
                }
            
            # 验证有效期
            now = int(datetime.now().timestamp())
            if now > payload["exp"]:
                return {
                    "valid": False,
                    "reason": "令牌已过期"
                }
            
            # 验证nonce（防重放）
            nonce = payload.get("nonce")
            if not self._check_and_consume_nonce(nonce):
                return {
                    "valid": False,
                    "reason": "令牌已被使用或不存在（防重放检查失败）"
                }
            
            # 验证签名
            import nacl.signing
            
            # 构造签名验证输入（必须与签名时完全一致）
            signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
            
            # 获取验证密钥
            verify_key = self._get_verify_key(payload.get("did"))
            
            # 验证签名
            try:
                signature_bytes = self._base64url_decode(signature_b64)
                verify_key.verify(signing_input, signature_bytes)
            except Exception as e:
                return {
                    "valid": False,
                    "reason": f"签名验证失败: {str(e)}"
                }
            
            # 验证通过
            return {
                "valid": True,
                "did": payload["did"],
                "instance_id": payload["instance_id"],
                "action": payload["action"],
                "reason": None
            }
            
        except Exception as e:
            return {
                "valid": False,
                "reason": f"令牌验证异常: {str(e)}"
            }
    
    def check_permission(self, primary_did: str, instance_id: str, action: str) -> bool:
        """
        基于权限矩阵检查操作权限
        
        权限矩阵:
        | 操作            | 主DID持有者 | 注册实例(本人) | 未注册实例 |
        |----------------|------------|--------------|-----------|
        | memory_write   | ✅          | ✅ (本人)     | ❌         |
        | memory_read    | ✅          | ✅           | ✅         |
        | baseline_admin | ✅          | ❌           | ❌         |
        | instance_register | ✅       | ❌           | ❌         |
        | instance_revoke | ✅         | ❌           | ❌         |
        
        Args:
            primary_did: 主DID
            instance_id: 实例ID
            action: 操作类型
            
        Returns:
            True if有权限, False if无权限
        """
        # 检查action是否有效
        if action not in self.PERMISSION_MATRIX:
            return False
        
        # 判断调用者身份
        # 1. 是否为主DID持有者（检查instance_id是否为空或特殊值）
        is_primary_did_holder = (instance_id == "primary") or (instance_id is None)
        
        if not is_primary_did_holder:
            # 2. 是否为注册实例
            try:
                instances = self._multi_instance_manager.list_instances(primary_did)
                registered_instances = [inst["instance_id"] for inst in instances if inst.get("status") == "active"]
                is_registered_instance = instance_id in registered_instances
            except Exception:
                is_registered_instance = False
            
            # 3. 是否为未注册实例
            is_unregistered_instance = not is_registered_instance
        else:
            is_registered_instance = False
            is_unregistered_instance = False
        
        # 查询权限矩阵
        permissions = self.PERMISSION_MATRIX[action]
        
        if is_primary_did_holder:
            return permissions["primary_did_holder"]
        elif is_registered_instance:
            return permissions["registered_instance"]
        else:
            return permissions["unregistered_instance"]
    
    def get_verify_key_from_did(self, did: str) -> Optional[Any]:
        """
        从DID文档中获取验证密钥
        
        Args:
            did: DID标识符
            
        Returns:
            nacl.signing.VerifyKey对象，如果失败返回None
        """
        try:
            import nacl.signing
            
            # 读取DID文档
            did_document_path = self.storage_path / "did_document.json"
            if not did_document_path.exists():
                return None
            
            did_document = json.loads(did_document_path.read_text(encoding='utf-8'))
            
            # 提取公钥
            public_key_hex = did_document["publicKey"][0]["publicKeyHex"]
            public_key_bytes = bytes.fromhex(public_key_hex)
            
            return nacl.signing.VerifyKey(public_key_bytes)
            
        except Exception:
            return None


def example_memguard_integration():
    """
    MemGuard调用示例（参考，不需要修改MemGuard）
    """
    print("=" * 60)
    print("MemGuard集成示例")
    print("=" * 60)
    
    # 初始化鉴权器
    auth = DIDAuthenticator()
    
    # 假设已经有一个主DID
    primary_did = "did:key:z7QEhf3KC..."
    instance_id = "nyx-windows"
    
    # 1. 生成写入令牌（需要密码）
    print("\n1. 生成写入令牌...")
    password = "test_password_123"
    token = auth.create_auth_token(
        primary_did=primary_did,
        instance_id=instance_id,
        action="memory_write",
        expires_in=300,  # 5分钟有效期
        password=password
    )
    print("OK: 令牌已生成:", token[:50], "...")
    
    # 2. MemGuard验证令牌
    print("\n2. 验证令牌...")
    result = auth.verify_token(token)
    print("OK: 验证结果: valid=" + str(result['valid']) + ", action=" + str(result.get('action')))
    
    print("\n" + "=" * 60)
    print("示例完成")
    print("=" * 60)


if __name__ == "__main__":
    example_memguard_integration()
