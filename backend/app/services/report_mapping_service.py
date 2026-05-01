"""报表模板转换映射服务

国企版 ↔ 上市版报表项目映射规则管理。
- 预设规则：按行名精确匹配自动生成
- 用户可编辑确认后保存
- 首次转换后缓存计算结果到数据库
- 映射规则变更后标记需重算
"""

from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import ReportConfig, FinancialReportType

logger = logging.getLogger(__name__)


class ReportMappingService:
    """报表模板转换映射服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_preset_mapping(
        self,
        report_type: str,
        scope: str,
    ) -> list[dict]:
        """生成预设映射规则（先查同义词表，再按行名精确匹配）"""
        soe_std = f"soe_{scope}"
        listed_std = f"listed_{scope}"

        soe_rows = await self._load_rows(report_type, soe_std)
        listed_rows = await self._load_rows(report_type, listed_std)

        # 加载同义词预设
        synonyms = self._load_synonym_preset(report_type)

        # 按清洗后的行名建索引
        listed_index: dict[str, dict] = {}
        for r in listed_rows:
            listed_index[r["row_name"].strip()] = r
            listed_index[self._clean_name(r["row_name"])] = r

        rules = []
        for soe in soe_rows:
            clean = self._clean_name(soe["row_name"])
            match = None

            # 1. 先查同义词表
            if clean in synonyms:
                target_name = synonyms[clean]
                if target_name is not None:
                    # 在上市版中查找
                    match = listed_index.get(target_name) or listed_index.get(self._clean_name(target_name))

            # 2. 精确匹配
            if not match:
                match = listed_index.get(clean)

            # 3. 模糊匹配（去掉括号内容和标点）
            if not match:
                fuzzy = self._fuzzy_name(clean)
                for lr in listed_rows:
                    if self._fuzzy_name(lr["row_name"]) == fuzzy:
                        match = lr
                        break

            rules.append({
                "soe_row_code": soe["row_code"],
                "soe_row_name": soe["row_name"],
                "listed_row_code": match["row_code"] if match else None,
                "listed_row_name": match["row_name"] if match else None,
            })
        return rules

    async def save_mapping(
        self,
        project_id: UUID,
        report_type: str,
        scope: str,
        rules: list[dict],
    ) -> dict:
        """保存映射规则到项目配置（wizard_state）"""
        from app.models.core import Project

        result = await self.db.execute(
            sa.select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "项目不存在"}

        # 存到 wizard_state.report_mapping
        ws = project.wizard_state or {}
        if "report_mapping" not in ws:
            ws["report_mapping"] = {}

        key = f"{report_type}_{scope}"
        rule_hash = self._hash_rules(rules)
        ws["report_mapping"][key] = {
            "rules": rules,
            "rule_hash": rule_hash,
            "cached": False,
        }

        project.wizard_state = ws
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(project, "wizard_state")
        await self.db.flush()

        return {
            "saved": len(rules),
            "rule_hash": rule_hash,
        }

    async def get_saved_mapping(
        self,
        project_id: UUID,
        report_type: str,
        scope: str,
    ) -> dict | None:
        """获取已保存的映射规则"""
        from app.models.core import Project

        result = await self.db.execute(
            sa.select(Project.wizard_state).where(Project.id == project_id)
        )
        ws = result.scalar_one_or_none()
        if not ws:
            return None

        key = f"{report_type}_{scope}"
        return (ws or {}).get("report_mapping", {}).get(key)

    async def _load_rows(self, report_type: str, applicable_standard: str) -> list[dict]:
        """加载报表配置行"""
        try:
            rt = FinancialReportType(report_type)
        except ValueError:
            return []

        result = await self.db.execute(
            sa.select(ReportConfig)
            .where(
                ReportConfig.report_type == rt,
                ReportConfig.applicable_standard == applicable_standard,
                ReportConfig.is_deleted == sa.false(),
            )
            .order_by(ReportConfig.row_number)
        )
        return [
            {"row_code": r.row_code, "row_name": r.row_name, "row_number": r.row_number}
            for r in result.scalars().all()
        ]

    @staticmethod
    def _clean_name(name: str) -> str:
        """清洗行名用于匹配（去掉特殊前缀标记）"""
        import re
        s = (name or "").strip()
        s = re.sub(r'^[*△▲#]+', '', s).strip()
        return s

    @staticmethod
    def _fuzzy_name(name: str) -> str:
        """模糊化行名（去掉括号内容、标点、空格，只保留核心中文）"""
        import re
        s = (name or "").strip()
        s = re.sub(r'^[*△▲#]+', '', s)
        s = re.sub(r'[（(][^）)]*[）)]', '', s)
        s = re.sub(r'["""\-－：:、．.，,\s]', '', s)
        s = re.sub(r'^[一二三四五六七八九十\d]+', '', s)
        s = re.sub(r'^[加减其中]+[：:]?', '', s)
        return s.strip()

    @staticmethod
    def _load_synonym_preset(report_type: str) -> dict[str, str | None]:
        """加载同义词预设映射表"""
        import json
        from pathlib import Path
        preset_path = Path(__file__).resolve().parent.parent.parent / "data" / "soe_listed_mapping_preset.json"
        try:
            with open(preset_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get(report_type, {})
        except Exception:
            return {}

    @staticmethod
    def _hash_rules(rules: list[dict]) -> str:
        """计算规则哈希，用于检测变更"""
        content = json.dumps(rules, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content.encode()).hexdigest()[:12]
