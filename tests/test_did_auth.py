"""
测试DID身份鉴权模块

验证DIDAuthenticator的所有核心功能。
"""

import sys
import os
import json
import shutil
import base64
from pathlib import Path
from datetime import datetime, timedelta

# 设置标准输出编码为UTF-8
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入鉴权模块
from auth.did_auth import DIDAuthenticator

# 导入多实例DID管理器（用于生成测试数据）
sys.path.insert(0, str(project_root / "did"))
manager_py = project_root / "did" / "manager.py"
with open(manager_py, 'r', encoding='utf-8') as f:
    code = f.read()
code = code.replace(
    "from ..storage.nas_storage import NASStorage",
    "# from ..storage.nas_storage import NASStorage  # 测试时禁用相对导入"
)
temp_manager_py = project_root / "did" / "manager_temp.py"
with open(temp_manager_py, 'w', encoding='utf-8') as f:
    f.write(code)
from did.multi_instance import MultiInstanceDIDManager
if temp_manager_py.exists():
    temp_manager_py.unlink()


def test_did_authenticator():
    """测试DID身份鉴权功能"""
    
    # 使用临时目录进行测试
    test_storage = "Z:/qclaw/test_did_auth"
    if os.path.exists(test_storage):
        shutil.rmtree(test_storage)
    os.makedirs(test_storage, exist_ok=True)
    
    try:
        print("=" * 60)
        print("DID身份鉴权模块测试")
        print("=" * 60)
        
        # 1. 生成主DID和注册实例
        print("\n1. 生成主DID和注册实例...")
        multi_manager = MultiInstanceDIDManager(test_storage)
        result = multi_manager.generate_primary_did("test_password_123", force=True)
        primary_did = result["did"]
        print("OK: 主DID生成成功:", primary_did[:50], "...")
        
        # 注册实例
        multi_manager.register_instance(primary_did, "nyx-windows", "QClaw (Windows)")
        multi_manager.register_instance(primary_did, "nyx-mac", "QClaw (macOS)")
        print("OK: 实例注册成功: nyx-windows, nyx-mac")
        
        # 2. 初始化鉴权器
        print("\n2. 初始化鉴权器...")
        auth = DIDAuthenticator(test_storage)
        print("OK: 鉴权器初始化成功")
        
        # 3. 生成令牌
        print("\n3. 测试生成令牌...")
        password = "test_password_123"
        token = auth.create_auth_token(
            primary_did=primary_did,
            instance_id="nyx-windows",
            action="memory_write",
            expires_in=3600,
            password=password
        )
        assert token is not None, "令牌生成失败"
        assert len(token.split('.')) == 3, "令牌格式错误"
        print("OK: 令牌生成成功:", token[:50], "...")
        
        # 4. 验证令牌
        print("\n4. 测试验证令牌...")
        result = auth.verify_token(token)
        assert result["valid"] == True, "令牌验证失败: " + str(result.get('reason'))
        assert result["action"] == "memory_write", "令牌action不匹配"
        assert result["instance_id"] == "nyx-windows", "令牌instance_id不匹配"
        print("OK: 令牌验证成功: valid=" + str(result['valid']) + ", action=" + str(result['action']))
        
        # 5. 测试过期令牌
        print("\n5. 测试过期令牌...")
        import nacl.signing
        
        # 手动构造一个过期的令牌
        header = {"alg": "Ed25519", "typ": "DID-Auth-Token", "version": "1.0"}
        payload = {
            "did": primary_did,
            "instance_id": "nyx-windows",
            "action": "memory_write",
            "iat": int((datetime.now() - timedelta(hours=2)).timestamp()),
            "exp": int((datetime.now() - timedelta(hours=1)).timestamp()),
            "nonce": "expired_nonce_1234567890"
        }
        
        # 序列化并签名
        header_b64 = base64.urlsafe_b64encode(json.dumps(header, separators=(',', ':')).encode('utf-8')).rstrip(b'=').decode('utf-8')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode('utf-8')).rstrip(b'=').decode('utf-8')
        
        # 获取签名密钥
        did_data = multi_manager._did_manager.load_did(password)
        private_key_bytes = did_data["private_key"]
        signing_key = nacl.signing.SigningKey(private_key_bytes)
        
        # 签名
        signing_input = header_b64 + "." + payload_b64
        signed = signing_key.sign(signing_input.encode('utf-8'))
        signature_b64 = base64.urlsafe_b64encode(signed.signature).rstrip(b'=').decode('utf-8')
        
        expired_token = header_b64 + "." + payload_b64 + "." + signature_b64
        
        # 验证过期令牌
        result = auth.verify_token(expired_token)
        assert result["valid"] == False, "过期令牌应该验证失败"
        assert "过期" in result["reason"], "错误信息应该包含'过期': " + str(result['reason'])
        print("OK: 过期令牌被正确拒绝:", result['reason'])
        
        # 6. 测试伪造令牌
        print("\n6. 测试伪造令牌...")
        fake_token = token[:-4] + "XXXX"
        result = auth.verify_token(fake_token)
        assert result["valid"] == False, "伪造令牌应该验证失败"
        print("OK: 伪造令牌被正确拒绝:", result['reason'])
        
        # 7. 测试权限矩阵
        print("\n7. 测试权限矩阵...")
        
        # memory_write - 注册实例有权限
        assert auth.check_permission(primary_did, "nyx-windows", "memory_write") == True, \
            "注册实例应该有memory_write权限"
        print("OK: nyx-windows有memory_write权限")
        
        # baseline_admin - 实例无权限
        assert auth.check_permission(primary_did, "nyx-windows", "baseline_admin") == False, \
            "注册实例不应该有baseline_admin权限"
        print("OK: nyx-windows无baseline_admin权限")
        
        # memory_write - 未注册实例无权限
        assert auth.check_permission(primary_did, "unregistered_instance", "memory_write") == False, \
            "未注册实例不应该有memory_write权限"
        print("OK: 未注册实例无memory_write权限")
        
        # memory_read - 所有人都有权限
        assert auth.check_permission(primary_did, "nyx-windows", "memory_read") == True, \
            "注册实例应该有memory_read权限"
        assert auth.check_permission(primary_did, "unregistered_instance", "memory_read") == True, \
            "未注册实例应该有memory_read权限"
        print("OK: memory_read权限正确（所有人都有）")
        
        # 8. 测试多实例权限隔离
        print("\n8. 测试多实例权限隔离...")
        
        # 注册实例有权限
        assert auth.check_permission(primary_did, "nyx-mac", "memory_write") == True, \
            "nyx-mac应该有memory_write权限"
        print("OK: nyx-mac有memory_write权限（注册实例）")
        
        # 未注册实例没有权限
        assert auth.check_permission(primary_did, "kronos-heng", "memory_write") == False, \
            "未注册实例kronos-heng不应该有memory_write权限"
        print("OK: 未注册实例kronos-heng无memory_write权限")
        
        # 9. 测试防重放攻击
        print("\n9. 测试防重放攻击...")
        
        # 第一次验证应该成功
        token2 = auth.create_auth_token(
            primary_did=primary_did,
            instance_id="nyx-windows",
            action="memory_read",
            expires_in=3600,
            password=password
        )
        result1 = auth.verify_token(token2)
        assert result1["valid"] == True, "第一次验证应该成功"
        print("OK: 第一次验证成功")
        
        # 第二次验证应该失败（nonce已被消费）
        result2 = auth.verify_token(token2)
        assert result2["valid"] == False, "第二次验证应该失败（防重放）"
        assert "已被使用" in result2["reason"] or "防重放" in result2["reason"], \
            "错误信息应该包含防重放提示: " + str(result2['reason'])
        print("OK: 第二次验证被拒绝:", result2['reason'])
        
        # 10. 测试不同操作类型
        print("\n10. 测试不同操作类型...")
        
        for action in ["memory_write", "memory_read", "baseline_admin", "instance_register", "instance_revoke"]:
            try:
                token_action = auth.create_auth_token(
                    primary_did=primary_did,
                    instance_id="nyx-windows",
                    action=action,
                    expires_in=3600,
                    password=password
                )
                result_action = auth.verify_token(token_action)
                print("OK: 操作 " + action + ": valid=" + str(result_action['valid']))
            except ValueError as e:
                print("INFO: 操作 " + action + " 被拒绝（权限不足）: " + str(e))
        
        print("\n" + "=" * 60)
        print("所有测试通过!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print("\n[FAIL] 测试失败:", str(e))
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # 清理测试数据
        if os.path.exists(test_storage):
            shutil.rmtree(test_storage)
            print("\n[OK] 已清理测试数据:", test_storage)


def test_session_mode():
    """测试会话模式（传入私钥对象）"""
    
    print("\n" + "=" * 60)
    print("测试会话模式")
    print("=" * 60)
    
    # 使用临时目录进行测试
    test_storage = "Z:/qclaw/test_did_auth_session"
    if os.path.exists(test_storage):
        shutil.rmtree(test_storage)
    os.makedirs(test_storage, exist_ok=True)
    
    try:
        import nacl.signing
        
        # 1. 生成主DID
        multi_manager = MultiInstanceDIDManager(test_storage)
        result = multi_manager.generate_primary_did("test_password_123", force=True)
        primary_did = result["did"]
        
        # 注册实例
        multi_manager.register_instance(primary_did, "nyx-windows", "QClaw (Windows)")
        
        # 2. 解密私钥（会话模式）
        password = "test_password_123"
        did_data = multi_manager._did_manager.load_did(password)
        private_key_bytes = did_data["private_key"]
        signing_key = nacl.signing.SigningKey(private_key_bytes)
        
        # 3. 使用会话模式初始化鉴权器
        print("\n1. 使用会话模式初始化鉴权器...")
        auth = DIDAuthenticator(test_storage, private_key_obj=signing_key)
        print("OK: 会话模式鉴权器初始化成功")
        
        # 4. 生成令牌（不需要密码）
        print("\n2. 测试生成令牌（不需要密码）...")
        token = auth.create_auth_token(
            primary_did=primary_did,
            instance_id="nyx-windows",
            action="memory_write",
            expires_in=3600
            # 不传password参数
        )
        assert token is not None, "令牌生成失败"
        print("OK: 令牌生成成功（会话模式）:", token[:50], "...")
        
        # 5. 验证令牌
        print("\n3. 测试验证令牌...")
        result = auth.verify_token(token)
        assert result["valid"] == True, "令牌验证失败: " + str(result.get('reason'))
        print("OK: 令牌验证成功: valid=" + str(result['valid']))
        
        print("\n" + "=" * 60)
        print("会话模式测试通过!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print("\n[FAIL] 会话模式测试失败:", str(e))
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # 清理测试数据
        if os.path.exists(test_storage):
            shutil.rmtree(test_storage)
            print("\n[OK] 已清理测试数据:", test_storage)


if __name__ == "__main__":
    print("开始测试DID身份鉴权模块...")
    
    # 运行测试
    test1_passed = test_did_authenticator()
    test2_passed = test_session_mode()
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print("基础功能测试:", "通过" if test1_passed else "失败")
    print("会话模式测试:", "通过" if test2_passed else "失败")
    
    if test1_passed and test2_passed:
        print("\n[SUCCESS] 所有测试通过!")
    else:
        print("\n[FAIL] 部分测试失败，请检查实现")
