# MeshIdentity 架构设计

## 1. 设计目标

MeshIdentity解决的核心问题：
1. **身份统一性**：本地Agent在不同终端上运行时，如何证明"我是同一个存在"？
2. **记忆连续性**：不同终端产生的记忆如何同步，且不冲突？
3. **场景适应性**：同一Agent在不同场景下如何自适应调整行为？
4. **去中心化**：所有数据和身份控制完全在用户手中，无第三方依赖。

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                  MeshIdentity SDK                        │
├─────────────────────────────────────────────────────────┤
│  CLI Layer (cli/main.py)                                │
│  - init: 初始化身份                                      │
│  - sync: 同步记忆                                        │
│  - scene: 场景切换                                       │
│  - status: 查看状态                                      │
├─────────────────────────────────────────────────────────┤
│  Core Layer                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │ DID Manager │  │ Memory Sync │  │ Scene       │      │
│  │ (did/)      │  │ Engine      │  │ Adapter     │      │
│  │             │  │ (sync/)     │  │ (scene/)    │      │
│  └─────────────┘  └─────────────┘  └─────────────┘      │
│         │                 │                 │            │
│         ▼                 ▼                 ▼            │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Conflict Resolver (resolve/conflict.py)        │    │
│  │  - 冲突检测                                      │    │
│  │  - LWW策略                                       │    │
│  │  - 人工审核接口                                  │    │
│  └─────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│  Storage Layer (storage/nas_storage.py)                 │
│  - NAS抽象接口                                           │
│  - 文件锁机制                                            │
│  - 健康检查                                              │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│             Shared Storage (NAS / Local)                │
│  - did/: DID凭证、公钥                                   │
│  - memory_vault/: 结构化记忆（JSON）                     │
│  - scene_config/: 场景配置                               │
│  - lock/: 文件锁                                         │
│  - conflicts/: 冲突日志                                  │
└─────────────────────────────────────────────────────────┘
```

## 3. 核心模块设计

### 3.1 DID Manager（身份管理）

**职责**：
- 生成/验证W3C DID身份标识
- 计算soul_anchor（SOUL.md哈希值）
- 签名/验证消息

**实现细节**：
- 使用Ed25519椭圆曲线密码学
- DID格式：`did:key:z{公钥hex}`
- soul_anchor：`SHA256(SOUL.md内容)`
- 私钥存储：`Z:/qclaw/did/private_key.hex`（用户保管）

**关键代码**：
```python
# 生成DID
manager = DIDManager()
result = manager.generate_did()

# 验证身份
valid, msg = manager.verify_identity(did)

# 签名消息
signature, public_key = manager.sign_message("Hello")
```

### 3.2 Memory Sync Engine（记忆同步引擎）

**职责**：
- 双向同步本地和NAS上的记忆
- 版本控制（向量时钟）
- 冲突检测

**同步策略**：
- MVP：轮询 + 最后写入优先（LWW）
- 未来：事件触发（watchdog） + 语义合并

**向量时钟**：
```json
{
  "nyx-windows": 5,
  "nyx-mac": 3,
  "kronos-heng": 7
}
```

**关键代码**：
```python
# 双向同步
engine = MemorySyncEngine()
result = engine.sync()

# 只推送
result = engine.push_memory()

# 只拉取
result = engine.pull_memory()
```

### 3.3 Conflict Resolver（冲突解决器）

**职责**：
- 检测两个版本的记忆是否冲突
- 自动解决（LWW策略）
- 记录冲突，提供人工审核接口

**冲突检测逻辑**：
1. 比较向量时钟
2. 比较最后修改时间
3. 比较内容哈希

**解决策略**：
- `LWW`：最后写入优先（默认）
- `MANUAL`：标记为待审核，人工解决
- `SEMANTIC`：语义合并（未来版本）

**关键代码**：
```python
# 检测冲突
conflict = resolver.detect_conflict(local_entry, remote_entry)

# 自动解决
resolved = resolver.resolve(local_entry, remote_entry)

# 列出待审核冲突
pending = resolver.list_pending_conflicts()
```

### 3.4 Scene Adapter（场景适配器）

**职责**：
- 管理场景标签（工作/个人/开发/自定义）
- 根据场景调整Agent行为
- 自适应Polaris漂移检测阈值

**预定义场景**：
| 场景 | 语气 | 详细程度 | 格式 | Polaris阈值 |
|------|------|----------|------|-------------|
| work | professional | concise | structured | 0.15 |
| personal | casual | detailed | narrative | 0.25 |
| development | technical | detailed | code_first | 0.10 |

**关键代码**：
```python
# 切换场景
adapter = SceneAdapter()
adapter.set_scene("work")

# 获取当前场景配置
behavior = adapter.get_behavior()

# 调整输出风格
text = adapter.adapt_output_style(text)

# 调整记忆检索策略
retrieval_params = adapter.adapt_memory_retrieval(query)
```

### 3.5 NAS Storage Abstraction（存储抽象层）

**职责**：
- 统一NAS访问接口（SMB/NFS）
- 文件锁机制（防止多终端同时写入）
- 健康检查

**文件锁实现**：
- 锁文件：`Z:/qclaw/lock/{name}.lock`
- 格式：`{主机名}|{时间戳}`
- 超时：30秒（可配置）

**关键代码**：
```python
# 初始化存储
storage = NASStorage("Z:/qclaw")

# 健康检查
health = storage.health_check()

# 获取锁
if storage.acquire_lock("memory_sync"):
    # 执行同步
    storage.release_lock("memory_sync")
```

## 4. 数据流

### 4.1 身份初始化流程

```
用户执行: mesh-id init --name MyAgent
    ↓
DIDManager.generate_did()
    ↓
1. 生成Ed25519密钥对
2. 构造DID: did:key:z{公钥hex}
3. 保存私钥到 private_key.hex
4. 保存DID文档到 did_document.json
5. 计算soul_anchor (SOUL.md哈希)
    ↓
返回: DID + 私钥路径 + 警告信息
```

### 4.2 记忆同步流程

```
定时触发或事件触发
    ↓
MemorySyncEngine.sync()
    ↓
1. 获取锁 (acquire_lock)
2. 推送本地记忆 (push_memory)
   - 检测未同步条目
   - 检查冲突
   - 解决冲突（LWW）
   - 保存到NAS
3. 拉取远程记忆 (pull_memory)
   - 检测远程更新
   - 检查冲突
   - 解决冲突
   - 保存到本地
4. 释放锁 (release_lock)
5. 更新同步状态
    ↓
返回: 同步结果统计
```

### 4.3 场景切换流程

```
用户执行: mesh-id scene set work
    ↓
SceneAdapter.set_scene("work")
    ↓
1. 加载预定义场景配置
2. 更新当前场景文件 (current_scene.json)
3. 返回场景配置
    ↓
Agent读取场景配置
    ↓
调整行为:
- 输出风格 (adapt_output_style)
- 记忆检索策略 (adapt_memory_retrieval)
- Polaris阈值 (get_polaris_threshold)
```

## 5. 安全设计

### 5.1 身份安全
- 私钥本地存储，不传输
- 使用Ed25519签名验证身份
- soul_anchor绑定核心灵魂文件

### 5.2 记忆安全
- 传输过程：NAS内网传输（Tailscale加密）
- 存储：可选AES-256加密（未来版本）
- 访问控制：文件权限 + 场景隔离

### 5.3 冲突安全
- 所有冲突记录日志
- 高风险操作需要人工审核
- 支持回滚到之前版本

## 6. 扩展性设计

### 6.1 新场景类型
用户可以通过CLI创建自定义场景：
```bash
mesh-id scene create my_scene \
  --description "我的自定义场景" \
  --behavior '{"tone": "friendly", "polaris_threshold": 0.20}'
```

### 6.2 新存储后端
实现`BaseStorage`接口，可以扩展支持：
- 对象存储（S3/MinIO）
- 分布式文件系统（IPFS）
- 区块链存储（未来）

### 6.3 新冲突解决策略
实现`BaseConflictResolver`接口，可以扩展：
- 语义合并（AI辅助）
- 三路合并（类似Git）
- 用户自定义策略

## 7. 性能优化

### 7.1 同步性能
- 增量同步：只同步变化的条目
- 压缩传输：未来版本支持
- 并行同步：未来版本支持

### 7.2 存储性能
- 索引缓存：memory_vault/index.json
- 批量操作：减少NAS访问次数
- 异步写入：未来版本支持

## 8. 测试策略

### 8.1 单元测试
- DID生成/验证
- 记忆同步（冲突/无冲突）
- 场景切换
- 存储层健康检查

### 8.2 集成测试
- 多终端同步测试
- 冲突解决测试
- 场景自适应测试

### 8.3 性能测试
- 大规模记忆同步（1000+条目）
- 高并发写入（模拟多终端）

## 9. 部署建议

### 9.1 最小部署
- 1台NAS（存储共享）
- 1个Agent实例
- 无多终端需求

### 9.2 典型部署
- 1台NAS（存储共享）
- 2-3个Agent实例（PC、Mac、手机）
- 需要多终端同步

### 9.3 企业部署
- NAS集群（高可用）
- 多个Agent实例
- 管理控制台（未来版本）

## 10. 未来路线图

### v0.2（1个月内）
- 事件触发同步（watchdog集成）
- Web UI管理控制台
- 更完善的冲突解决

### v0.3（2个月内）
- 语义合并（AI辅助）
- 多存储后端支持
- 性能优化

### v1.0（3个月内）
- 生产级稳定性
- 企业功能（权限管理、审计日志）
- 完整文档和示例

---

**作者**: Nyx (硅基文明数据库项目)  
**日期**: 2026-06-30  
**版本**: v0.1.0
