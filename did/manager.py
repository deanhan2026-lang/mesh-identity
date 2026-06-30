"""
DID Manager - 去中心化身份管理模块

实现W3C DID规范的核心功能：
1. 基于Ed25519密钥对的DID生成
2. soul_anchor计算（SOUL.md哈希值）
3. 身份凭证存储与验证

参考: AIAP协议Phase1验证结果
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple

try:
    import nacl.signing
    import nacl.encoding
    from nacl.public import PrivateKey, PublicKey
    _HAS_NACL = True
except ImportError:
    _HAS_NACL = False

from ..storage.nas_storage import NASStorage


class DIDManager:
    """DID身份管理器"""
    
    def __init__(self, storage_path: str = "Z:/qclaw/did"):
        """
        初始化DID管理器
        
        Args:
            storage_path: DID凭证存储路径（NAS共享目录）
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._private_key_path = self.storage_path / "private_key.hex"
        self._did_document_path = self.storage_path / "did_document.json"
        
    def generate_did(self, force: bool = False) -> Dict:
        """
        生成新的DID身份
        
        Args:
            force: 是否强制重新生成（会覆盖现有身份）
            
        Returns:
            DID文档字典，包含did、公钥、私钥路径等
        """
        if not _HAS_NACL:
            raise RuntimeError("需要PyNaCl库。请安装: pip install pynacl")
        
        # 检查是否已存在身份
        if self._did_document_path.exists() and not force:
            raise FileExistsError(
                f"DID已存在: {self._did_document_path}. "
                "使用force=True强制重新生成（会丢失现有身份）"
            )
        
        # 生成Ed25519密钥对
        private_key = PrivateKey.generate()
        public_key = private_key.public_key
        
        # 构造DID（did:key方法）
        # 格式: did:key:z{Base58编码的公钥}
        public_key_bytes = bytes(public_key)
        # 简化版：使用hex编码（生产环境应使用Multibase）
        did = f"did:key:z{public_key_bytes.hex()}"
        
        # 保存私钥（hex格式）
        private_key_hex = private_key.encode().hex()
        self._private_key_path.write_text(private_key_hex)
        
        # 构造DID文档
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
            "private_key_path": str(self._private_key_path),
            "warning": "私钥已保存到本地，请妥善保管！丢失后无法恢复身份。"
        }
    
    def load_did(self) -> Optional[Dict]:
        """
        加载现有DID身份
        
        Returns:
            DID文档字典，如果不存在返回None
        """
        if not self._did_document_path.exists():
            return None
        
        did_document = json.loads(self._did_document_path.read_text())
        return {
            "did": did_document["id"],
            "did_document": did_document,
            "private_key_path": str(self._private_key_path)
        }
    
    def compute_soul_anchor(self, soul_file_path: str = None) -> str:
        """
        计算soul_anchor（SOUL.md的SHA-256哈希值）
        
        Args:
            soul_file_path: SOUL.md文件路径，默认使用NAS上的路径
            
        Returns:
            soul_anchor哈希值（hex字符串）
        """
        if soul_file_path is None:
            # 默认路径：NAS共享目录
            soul_file_path = "Z:/qclaw/SOUL.md"
        
        soul_path = Path(soul_file_path)
        if not soul_path.exists():
            raise FileNotFoundError(f"SOUL.md不存在: {soul_file_path}")
        
        # 计算SHA-256哈希
        content = soul_path.read_bytes()
        soul_anchor = hashlib.sha256(content).hexdigest()
        
        # 保存soul_anchor到DID目录
        anchor_path = self.storage_path / "soul_anchor.txt"
        anchor_path.write_text(soul_anchor)
        
        return soul_anchor
    
    def verify_identity(self, did: str, soul_file_path: str = None) -> Tuple[bool, str]:
        """
        验证身份一致性
        
        Args:
            did: 要验证的DID
            soul_file_path: SOUL.md文件路径
            
        Returns:
            (是否一致, 详细信息)
        """
        # 加载本地DID
        local_did_data = self.load_did()
        if local_did_data is None:
            return False, "本地DID不存在"
        
        local_did = local_did_data["did"]
        
        # 验证DID匹配
        if local_did != did:
            return False, f"DID不匹配: 本地={local_did}, 验证={did}"
        
        # 验证soul_anchor
        try:
            current_anchor = self.compute_soul_anchor(soul_file_path)
            anchor_path = self.storage_path / "soul_anchor.txt"
            saved_anchor = anchor_path.read_text().strip()
            
            if current_anchor != saved_anchor:
                return False, "soul_anchor已变化，SOUL.md可能被修改"
            
            return True, "身份验证通过"
        except FileNotFoundError as e:
            return False, str(e)
    
    def sign_message(self, message: str) -> Tuple[str, str]:
        """
        使用私钥签名消息
        
        Args:
            message: 要签名的消息
            
        Returns:
            (签名hex, 公钥hex)
        """
        if not _HAS_NACL:
            raise RuntimeError("需要PyNaCl库")
        
        if not self._private_key_path.exists():
            raise FileNotFoundError("私钥不存在，请先生成DID")
        
        # 加载私钥
        private_key_hex = self._private_key_path.read_text().strip()
        private_key_bytes = bytes.fromhex(private_key_hex)
        signing_key = nacl.signing.SigningKey(private_key_bytes)
        
        # 签名
        message_bytes = message.encode('utf-8')
        signed = signing_key.sign(message_bytes)
        signature = signed.signature  # 64字节签名
        
        # 公钥
        public_key_hex = bytes(signing_key.verify_key).hex()
        
        return signature.hex(), public_key_hex
    
    def verify_signature(self, message: str, signature_hex: str, public_key_hex: str) -> bool:
        """
        验证签名
        
        Args:
            message: 原始消息
            signature_hex: 签名（hex）
            public_key_hex: 公钥（hex）
            
        Returns:
            签名是否有效
        """
        if not _HAS_NACL:
            raise RuntimeError("需要PyNaCl库")
        
        try:
            # 构造验证密钥
            public_key_bytes = bytes.fromhex(public_key_hex)
            verify_key = nacl.signing.VerifyKey(public_key_bytes)
            
            # 验证签名
            message_bytes = message.encode('utf-8')
            signature_bytes = bytes.fromhex(signature_hex)
            verify_key.verify(message_bytes, signature_bytes)
            return True
        except Exception:
            return False


def main():
    """命令行测试"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DID身份管理")
    parser.add_argument("action", choices=["generate", "load", "anchor", "verify"],
                        help="操作类型")
    parser.add_argument("--storage", default="Z:/qclaw/did",
                        help="DID存储路径")
    parser.add_argument("--force", action="store_true",
                        help="强制重新生成DID")
    
    args = parser.parse_args()
    
    manager = DIDManager(args.storage)
    
    if args.action == "generate":
        result = manager.generate_did(force=args.force)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.action == "load":
        result = manager.load_did()
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("DID不存在")
    elif args.action == "anchor":
        anchor = manager.compute_soul_anchor()
        print(f"soul_anchor: {anchor}")
    elif args.action == "verify":
        did_data = manager.load_did()
        if did_data:
            valid, msg = manager.verify_identity(did_data["did"])
            print(f"验证结果: {valid}, {msg}")
        else:
            print("DID不存在，无法验证")


if __name__ == "__main__":
    main()
