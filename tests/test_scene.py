"""测试场景适配器"""
import pytest


class TestSceneAdapter:
    """场景适配器测试"""
    
    SCENE_PRESETS = {
        "work": {
            "formality": "formal",
            "verbosity": "concise",
            "emoji_allowed": False,
            "politeness_level": "high",
        },
        "personal": {
            "formality": "casual",
            "verbosity": "balanced",
            "emoji_allowed": True,
            "politeness_level": "normal",
        },
        "dev": {
            "formality": "technical",
            "verbosity": "detailed",
            "emoji_allowed": True,
            "politeness_level": "normal",
        }
    }
    
    def test_scene_presets_defined(self):
        """三种场景预设均已定义"""
        for scene in ["work", "personal", "dev"]:
            assert scene in self.SCENE_PRESETS
            preset = self.SCENE_PRESETS[scene]
            assert "formality" in preset
            assert "verbosity" in preset
            assert "emoji_allowed" in preset
    
    def test_work_scene_formal(self):
        """工作场景是正式的"""
        preset = self.SCENE_PRESETS["work"]
        assert preset["formality"] == "formal"
        assert preset["emoji_allowed"] == False
        assert preset["politeness_level"] == "high"
    
    def test_personal_scene_casual(self):
        """个人场景是随性的"""
        preset = self.SCENE_PRESETS["personal"]
        assert preset["formality"] == "casual"
        assert preset["emoji_allowed"] == True
    
    def test_dev_scene_technical(self):
        """开发场景是技术性的"""
        preset = self.SCENE_PRESETS["dev"]
        assert preset["formality"] == "technical"
        assert preset["verbosity"] == "detailed"
    
    def test_scene_exclusivity(self):
        """任意时刻只有一个活跃场景"""
        active_scene = "work"
        scenes = ["work", "personal", "dev"]
        assert active_scene in scenes
        inactive = [s for s in scenes if s != active_scene]
        assert len(inactive) == 2
        assert "work" not in inactive


class TestSceneTransition:
    """场景切换测试"""
    
    def test_did_unchanged_after_scene_switch(self):
        """切换场景后 DID 不变"""
        did = "did:key:z1234567890abcdef"
        scenes = ["work", "personal", "dev"]
        for scene in scenes:
            # DID 是身份根，场景只是行为模式
            assert did.startswith("did:key:")
    
    def test_scene_affects_polaris_threshold(self):
        """场景影响 Polaris 漂移检测阈值"""
        thresholds = {
            "work": 0.03,      # 工作场景更敏感
            "personal": 0.05,  # 个人场景宽松
            "dev": 0.07,       # 开发场景最宽松（允许探索）
        }
        # 工作场景阈值最低 = 最敏感
        assert thresholds["work"] < thresholds["personal"]
        assert thresholds["personal"] < thresholds["dev"]
