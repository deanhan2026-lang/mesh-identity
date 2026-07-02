"""
DID Manager - 去中心化身份管理模块 (加密存储版)

实现W3C DID规范的核心功能：
1. 基于Ed25519密钥对的DID生成
2. 私钥密码加密存储 (Fernet + PBKDF2)
3. soul_anchor计算（SOUL.md哈希值）
4. 身份凭证存储与验证

安全设计：
- 私钥使用用户密码派生密钥加密
- 密钥派生: PBKDF2HMAC(SHA256) + 随机盐值
- 加密算法: AES-256 (Fernet)
- 存储格式: JSON {encrypted_key, salt, iterations}
"""

import os
import json
import hashlib
import base64
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple

try:
    import nacl.signing
    import nacl.encoding
    _HAS_NACL = True
except ImportError:
    _HAS_NACL = False

# 加密依赖
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

from ..storage.nas_storage import NASStorage


class DIDManager:
    """DID身份管理器（私钥密码加密存储）"""
    
    # 默认PBKDF2参数
    PBKDF2_ITERATIONS = 100000
    ENCRYPTED_VERSION = "1.0"
    
    def __init__(self, storage_path: str = "Z:/qclaw/did"):
        """
        初始化DID管理器
        
        Args:
            storage_path: DID凭证存储路径（NAS共享目录）
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._encrypted_key_path = self.storage_path / "private_key.enc"
        self._old_key_path = self.storage_path / "private_key.hex"
        self._did_document_path = self.storage_path / "did_document.json"
        
    @staticmethod
    def _derive_key(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
        """
        使用PBKDF2从密码派生加密密钥
        
        Args:
            password: 用户密码
            salt: 随机盐值（16字节）
            iterations: 迭代次数
            
        Returns:
            派生密钥（32字节，适合Fernet）
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8')))
    
    @staticmethod
    def _encrypt_data(data: bytes, password: str, salt: bytes = None, iterations: int = PBKDF2_ITERATIONS) -> Dict:
        """
        加密数据
        
        Args:
            data: 要加密的原始数据
            password: 用户密码
            salt: 随机盐值（自动生成）
            iterations: PBKDF2迭代次数
            
        Returns:
            加密结果字典: {encrypted_key, salt, iterations}
        """
        if salt is None:
            salt = os.urandom(16)
        
        key = DIDManager._derive_key(password, salt, iterations)
        fernet = Fernet(key)
        encrypted = fernet.encrypt(data)
        
        return {
            "encrypted_key": base64.b64encode(encrypted).decode('utf-8'),
            "salt": salt.hex(),
            "iterations": iterations,
            "version": DIDManager.ENCRYPTED_VERSION
        }
    
    @staticmethod
    def _decrypt_data(encrypted_payload: Dict, password: str) -> bytes:
        """
        解密数据
        
        Args:
            encrypted_payload: 加密数据字典
            password: 用户密码
            
        Returns:
            解密后的原始数据
            
        Raises:
            ValueError: 密码错误
        """
        salt = bytes.fromhex(encrypted_payload['salt'])
        iterations = encrypted_payload.get('iterations', DIDManager.PBKDF2_ITERATIONS)
        encrypted = base64.b64decode(encrypted_payload['encrypted_key'])
        
        key = DIDManager._derive_key(password, salt, iterations)
        fernet = Fernet(key)
        
        try:
            return fernet.decrypt(encrypted)
        except Exception:
            raise ValueError("密码错误，无法解密私钥")
    
    def generate_did(self, password: str, force: bool = False) -> Dict:
        """
        生成新的DID身份（私钥加密存储）
        
        Args:
            password: 用于加密私钥的密码
            force: 是否强制重新生成（会覆盖现有身份）
            
        Returns:
            DID文档字典
        """
        if not _HAS_NACL:
            raise RuntimeError("需要PyNaCl库。请安装: pip install pynacl")
        if not _HAS_CRYPTO:
            raise RuntimeError("需要cryptography库。请安装: pip install cryptography>=41.0.0")
        
        # 检查是否已存在身份
        if self._encrypted_key_path.exists() and not force:
            raise FileExistsError(
                f"DID已存在: {self._did_document_path}. "
                "使用force=True强制重新生成（会丢失现有身份）"
            )
        
        # 生成Ed25519密钥对
        signing_key = nacl.signing.SigningKey.generate()
        verify_key = signing_key.verify_key
        public_key_bytes = bytes(verify_key)
        private_key_bytes = bytes(signing_key)
        
        # 构造DID
        did = f"did:key:z{public_key_bytes.hex()}"
        
        # === 加密存储私钥 ===
        encrypted_payload = self._encrypt_data(private_key_bytes, password)
        
        # 保存加密私钥
        self._encrypted_key_path.write_text(
            json.dumps(encrypted_payload, indent=2, ensure_ascii=False)
        )
        
        # === 如果存在旧版明文私钥，删除 ===
        if self._old_key_path.exists():
            self._old_key_path.unlink()
        
        # 构造DID文档（仅含公钥，不需密码）
        did_document = {
            "@context": "https://w3id.org/did/v1",
            "id": did,
            "created": datetime.utcnow().isoformat() + "Z",
            "publicKey": [{
                "id": f"{did}#signing-key",
                "type": "Ed25519VerificationKey2018",
                "controller": did,
                "publicKeyHex": public_key_bytes.hex()
            }],
            "authentication": [f"{did}#signing-key"]
        }
        
        # 保存DID文档
        self._did_document_path.write_text(
            json.dumps(did_document, indent=2, ensure_ascii=False)
        )
        
        return {
            "did": did,
            "did_document": did_document,
            "encrypted_key_path": str(self._encrypted_key_path),
            "message": "✅ DID已生成，私钥已加密存储。请牢记您的密码！"
        }
    
    def load_did(self, password: str = None) -> Optional[Dict]:
        """
        加载现有DID身份
        
        Args:
            password: 用户密码（解密私钥）
            
        Returns:
            DID信息字典，如果不存在返回None
        """
        if not self._did_document_path.exists():
            return None
        
        did_document = json.loads(self._did_document_path.read_text())
        result = {
            "did": did_document["id"],
            "did_document": did_document,
            "encrypted_key_path": str(self._encrypted_key_path),
            "private_key_loaded": False
        }
        
        # 如果提供了密码，尝试解密私钥
        if password is not None:
            if self._encrypted_key_path.exists():
                try:
                    encrypted_payload = json.loads(self._encrypted_key_path.read_text())
                    private_key_bytes = self._decrypt_data(encrypted_payload, password)
                    result["private_key_loaded"] = True
                    result["private_key"] = private_key_bytes
                except ValueError:
                    raise ValueError("密码错误，无法解密私钥")
            elif self._old_key_path.exists():
                # 兼容旧版：迁移明文私钥
                result["private_key_loaded"] = True
                result["private_key"] = bytes.fromhex(self._old_key_path.read_text().strip())
                result["migration_needed"] = True
        
        return result
    
    def export_public_key(self) -> str:
        """
        导出公钥（不需要密码）
        
        Returns:
            公钥hex字符串
        """
        if not self._did_document_path.exists():
            raise FileNotFoundError("DID不存在，请先生成")
        
        did_document = json.loads(self._did_document_path.read_text())
        pub_key_hex = did_document["publicKey"][0]["publicKeyHex"]
        return pub_key_hex
    
    def change_password(self, old_password: str, new_password: str) -> Dict:
        """
        修改加密密码
        
        Args:
            old_password: 当前密码
            new_password: 新密码
            
        Returns:
            操作结果
        """
        if not self._encrypted_key_path.exists():
            raise FileNotFoundError("加密私钥不存在，请先生成DID（带密码）")
        
        # 用旧密码解密
        encrypted_payload = json.loads(self._encrypted_key_path.read_text())
        private_key_bytes = self._decrypt_data(encrypted_payload, old_password)
        
        # 用新密码重新加密
        new_encrypted_payload = self._encrypt_data(private_key_bytes, new_password)
        
        # 保存
        self._encrypted_key_path.write_text(
            json.dumps(new_encrypted_payload, indent=2, ensure_ascii=False)
        )
        
        return {
            "message": "✅ 密码已修改",
            "encrypted_key_path": str(self._encrypted_key_path)
        }
    
    def migrate_from_plaintext(self, password: str) -> Dict:
        """
        从旧版明文私钥迁移到加密存储
        
        Args:
            password: 用于加密的密码
            
        Returns:
            迁移结果
        """
        if not self._old_key_path.exists():
            raise FileNotFoundError("旧版私钥不存在，无需迁移")
        
        private_key_hex = self._old_key_path.read_text().strip()
        private_key_bytes = bytes.fromhex(private_key_hex)
        
        # 加密存储
        encrypted_payload = self._encrypt_data(private_key_bytes, password)
        self._encrypted_key_path.write_text(
            json.dumps(encrypted_payload, indent=2, ensure_ascii=False)
        )
        
        # 删除旧版明文
        self._old_key_path.unlink()
        
        return {
            "message": "✅ 私钥已从明文迁移到加密存储",
            "encrypted_key_path": str(self._encrypted_key_path)
        }
    
    def compute_soul_anchor(self, soul_file_path: str = None) -> str:
        """计算soul_anchor（SOUL.md的SHA-256哈希值）"""
        if soul_file_path is None:
            soul_file_path = "Z:/qclaw/SOUL.md"
        
        soul_path = Path(soul_file_path)
        if not soul_path.exists():
            raise FileNotFoundError(f"SOUL.md不存在: {soul_file_path}")
        
        content = soul_path.read_bytes()
        soul_anchor = hashlib.sha256(content).hexdigest()
        
        anchor_path = self.storage_path / "soul_anchor.txt"
        anchor_path.write_text(soul_anchor)
        
        return soul_anchor
    
    def verify_identity(self, did: str, soul_file_path: str = None) -> Tuple[bool, str]:
        """验证身份一致性"""
        if not self._did_document_path.exists():
            return False, "本地DID不存在"
        
        did_document = json.loads(self._did_document_path.read_text())
        local_did = did_document["id"]
        
        if local_did != did:
            return False, f"DID不匹配: 本地={local_did}, 验证={did}"
        
        try:
            current_anchor = self.compute_soul_anchor(soul_file_path)
            anchor_path = self.storage_path / "soul_anchor.txt"
            saved_anchor = anchor_path.read_text().strip()
            
            if current_anchor != saved_anchor:
                return False, "soul_anchor已变化，SOUL.md可能被修改"
            
            return True, "身份验证通过"
        except FileNotFoundError as e:
            return False, str(e)
    
    def sign_message(self, message: str, password: str) -> Tuple[str, str]:
        """
        使用私钥签名消息（需密码解密）
        
        Args:
            message: 要签名的消息
            password: 用户密码
            
        Returns:
            (签名hex, 公钥hex)
        """
        if not _HAS_NACL:
            raise RuntimeError("需要PyNaCl库")
        
        # 加载DID并解密私钥
        did_data = self.load_did(password)
        if did_data is None:
            raise FileNotFoundError("DID不存在，请先生成")
        if not did_data.get("private_key_loaded"):
            raise ValueError("密码错误或私钥不可用")
        
        private_key_bytes = did_data["private_key"]
        signing_key = nacl.signing.SigningKey(private_key_bytes)
        
        # 签名
        message_bytes = message.encode('utf-8')
        signed = signing_key.sign(message_bytes)
        signature = signed.signature
        public_key_hex = bytes(signing_key.verify_key).hex()
        
        return signature.hex(), public_key_hex
    
    def verify_signature(self, message: str, signature_hex: str, public_key_hex: str) -> bool:
        """验证签名（不需要密码）"""
        if not _HAS_NACL:
            raise RuntimeError("需要PyNaCl库")
        
        try:
            public_key_bytes = bytes.fromhex(public_key_hex)
            verify_key = nacl.signing.VerifyKey(public_key_bytes)
            message_bytes = message.encode('utf-8')
            signature_bytes = bytes.fromhex(signature_hex)
            verify_key.verify(message_bytes, signature_bytes)
            return True
        except Exception:
            return False


def main():
    """命令行测试"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DID身份管理 (加密存储)")
    parser.add_argument("action", choices=["generate", "load", "anchor", "verify", "change-password", "migrate"],
                        help="操作类型")
    parser.add_argument("--storage", default="Z:/qclaw/did",
                        help="DID存储路径")
    parser.add_argument("--password", default=None,
                        help="私钥加密密码")
    parser.add_argument("--new-password", default=None,
                        help="新密码（change-password时使用）")
    parser.add_argument("--force", action="store_true",
                        help="强制重新生成DID")
    parser.add_argument("--export-pubkey", action="store_true",
                        help="导出公钥")
    
    args = parser.parse_args()
    
    manager = DIDManager(args.storage)
    
    if args.action == "generate":
        if not args.password:
            print("❌ 错误: 生成DID需要 --password 参数")
            return
        result = manager.generate_did(password=args.password, force=args.force)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    elif args.action == "load":
        try:
            result = manager.load_did(password=args.password)
            if result:
                print(f"DID: {result['did']}")
                print(f"私钥已加密: {result['encrypted_key_path']}")
                print(f"私钥已解密: {result.get('private_key_loaded', False)}")
                if args.export_pubkey:
                    pubkey = manager.export_public_key()
                    print(f"公钥: {pubkey}")
            else:
                print("❌ DID不存在")
        except ValueError as e:
            print(f"❌ {e}")
            
    elif args.action == "anchor":
        anchor = manager.compute_soul_anchor()
        print(f"soul_anchor: {anchor}")
        
    elif args.action == "verify":
        if not args.password:
            print("❌ 验证需要 --password 参数")
            return
        try:
            did_data = manager.load_did(password=args.password)
            if did_data:
                valid, msg = manager.verify_identity(did_data["did"])
                print(f"验证结果: {'✅ 通过' if valid else '❌ 失败'}, {msg}")
            else:
                print("❌ DID不存在")
        except ValueError as e:
            print(f"❌ {e}")
            
    elif args.action == "change-password":
        if not args.password or not args.new_password:
            print("❌ 改密需要 --password 和 --new-password 参数")
            return
        try:
            result = manager.change_password(args.password, args.new_password)
            print(result['message'])
        except ValueError as e:
            print(f"❌ {e}")
            
    elif args.action == "migrate":
        if not args.password:
            print("❌ 迁移需要 --password 参数")
            return
        try:
            result = manager.migrate_from_plaintext(args.password)
            print(result['message'])
        except FileNotFoundError as e:
            print(f"❌ {e}")


if __name__ == "__main__":
    main()
