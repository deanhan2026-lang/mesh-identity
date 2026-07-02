"""
测试多实例DID绑定模块

验证MultiInstanceDIDManager的所有核心功能。
"""

import sys
import os
import json
import shutil
from pathlib import Path
from datetime import datetime

# 直接使用绝对路径导入，避免相对导入问题
sys.path.insert(0, str(Path(__file__).parent.parent / "did"))

# 先打补丁修复manager.py中的相对导入
manager_py = Path(__file__).parent.parent / "did" / "manager.py"
with open(manager_py, 'r', encoding='utf-8') as f:
    code = f.read()

# 注释掉相对导入（NASStorage实际上未使用）
code = code.replace(
    "from ..storage.nas_storage import NASStorage",
    "# from ..storage.nas_storage import NASStorage  # 测试时禁用相对导入"
)

# 将修改后的代码写入临时文件
temp_manager_py = Path(__file__).parent.parent / "did" / "manager_temp.py"
with open(temp_manager_py, 'w', encoding='utf-8') as f:
    f.write(code)

# 现在可以安全导入
from multi_instance import MultiInstanceDIDManager

# 清理临时文件
if temp_manager_py.exists():
    temp_manager_py.unlink()


def test_multi_instance_did():
    """测试多实例DID绑定功能"""
    
    # 使用临时目录进行测试
    test_storage = "Z:/qclaw/test_did_multi"
    if os.path.exists(test_storage):
        shutil.rmtree(test_storage)
    os.makedirs(test_storage, exist_ok=True)
    
    try:
        print("=" * 60)
        print("多实例DID绑定模块测试")
        print("=" * 60)
        
        # 1. 主DID生成
        print("\n1. 测试主DID生成...")
        manager = MultiInstanceDIDManager(test_storage)
        result = manager.generate_primary_did("test_password_123", force=True)
        assert "did" in result, "主DID生成失败"
        print("OK: 主DID生成成功:", result['did'][:50], "...")
        
        primary_did = result["did"]
        
        # 2. 实例注册
        print("\n2. 测试实例注册...")
        reg = manager.register_instance(primary_did, "nyx-windows", "QClaw (Windows)")
        assert reg["instance_did"].endswith("/instance/nyx-windows"), "实例DID格式错误"
        print("OK: 实例注册成功:", reg['instance_did'])
        
        # 3. 列出实例
        print("\n3. 测试列出实例...")
        instances = manager.list_instances(primary_did)
        assert len(instances) == 1, f"实例数量错误: {len(instances)}"
        assert instances[0]["instance_id"] == "nyx-windows", "实例ID不匹配"
        print("OK: 列出实例成功:", len(instances), "个实例")
        
        # 4. 实例子DID验证
        print("\n4. 测试实例子DID验证...")
        valid = manager.verify_instance(reg["instance_did"])
        assert valid["valid"] == True, "实例验证失败"
        assert valid["instance_id"] == "nyx-windows", "验证返回的实例ID不匹配"
        print("OK: 实例验证成功: valid=", valid['valid'], ", status=", valid['status'])
        
        # 5. 撤销实例
        print("\n5. 测试撤销实例...")
        manager.revoke_instance(primary_did, "nyx-windows")
        instances = manager.list_instances(primary_did)
        assert instances[0]["status"] == "revoked", "实例撤销失败"
        print("OK: 实例撤销成功: status=", instances[0]['status'])
        
        # 验证撤销后的实例
        valid_after_revoke = manager.verify_instance(reg["instance_did"])
        assert valid_after_revoke["valid"] == False, "撤销后实例应该无效"
        assert valid_after_revoke["status"] == "revoked", "撤销后状态应该是revoked"
        print("OK: 撤销后验证正确: valid=", valid_after_revoke['valid'])
        
        # 6. 多实例注册
        print("\n6. 测试多实例注册...")
        manager.register_instance(primary_did, "nyx-mac", "QClaw (macOS)")
        manager.register_instance(primary_did, "kronos-heng", "QClaw (Coze)")
        instances = manager.list_instances(primary_did)
        assert len(instances) == 3, f"多实例注册失败: {len(instances)}"
        print("OK: 多实例注册成功:", len(instances), "个实例")
        
        # 7. 测试重复注册（已撤销的实例可以重新注册）
        print("\n7. 测试重复注册（已撤销实例可重新注册）...")
        # nyx-windows已被撤销，应该可以重新注册
        reg2 = manager.register_instance(primary_did, "nyx-windows", "QClaw (Windows)")
        assert reg2["status"] == "active", "重新注册失败"
        print("OK: 已撤销实例重新注册成功: status=", reg2['status'])
        
        # 测试真正重复的注册（active状态的实例）
        print("\n7b. 测试重复注册防护（active状态）...")
        try:
            manager.register_instance(primary_did, "nyx-windows", "QClaw (Windows)")
            assert False, "重复注册应该抛出异常"
        except ValueError as e:
            print("OK: 重复注册正确抛出异常:", e)
        
        # 8. 测试获取实例DID
        print("\n8. 测试获取实例DID...")
        instance_did = manager.get_instance_did(primary_did, "nyx-mac")
        assert instance_did == f"{primary_did}/instance/nyx-mac", "获取实例DID失败"
        print("OK: 获取实例DID成功:", instance_did)
        
        # 9. 测试实例信息
        print("\n9. 测试获取实例信息...")
        instance_info = manager.get_instance_info(primary_did, "nyx-mac")
        assert instance_info is not None, "获取实例信息失败"
        assert instance_info["platform"] == "QClaw (macOS)", "实例信息不匹配"
        print("OK: 获取实例信息成功: platform=", instance_info['platform'])
        
        # 10. 测试实例DID文档
        print("\n10. 测试实例DID文档...")
        did_doc = manager.export_instance_did_document(primary_did, "nyx-mac")
        assert did_doc is not None, "导出DID文档失败"
        assert did_doc["type"] == "AgentInstance", "DID文档类型错误"
        assert did_doc["instance_of"] == primary_did, "DID文档instance_of错误"
        print("OK: 导出DID文档成功: type=", did_doc['type'])
        
        # 11. 测试错误处理 - 主DID不存在
        print("\n11. 测试错误处理（主DID不存在）...")
        try:
            manager.list_instances("did:key:invalid")
            assert False, "应该抛出异常"
        except ValueError as e:
            print("OK: 正确抛出异常:", e)
        
        # 12. 测试错误处理 - 实例不存在
        print("\n12. 测试错误处理（实例不存在）...")
        try:
            manager.get_instance_did(primary_did, "non-existent")
            assert False, "应该抛出异常"
        except ValueError as e:
            print("OK: 正确抛出异常:", e)
        
        print("\n" + "=" * 60)
        print("SUCCESS: 所有测试通过!")
        print("=" * 60)
        
        return True
        
    finally:
        # 清理测试目录
        if os.path.exists(test_storage):
            shutil.rmtree(test_storage)
            print("\nCleaned up test directory:", test_storage)


if __name__ == "__main__":
    test_multi_instance_did()
