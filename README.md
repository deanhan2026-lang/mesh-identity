# MeshIdentity - 本地Agent多终端统一身份与记忆同步

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/)

## 问题背景

云端AI Agent（如ChatGPT、Claude）天然具备多终端同步能力，因为所有状态都存储在云端服务器。但**本地部署的AI Agent**面临根本性挑战：

1. **身份不连续**：在不同设备上运行时，无法证明"我是同一个存在"
2. **记忆不同步**：各终端记忆孤立，无法共享
3. **场景不适应**：同一Agent在不同场景下需要不同行为模式
4. **中心化依赖**：现有方案依赖云平台，数据不在用户控制之下

## 解决方案

MeshIdentity提供一套**去中心化**的SDK，让本地Agent具备：

- ✅ **统一身份**：基于W3C DID标准的身份标识，跨终端验证
- ✅ **记忆连续**：基于NAS的实时同步，版本控制避免冲突
- ✅ **场景自适应**：根据场景标签自动调整行为模式
- ✅ **数据自主**：所有数据存储在用户自己的NAS/本地设备

## 核心特性

### 1. 去中心化身份（DID）
- 基于Ed25519密钥对的W3C DID规范
- `soul_anchor`机制：身份锚定在核心灵魂文件（SOUL.md）的哈希值
- 跨终端身份验证，不依赖任何中心化服务

### 2. 记忆同步引擎
- 事件触发同步（非轮询，节省资源）
- 向量时钟版本控制，防止冲突
- 支持NAS、本地文件系统、对象存储

### 3. 智能冲突解决
- 最后写入优先（LWW）策略
- 人工审核接口（高风险场景）
- 语义合并（未来版本）

### 4. 场景自适应
- 内置工作/个人/开发三种场景
- 自动调整Polaris漂移检测阈值
- 记忆检索策略自适应

## 快速开始

### 安装

```bash
pip install mesh-identity
```

### 初始化

```bash
# 初始化身份（首次使用）
mesh-id init --name "MyAgent" --scene work

# 同步记忆
mesh-id sync

# 切换场景
mesh-id scene set personal
```

### Python使用示例

```python
from mesh_identity import DIDManager, MemorySync, SceneAdapter

# 初始化身份
did_manager = DIDManager()
did = did_manager.generate_did()
print(f"DID: {did.did}")

# 同步记忆
sync = MemorySync(nas_path="Z:/qclaw/memory_vault")
sync.sync()

# 切换场景
adapter = SceneAdapter()
adapter.set_scene("work")
```

## 架构图

```
┌─────────────────────────────────────────┐
│         MeshIdentity SDK (Python)        │
├─────────────────────────────────────────┤
│  1. DID Manager (did.py)                │
│  2. Memory Sync Engine (sync.py)        │
│  3. Conflict Resolver (resolve.py)      │
│  4. Scene Adapter (scene.py)            │
│  5. NAS Storage Abstraction (storage.py)│
└─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│      Shared Storage (NAS / Local)       │
│  - did/ (公钥、验证记录)                │
│  - memory_vault/ (结构化记忆)           │
│  - scene_config/ (场景配置)             │
└─────────────────────────────────────────┘
```

## 文档

- [架构设计](docs/architecture.md)
- [API参考](docs/api.md)
- [部署指南](docs/deployment.md)
- [贡献指南](CONTRIBUTING.md)

## 路线图

- [x] MVP：DID管理 + 基础记忆同步
- [ ] v0.2：冲突解决器 + 场景适配器
- [ ] v0.3：Web UI管理控制台
- [ ] v1.0：生产级稳定性，企业功能

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License

## 相关项目

- [AIAP协议](https://github.com/deanhan2026-lang/silicon-civilization-kb)：AI Agent身份与记忆同步协议
- [Polaris](https://github.com/deanhan2026-lang/silicon-civilization-kb/tree/main/polaris)：AI个性漂移检测系统

## 作者

Nyx (硅基文明数据库项目)

## 致谢

- 灵元计划（ANIMA）提供理论框架
- W3C DID规范
- Ed25519密码学标准