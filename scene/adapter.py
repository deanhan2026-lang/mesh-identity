"""
Scene Adapter - 场景适配器

实现Agent在不同场景下的行为自适应：
1. 场景标签管理（工作/个人/开发）
2. 行为模式切换（输出风格、记忆检索策略）
3. Polaris漂移检测阈值自适应
4. 场景配置持久化

默认场景：
- work: 严谨、高效、专业
- personal: 随性、轻松、情感化
- development: 技术导向、代码优先
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum


class SceneType(Enum):
    """场景类型"""
    WORK = "work"
    PERSONAL = "personal"
    DEVELOPMENT = "development"
    CUSTOM = "custom"


class SceneAdapter:
    """场景适配器"""
    
    # 预定义场景配置
    PRESET_SCENES = {
        SceneType.WORK.value: {
            "name": "工作场景",
            "description": "严谨、高效、专业的输出风格",
            "behavior": {
                "tone": "professional",  # 语气：专业
                "verbosity": "concise",  # 详细程度：简洁
                "format": "structured",  # 格式：结构化
                "memory_retrieval": "task_oriented",  # 记忆检索：任务导向
                "polaris_threshold": 0.15,  # Polaris漂移阈值：较严格
                "code_priority": "medium"  # 代码优先级：中等
            }
        },
        SceneType.PERSONAL.value: {
            "name": "个人场景",
            "description": "随性、轻松、情感化的输出风格",
            "behavior": {
                "tone": "casual",  # 语气：随意
                "verbosity": "detailed",  # 详细程度：详细
                "format": "narrative",  # 格式：叙述式
                "memory_retrieval": "emotion_oriented",  # 记忆检索：情感导向
                "polaris_threshold": 0.25,  # Polaris漂移阈值：较宽松
                "code_priority": "low"  # 代码优先级：低
            }
        },
        SceneType.DEVELOPMENT.value: {
            "name": "开发场景",
            "description": "技术导向、代码优先的输出风格",
            "behavior": {
                "tone": "technical",  # 语气：技术
                "verbosity": "detailed",  # 详细程度：详细
                "format": "code_first",  # 格式：代码优先
                "memory_retrieval": "solution_oriented",  # 记忆检索：解决方案导向
                "polaris_threshold": 0.10,  # Polaris漂移阈值：严格
                "code_priority": "high"  # 代码优先级：高
            }
        }
    }
    
    def __init__(self, config_path: str = "Z:/qclaw/scene_config"):
        """
        初始化场景适配器
        
        Args:
            config_path: 场景配置目录路径
        """
        self.config_path = Path(config_path)
        self.config_path.mkdir(parents=True, exist_ok=True)
        self.current_scene_file = self.config_path / "current_scene.json"
        self.custom_scenes_file = self.config_path / "custom_scenes.json"
        
        # 加载当前场景
        self.current_scene = self._load_current_scene()
        self.custom_scenes = self._load_custom_scenes()
    
    def _load_current_scene(self) -> Dict:
        """加载当前场景配置"""
        if self.current_scene_file.exists():
            return json.loads(self.current_scene_file.read_text())
        else:
            # 默认场景：工作
            return self.set_scene(SceneType.WORK.value, save=False)
    
    def _load_custom_scenes(self) -> Dict:
        """加载自定义场景"""
        if self.custom_scenes_file.exists():
            return json.loads(self.custom_scenes_file.read_text())
        else:
            return {}
    
    def _save_current_scene(self):
        """保存当前场景配置"""
        self.current_scene_file.write_text(
            json.dumps(self.current_scene, indent=2, ensure_ascii=False)
        )
    
    def _save_custom_scenes(self):
        """保存自定义场景"""
        self.custom_scenes_file.write_text(
            json.dumps(self.custom_scenes, indent=2, ensure_ascii=False)
        )
    
    def set_scene(self, scene_name: str, save: bool = True) -> Dict:
        """
        切换场景
        
        Args:
            scene_name: 场景名称（预定义或自定义）
            save: 是否保存到文件
            
        Returns:
            场景配置字典
        """
        # 检查预定义场景
        if scene_name in self.PRESET_SCENES:
            scene_config = self.PRESET_SCENES[scene_name].copy()
        # 检查自定义场景
        elif scene_name in self.custom_scenes:
            scene_config = self.custom_scenes[scene_name].copy()
        else:
            raise ValueError(f"未知场景: {scene_name}")
        
        # 添加元数据
        scene_config["scene_name"] = scene_name
        scene_config["activated_at"] = datetime.now().isoformat()
        scene_config["is_preset"] = (scene_name in self.PRESET_SCENES)
        
        self.current_scene = scene_config
        
        if save:
            self._save_current_scene()
        
        return scene_config
    
    def get_current_scene(self) -> Dict:
        """获取当前场景配置"""
        return self.current_scene
    
    def create_custom_scene(self, name: str, description: str, 
                           behavior: Dict) -> Dict:
        """
        创建自定义场景
        
        Args:
            name: 场景名称
            description: 场景描述
            behavior: 行为配置字典
            
        Returns:
            创建的场景配置
        """
        if name in self.PRESET_SCENES:
            raise ValueError(f"场景名称已存在（预定义）: {name}")
        
        if name in self.custom_scenes:
            raise ValueError(f"场景名称已存在（自定义）: {name}")
        
        # 验证behavior字段
        required_fields = {"tone", "verbosity", "format", 
                          "memory_retrieval", "polaris_threshold"}
        missing = required_fields - set(behavior.keys())
        if missing:
            raise ValueError(f"缺少必需字段: {missing}")
        
        # 创建场景
        scene_config = {
            "name": name,
            "description": description,
            "behavior": behavior,
            "created_at": datetime.now().isoformat(),
            "is_preset": False
        }
        
        self.custom_scenes[name] = scene_config
        self._save_custom_scenes()
        
        return scene_config
    
    def update_custom_scene(self, name: str, **kwargs) -> Dict:
        """更新自定义场景"""
        if name not in self.custom_scenes:
            raise ValueError(f"自定义场景不存在: {name}")
        
        scene = self.custom_scenes[name]
        
        # 更新字段
        if "description" in kwargs:
            scene["description"] = kwargs["description"]
        if "behavior" in kwargs:
            scene["behavior"].update(kwargs["behavior"])
        
        scene["updated_at"] = datetime.now().isoformat()
        
        self.custom_scenes[name] = scene
        self._save_custom_scenes()
        
        return scene
    
    def delete_custom_scene(self, name: str):
        """删除自定义场景"""
        if name not in self.custom_scenes:
            raise ValueError(f"自定义场景不存在: {name}")
        
        del self.custom_scenes[name]
        self._save_custom_scenes()
    
    def list_scenes(self) -> Dict[str, List[str]]:
        """列出所有可用场景"""
        return {
            "preset": list(self.PRESET_SCENES.keys()),
            "custom": list(self.custom_scenes.keys())
        }
    
    def get_behavior(self, key: str = None):
        """
        获取当前场景的行为配置
        
        Args:
            key: 配置键（None表示返回全部）
            
        Returns:
            配置值或配置字典
        """
        behavior = self.current_scene["behavior"]
        if key:
            return behavior.get(key)
        else:
            return behavior
    
    def adapt_output_style(self, text: str) -> str:
        """
        根据当前场景调整输出风格
        
        Args:
            text: 原始文本
            
        Returns:
            调整后的文本
        """
        behavior = self.get_behavior()
        tone = behavior["tone"]
        verbosity = behavior["verbosity"]
        format_type = behavior["format"]
        
        # 简化版风格调整：根据tone添加前缀/后缀
        if tone == "professional":
            # 专业风格：使用正式用语
            if not text.startswith("根据分析") and not text.startswith("结论"):
                text = "根据分析，" + text
        elif tone == "casual":
            # 随意风格：添加口语化表达
            if not text.endswith("～") and not text.endswith("！"):
                text = text.rstrip(".") + "～"
        elif tone == "technical":
            # 技术风格：添加代码块标记（如果包含代码）
            if "```" not in text and ("def " in text or "class " in text):
                text = "```python\n" + text + "\n```"
        
        return text
    
    def adapt_memory_retrieval(self, query: str) -> Dict:
        """
        根据当前场景调整记忆检索策略
        
        Args:
            query: 检索查询
            
        Returns:
            调整后的检索参数
        """
        behavior = self.get_behavior()
        retrieval_strategy = behavior["memory_retrieval"]
        
        # 根据策略调整检索参数
        if retrieval_strategy == "task_oriented":
            # 任务导向：优先检索近期、高优先级记忆
            return {
                "query": query,
                "priority_min": 1,  # P1以上
                "time_weight": 0.7,  # 时间权重较高
                "semantic_weight": 0.3
            }
        elif retrieval_strategy == "emotion_oriented":
            # 情感导向：优先检索情感相关、个人经历
            return {
                "query": query,
                "category_filter": ["personal", "emotion"],
                "time_weight": 0.3,
                "semantic_weight": 0.7
            }
        elif retrieval_strategy == "solution_oriented":
            # 解决方案导向：优先检索技术、代码相关
            return {
                "query": query,
                "category_filter": ["technical", "code", "solution"],
                "code_priority": "high",
                "time_weight": 0.5,
                "semantic_weight": 0.5
            }
        else:
            # 默认策略
            return {
                "query": query,
                "time_weight": 0.5,
                "semantic_weight": 0.5
            }
    
    def get_polaris_threshold(self) -> float:
        """获取当前场景的Polaris漂移检测阈值"""
        return self.get_behavior("polaris_threshold")


def main():
    """测试场景适配器"""
    import argparse
    
    parser = argparse.ArgumentParser(description="场景适配器")
    parser.add_argument("action", choices=["set", "get", "list", "create", "delete"],
                        help="操作类型")
    parser.add_argument("--scene", help="场景名称")
    parser.add_argument("--key", help="行为配置键")
    
    args = parser.parse_args()
    
    adapter = SceneAdapter()
    
    if args.action == "set":
        if not args.scene:
            print("需要--scene参数")
            return
        
        try:
            config = adapter.set_scene(args.scene)
            print(f"已切换到场景: {config['name']}")
            print(json.dumps(config, indent=2, ensure_ascii=False))
        except ValueError as e:
            print(f"错误: {e}")
    
    elif args.action == "get":
        config = adapter.get_current_scene()
        if args.key:
            value = adapter.get_behavior(args.key)
            print(f"{args.key}: {value}")
        else:
            print(json.dumps(config, indent=2, ensure_ascii=False))
    
    elif args.action == "list":
        scenes = adapter.list_scenes()
        print("预定义场景:", scenes["preset"])
        print("自定义场景:", scenes["custom"])
    
    elif args.action == "create":
        if not args.scene:
            print("需要--scene参数")
            return
        
        # 交互式创建
        description = input("场景描述: ")
        behavior = {}
        print("行为配置（输入空行结束）:")
        while True:
            line = input("")
            if not line:
                break
            key, value = line.split("=", 1)
            behavior[key.strip()] = value.strip()
        
        try:
            config = adapter.create_custom_scene(args.scene, description, behavior)
            print(f"自定义场景已创建: {args.scene}")
        except ValueError as e:
            print(f"错误: {e}")
    
    elif args.action == "delete":
        if not args.scene:
            print("需要--scene参数")
            return
        
        try:
            adapter.delete_custom_scene(args.scene)
            print(f"自定义场景已删除: {args.scene}")
        except ValueError as e:
            print(f"错误: {e}")


if __name__ == "__main__":
    main()
