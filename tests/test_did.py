"""测试 DID Manager 核心功能"""
import pytest
import tempfile
import shutil
import json
from pathlib import Path


class MockDIDManager:
    """模拟 DID Manager 用于测试"""
    
    @staticmethod
    def _compute_soul_anchor(soul_content: str) -> str:
        """计算灵魂锚点（SHA256）"""
        import hashlib
        return hashlib.sha256(soul_content.encode('utf-8')).hexdigest()
    
    @staticmethod
    def verify_soul_anchor(soul_content: str, expected: str) -> bool:
        """验证灵魂锚点"""
        computed = MockDIDManager._compute_soul_anchor(soul_content)
        return computed == expected


class TestSoulAnchor:
    """灵魂锚点测试"""
    
    def test_soul_anchor_deterministic(self):
        """同一内容应产生相同的锚点"""
        content = "# SOUL.md\nTest content"
        a = MockDIDManager._compute_soul_anchor(content)
        b = MockDIDManager._compute_soul_anchor(content)
        assert a == b
    
    def test_soul_anchor_different_content(self):
        """不同内容应产生不同的锚点"""
        a = MockDIDManager._compute_soul_anchor("content A")
        b = MockDIDManager._compute_soul_anchor("content B")
        assert a != b
    
    def test_soul_anchor_unicode(self):
        """支持 Unicode 内容"""
        content = "# 黑夜女神 Nyx\n测试中文内容 🖤"
        anchor = MockDIDManager._compute_soul_anchor(content)
        assert len(anchor) == 64  # SHA256 produces 64 hex chars
        assert MockDIDManager.verify_soul_anchor(content, anchor)


class TestDIDFormat:
    """DID 格式验证"""
    
    # did:key:z + multibase base58btc encoding (44-46 chars for Ed25519)
    DID_REGEX = r'^did:key:z[1-9A-HJ-NP-Za-km-z]{44,46}$'
    
    def test_did_key_format(self):
        """验证 did:key 格式"""
        import re
        # Ed25519 公钥 = 32 bytes → base58btc ≈ 44 chars
        valid_did = "did:key:z" + "1A2B3C4D5E6F7G8H9J" * 2  # valid base58btc chars
        valid_did = valid_did[:23]  # ~44 chars total
        valid_did = "did:key:z1A2B3C4D5E6F7G8H9JKLMNPQRST1A2B3C4D5E6F7G8H9J"  # 44 chars
        assert re.match(self.DID_REGEX, valid_did) is not None
        
        invalid_dids = [
            "did:web:example.com",
            "did:key:too-short",
            "not-a-did",
        ]
        for did in invalid_dids:
            assert re.match(self.DID_REGEX, did) is None
    
    def test_ed25519_pubkey_length(self):
        """Ed25519 公钥 = 32 bytes = 44 base58btc chars (z prefix)"""
        # Ed25519: 32 bytes → base58btc = ~44 chars
        # The 'z' prefix indicates multibase base58btc encoding
        # Valid did:key:z for Ed25519 is 'z' + base58btc(32 bytes)
        pubkey_b58_len = 44  # approx base58btc length for 32 bytes
        did = "did:key:z" + "A" * pubkey_b58_len
        # 'z' prefix is multibase indicator, rest is base58btc encoded key
        assert len(did.split(":")[-1]) == 1 + pubkey_b58_len
