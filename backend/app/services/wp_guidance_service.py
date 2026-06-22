"""底稿准则说明/编制说明服务 — 按 wp_code 加载 guidance JSON + 编排提取/缓存

统一为所有需要 guidance 的底稿（A3-8/A4-1/A5-3/A5-4 等）提供
准则引用和编制说明数据，供前端侧栏面板展示。

扩展：GuidanceService 类编排 GuidanceExtractor + GuidanceCache，
实现 get_guidance / classify_complexity / get_recommended_questions。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

_GUIDANCE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wp_guidance"


# ---------------------------------------------------------------------------
# 原有向后兼容函数（保留不变）
# ---------------------------------------------------------------------------


def get_wp_guidance(wp_code: str) -> dict | None:
    """按 wp_code 加载准则说明 JSON（无缓存，文件极小每次读取开销可忽略，改 JSON 后无需重启）。

    Returns:
        guidance dict with {wp_code, title, sections: [{title, content}]}
        或 None 如果不存在对应文件
    """
    path = _GUIDANCE_DIR / f"{wp_code}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("加载 guidance 失败 wp_code=%s: %s", wp_code, e)
        return None


def list_available_guidance() -> list[str]:
    """列出所有有 guidance 数据的 wp_code。"""
    if not _GUIDANCE_DIR.exists():
        return []
    return [f.stem for f in _GUIDANCE_DIR.glob("*.json") if not f.stem.startswith("_")]


# ---------------------------------------------------------------------------
# 复杂度分类配置
# ---------------------------------------------------------------------------


def _load_complexity_config() -> dict[str, list[str]]:
    """加载 _complexity.json 配置（无缓存，文件极小每次读取开销可忽略）"""
    config_path = _GUIDANCE_DIR / "_complexity.json"
    if not config_path.exists():
        return {"high": [], "medium": [], "low": []}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("加载 _complexity.json 失败: %s", e)
        return {"high": [], "medium": [], "low": []}


@lru_cache(maxsize=1)
def _load_questions_config() -> dict[str, list[str]]:
    """加载 _questions.json 配置"""
    config_path = _GUIDANCE_DIR / "_questions.json"
    if not config_path.exists():
        return {
            "program": ["这个程序表有哪些关键步骤？"],
            "determination": ["审定表的金额从哪里取数？"],
            "default": ["这个底稿的编制目的是什么？"],
        }
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("加载 _questions.json 失败: %s", e)
        return {"program": [], "determination": [], "default": []}


def _matches_pattern(wp_code: str, pattern: str) -> bool:
    """检查 wp_code 是否匹配通配符模式

    支持的模式：
    - 精确匹配：A17, B60
    - *-1：匹配所有以 -1 结尾的（D2-1, E1-1 等审定表）
    - *A：匹配所有以 A 结尾的（D0A, E1A 等程序表）
    - S*：匹配所有以 S 开头的
    """
    if "*" not in pattern:
        # 精确匹配
        return wp_code == pattern

    # 转换通配符模式为正则
    # *-1 → .*-1$, *A → .*A$, S* → ^S.*
    regex_pattern = pattern.replace("*", ".*")
    if pattern.startswith("*"):
        regex_pattern = regex_pattern + "$"
    elif pattern.endswith("*"):
        regex_pattern = "^" + regex_pattern
    else:
        regex_pattern = "^" + regex_pattern + "$"

    return bool(re.match(regex_pattern, wp_code))


# ---------------------------------------------------------------------------
# GuidanceService 类
# ---------------------------------------------------------------------------


class GuidanceService:
    """底稿编制指导服务 — 编排 GuidanceExtractor + GuidanceCache

    职责：
    - get_guidance：编排提取→缓存→降级链
    - classify_complexity：按 wp_code 判定复杂度等级
    - get_recommended_questions：按 wp_code 模式返回推荐问题
    """

    def __init__(self) -> None:
        from app.services.guidance_cache import GuidanceCache
        from app.services.guidance_extractor import GuidanceExtractor

        self._extractor = GuidanceExtractor()
        self._cache = GuidanceCache(maxsize=128)

    async def get_guidance(
        self,
        wp_code: str,
        wp_name: str = "",
        template_path: Path | None = None,
    ) -> dict[str, Any]:
        """编排提取→缓存→降级链，返回完整 guidance 响应

        Args:
            wp_code: 底稿编码
            wp_name: 底稿名称
            template_path: 模板文件路径（可选）

        Returns:
            dict: {wp_code, wp_name, source, complexity, guidance: {sections, raw_text}, recommended_questions}
        """
        from app.services.guidance_extractor import GuidanceResult

        # 1. 尝试缓存
        cached = self._cache.get(wp_code, template_path)
        if cached is not None:
            result = cached
        else:
            # 2. 缓存未命中：调用 extractor 提取
            result = await self._extractor.extract(wp_code, template_path)
            # 3. 写入缓存
            self._cache.put(wp_code, template_path, result)

        # 4. 补充 wp_name
        if wp_name and not result.wp_name:
            result.wp_name = wp_name

        # 5. 分类复杂度
        complexity = self.classify_complexity(wp_code)
        result.complexity = complexity

        # 6. 获取推荐问题
        recommended_questions = self.get_recommended_questions(wp_code, complexity)

        # 7. 构建响应
        return self._build_response(result, recommended_questions)

    def classify_complexity(self, wp_code: str) -> Literal["high", "medium", "low"]:
        """根据 wp_code 判定底稿复杂度等级

        匹配规则（按优先级）：
        1. _complexity.json 中 high 列表的精确匹配或通配符匹配
        2. medium 列表匹配
        3. 默认 low
        """
        config = _load_complexity_config()

        for pattern in config.get("high", []):
            if _matches_pattern(wp_code, pattern):
                return "high"

        for pattern in config.get("medium", []):
            if _matches_pattern(wp_code, pattern):
                return "medium"

        return "low"

    def get_recommended_questions(
        self, wp_code: str, complexity: str = ""
    ) -> list[str]:
        """根据 wp_code 模式返回推荐问题

        优先级：
        1. wp_guidance/{wp_code}.json 中的 recommended_questions 字段
        2. 按模式匹配 _questions.json 中的问题组
        """
        # 优先从静态 JSON 中读取专属推荐问题
        static_guidance = get_wp_guidance(wp_code)
        if static_guidance and "recommended_questions" in static_guidance:
            return static_guidance["recommended_questions"]

        # 按模式匹配
        questions_config = _load_questions_config()

        # *A → 程序表
        if wp_code.endswith("A") and len(wp_code) > 1:
            return questions_config.get("program", [])

        # *-1 → 审定表
        if re.search(r"-1$", wp_code):
            return questions_config.get("determination", [])

        return questions_config.get("default", [])

    def _build_response(
        self,
        result: Any,  # GuidanceResult
        recommended_questions: list[str],
    ) -> dict[str, Any]:
        """将 GuidanceResult 转为 API 响应 dict"""
        sections = [
            {"title": s.heading, "items": s.content.split("\n") if s.content else []}
            for s in result.sections
        ]

        return {
            "wp_code": result.wp_code,
            "wp_name": result.wp_name or "",
            "source": result.source,
            "complexity": result.complexity,
            "guidance": {
                "sections": sections,
                "raw_text": result.raw_text,
            },
            "recommended_questions": recommended_questions,
        }
