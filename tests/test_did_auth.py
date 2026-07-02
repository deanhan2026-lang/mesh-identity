"""
测试DID身份鉴权模块

验证DIDAuthenticator的所有核心功能。
"""

import pytest
import os
import json
import shutil
import base64
from pathlib import Path
from datetime import datetime, timedelta

import nacl.signing

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "did"))

from auth.did_auth import DIDAuthenticator
from did.multi_instance import MultiInstanceDIDManager


@pytest.fixture
def test_storage():
    """测试用的临时存储目录"""
    path = "Z:/qclaw/test_did_auth_fixture"
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)
    yield path
    if os.path.exists(path):
        shutil.rmtree(path)


@pytest.fixture
def primary_did_and_instances(test_storage):
    """生成主DID和注册实例"""
    multi_manager = MultiInstanceDIDManager(test_storage)
    result = multi_manager.generate_primary_did("test_password_123", force=True)
    primary_did = result["did"]
    multi_manager.register_instance(primary_did, "nyx-windows", "QClaw (Windows)")
    multi_manager.register_instance(primary_did, "nyx-mac", "QClaw (macOS)")
    return {
        "primary_did": primary_did,
        "password": "test_password_123",
        "multi_manager": multi_manager,
        "test_storage": test_storage,
    }


def test_token_generation_and_verification(primary_did_and_instances):
    """测试令牌生成和验证"""
    data = primary_did_and_instances
    auth = DIDAuthenticator(data["test_storage"])

    token = auth.create_auth_token(
        primary_did=data["primary_did"],
        instance_id="nyx-windows",
        action="memory_write",
        expires_in=3600,
        password=data["password"]
    )
    assert token is not None
    assert len(token.split('.')) == 3

    result = auth.verify_token(token)
    assert result["valid"] is True
    assert result["action"] == "memory_write"
    assert result["instance_id"] == "nyx-windows"


def test_expired_token_rejection(primary_did_and_instances):
    """测试过期令牌被拒绝"""
    data = primary_did_and_instances
    auth = DIDAuthenticator(data["test_storage"])

    # 手动构造一个过期的令牌
    header = {"alg": "Ed25519", "typ": "DID-Auth-Token", "version": "1.0"}
    payload = {
        "did": data["primary_did"],
        "instance_id": "nyx-windows",
        "action": "memory_write",
        "iat": int((datetime.now() - timedelta(hours=2)).timestamp()),
        "exp": int((datetime.now() - timedelta(hours=1)).timestamp()),
        "nonce": "expired_nonce_1234567890"
    }
    header_b64 = base64.urlsafe_b64encode(json.dumps(header, separators=(',', ':')).encode('utf-8')).rstrip(b'=').decode('utf-8')
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode('utf-8')).rstrip(b'=').decode('utf-8')

    did_data = data["multi_manager"]._did_manager.load_did(data["password"])
    private_key_bytes = did_data["private_key"]
    signing_key = nacl.signing.SigningKey(private_key_bytes)
    signing_input = header_b64 + "." + payload_b64
    signed = signing_key.sign(signing_input.encode('utf-8'))
    signature_b64 = base64.urlsafe_b64encode(signed.signature).rstrip(b'=').decode('utf-8')
    expired_token = header_b64 + "." + payload_b64 + "." + signature_b64

    result = auth.verify_token(expired_token)
    assert result["valid"] is False
    assert "过期" in result["reason"]


def test_forged_token_rejection(primary_did_and_instances):
    """测试伪造令牌被拒绝"""
    data = primary_did_and_instances
    auth = DIDAuthenticator(data["test_storage"])

    token = auth.create_auth_token(
        primary_did=data["primary_did"],
        instance_id="nyx-windows",
        action="memory_write",
        expires_in=3600,
        password=data["password"]
    )
    fake_token = token[:-4] + "XXXX"
    result = auth.verify_token(fake_token)
    assert result["valid"] is False


def test_permission_matrix(primary_did_and_instances):
    """测试权限矩阵"""
    data = primary_did_and_instances
    auth = DIDAuthenticator(data["test_storage"])
    pd = data["primary_did"]

    # memory_write - 注册实例有权限
    assert auth.check_permission(pd, "nyx-windows", "memory_write") is True
    # baseline_admin - 注册实例无权限
    assert auth.check_permission(pd, "nyx-windows", "baseline_admin") is False
    # memory_write - 未注册实例无权限
    assert auth.check_permission(pd, "unregistered_instance", "memory_write") is False
    # memory_read - 所有人都有权限
    assert auth.check_permission(pd, "nyx-windows", "memory_read") is True
    assert auth.check_permission(pd, "unregistered_instance", "memory_read") is True
    # instance_register - 注册实例无权限
    assert auth.check_permission(pd, "nyx-windows", "instance_register") is False


def test_multi_instance_permission_isolation(primary_did_and_instances):
    """测试多实例权限隔离"""
    data = primary_did_and_instances
    auth = DIDAuthenticator(data["test_storage"])
    pd = data["primary_did"]

    assert auth.check_permission(pd, "nyx-mac", "memory_write") is True
    assert auth.check_permission(pd, "kronos-heng", "memory_write") is False


def test_anti_replay(primary_did_and_instances):
    """测试防重放攻击"""
    data = primary_did_and_instances
    auth = DIDAuthenticator(data["test_storage"])

    token = auth.create_auth_token(
        primary_did=data["primary_did"],
        instance_id="nyx-windows",
        action="memory_read",
        expires_in=3600,
        password=data["password"]
    )
    result1 = auth.verify_token(token)
    assert result1["valid"] is True

    result2 = auth.verify_token(token)
    assert result2["valid"] is False


def test_session_mode_with_private_key_object(primary_did_and_instances):
    """测试会话模式（传入私钥对象）"""
    data = primary_did_and_instances

    did_data = data["multi_manager"]._did_manager.load_did(data["password"])
    private_key_bytes = did_data["private_key"]
    signing_key = nacl.signing.SigningKey(private_key_bytes)

    # 会话模式：传入解密后的私钥对象，不需要密码
    auth = DIDAuthenticator(data["test_storage"], private_key_obj=signing_key)

    token = auth.create_auth_token(
        primary_did=data["primary_did"],
        instance_id="nyx-windows",
        action="memory_write",
        expires_in=3600
        # 不传password
    )
    assert token is not None
    assert len(token.split('.')) == 3

    result = auth.verify_token(token)
    assert result["valid"] is True


def test_instance_register_revoke_permission(primary_did_and_instances):
    """测试 instance_register 和 instance_revoke 权限"""
    data = primary_did_and_instances
    auth = DIDAuthenticator(data["test_storage"])
    pd = data["primary_did"]

    assert auth.check_permission(pd, "nyx-windows", "instance_register") is False
    assert auth.check_permission(pd, "nyx-windows", "instance_revoke") is False
