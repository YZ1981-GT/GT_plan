"""TSJ 提示词库服务

从 TSJ/ 目录加载审计复核提示词 Markdown 文件，
按科目名称匹配，为底稿工作台提供审计要点和复核清单。
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

TSJ_DIR = Path(__file__).resolve().parent.parent.parent.parent / "TSJ"

# 科目名称 → TSJ 文件名关键词映射
_NAME_MAP: dict[str, list[str]] = {
    "货币资金": ["货币资金"],
    "应收票据": ["应收票据"],
    "应收账款": ["应收账款"],
    "预付款项": ["预付账款"],
    "其他应收款": ["其他应收款"],
    "存货": ["存货"],
    "长期股权投资": ["长期股权投资"],
    "投资性房地产": ["投资性房地产"],
    "固定资产": ["固定资产"],
    "在建工程": ["在建工程"],
    "无形资产": ["无形资产"],
    "商誉": ["商誉"],
    "长期待摊费用": ["长期待摊费用"],
    "递延所得税": ["递延所得税资产", "递延所得税负债"],
    "短期借款": ["短期借款"],
    "应付账款": ["应付账款"],
    "合同负债": ["合同负债"],
    "应付职工薪酬": ["应付职工薪酬"],
    "应交税费": ["应交税费"],
    "其他应付款": ["其他应付款"],
    "长期借款": ["长期借款"],
    "实收资本": ["实收资本"],
    "资本公积": ["资本公积"],
    "盈余公积": ["盈余公积"],
    "营业收入": ["收入"],
    "税金及附加": [],
    "销售费用": ["销售费用"],
    "管理费用": ["管理费用"],
    "财务费用": ["财务费用"],
    "研发费用": ["研发费用"],
    "所得税费用": ["所得税费用"],
}


@lru_cache(maxsize=1)
def _load_all_tsj() -> dict[str, str]:
    """加载所有 TSJ Markdown 文件，返回 {文件名stem: 内容}"""
    result = {}
    if not TSJ_DIR.exists():
        logger.warning("TSJ directory not found: %s", TSJ_DIR)
        return result
    for f in TSJ_DIR.glob("*.md"):
        try:
            result[f.stem] = f.read_text(encoding="utf-8-sig")
        except Exception as e:
            logger.warning("Failed to read TSJ file %s: %s", f.name, e)
    logger.info("Loaded %d TSJ prompt files", len(result))
    return result


def _extract_tips(content: str, max_tips: int = 8) -> list[str]:
    """从 Markdown 内容中提取审计要点（提取 checkbox 项）"""
    tips = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- [ ]") or line.startswith("- [x]"):
            tip = line.lstrip("- []x ").strip()
            if tip and len(tip) > 4:
                tips.append(tip)
            if len(tips) >= max_tips:
                break
    return tips


def _extract_checklist(content: str, max_items: int = 10) -> list[str]:
    """提取审计程序检查清单（从二级标题下的 checkbox）"""
    items = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- [ ]"):
            item = line.lstrip("- [] ").strip()
            if item and len(item) > 4:
                items.append(item)
            if len(items) >= max_items:
                break
    return items


def _extract_risk_areas(content: str) -> list[dict]:
    """提取风险领域分级"""
    areas = []
    current_level = ""
    for line in content.split("\n"):
        line = line.strip()
        if "高风险" in line:
            current_level = "high"
        elif "中风险" in line:
            current_level = "medium"
        elif "低风险" in line:
            current_level = "low"
        elif current_level and line.startswith("- "):
            text = line.lstrip("- ").strip()
            if text:
                areas.append({"level": current_level, "text": text})
    return areas[:12]


class TsjPromptService:
    """TSJ 提示词库服务"""

    def __init__(self):
        self._all = _load_all_tsj()

    def get_for_account(self, account_name: str) -> dict | None:
        """根据科目名称获取匹配的 TSJ 提示词"""
        keywords = _NAME_MAP.get(account_name, [account_name])
        for kw in keywords:
            for stem, content in self._all.items():
                if kw in stem:
                    return {
                        "account_name": account_name,
                        "tsj_file": stem,
                        "tips": _extract_tips(content),
                        "checklist": _extract_checklist(content),
                        "risk_areas": _extract_risk_areas(content),
                        "full_content": content,
                    }
        return None

    def get_tips(self, account_name: str) -> list[str]:
        """获取审计要点列表（简化版）"""
        result = self.get_for_account(account_name)
        return result["tips"] if result else []

    def get_checklist(self, account_name: str) -> list[str]:
        """获取审计程序检查清单"""
        result = self.get_for_account(account_name)
        return result["checklist"] if result else []

    def get_system_prompt(self, account_name: str) -> str | None:
        """获取完整 TSJ 内容作为 LLM system prompt"""
        result = self.get_for_account(account_name)
        return result["full_content"] if result else None

    def list_available(self) -> list[str]:
        """列出所有可用的 TSJ 文件"""
        return sorted(self._all.keys())
