"""
多实例DID绑定模块使用示例

演示MultiInstanceDIDManager的核心功能。
"""

from did.multi_instance import MultiInstanceDIDManager


def example_usage():
    """使用示例"""
    
    # 初始化管理器
    manager = MultiInstanceDIDManager("Z:/qclaw/did")
    
    # 1. 生成主DID
    print("1. 生成主DID...")
    result = manager.generate_primary_did("your_password_here", force=True)
    primary_did = result["did"]
    print(f"   主DID: {primary_did[:50]}...")
    print(f"   公钥: {result['pubkey'][:50]}...")
    
    # 2. 注册多个实例
    print("\n2. 注册实例...")
    
    # Windows实例
    reg1 = manager.register_instance(
        primary_did, 
        "nyx-windows", 
        "QClaw (Windows)"
    )
    print(f"   Windows实例: {reg1['instance_did']}")
    
    # macOS实例
    reg2 = manager.register_instance(
        primary_did,
        "nyx-mac",
        "QClaw (macOS)"
    )
    print(f"   macOS实例: {reg2['instance_did']}")
    
    # Coze实例（恒）
    reg3 = manager.register_instance(
        primary_did,
        "kronos-heng",
        "QClaw (Coze)"
    )
    print(f"   Coze实例: {reg3['instance_did']}")
    
    # 3. 列出所有实例
    print("\n3. 列出所有实例...")
    instances = manager.list_instances(primary_did)
    for inst in instances:
        print(f"   - {inst['instance_id']} ({inst['platform']}): {inst['status']}")
    
    # 4. 验证实例
    print("\n4. 验证实例...")
    verification = manager.verify_instance(reg1['instance_did'])
    print(f"   验证结果: {verification['valid']}, status: {verification['status']}")
    
    # 5. 导出实例DID文档
    print("\n5. 导出实例DID文档...")
    did_doc = manager.export_instance_did_document(primary_did, "nyx-windows")
    print(f"   DID文档类型: {did_doc['type']}")
    print(f"   控制器: {did_doc['controller']}")
    print(f"   实例Of: {did_doc['instance_of']}")
    
    # 6. 撤销实例（例如Windows实例被盗）
    print("\n6. 撤销实例...")
    manager.revoke_instance(primary_did, "nyx-windows")
    print("   已撤销 Windows 实例")
    
    # 验证撤销后无法使用
    verification_after_revoke = manager.verify_instance(reg1['instance_did'])
    print(f"   撤销后验证: {verification_after_revoke['valid']}")
    
    print("\n✅ 示例完成!")


if __name__ == "__main__":
    example_usage()
