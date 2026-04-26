"""底稿-科目映射服务

基于 wp_account_mapping.json 提供：
1. 科目→底稿 查找（试算表穿透到底稿）
2. 底稿→科目 查找（底稿预填充取数）
3. 底稿→附注 查找（附注从底稿提数）
4. 预填充：从 trial_balance 自动填充底稿审定表数据
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance

logger = logging.getLogger(__name__)

MAPPING_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "wp_account_mapping.json"
)


@lru_cache(maxsize=1)
def _load_mappings() -> list[dict]:
    try:
        with open(MAPPING_PATH, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data.get("mappings", [])
    except Exception as e:
        logger.warning("load wp_account_mapping failed: %s", e)
        return []


class WpMappingService:
    def __init__(self, db: AsyncSession | None = None):
        self.db = db
        self._mappings = _load_mappings()
        self._by_wp: dict[str, dict] = {}
        self._by_acct: dict[str, list[dict]] = {}
        self._by_note: dict[str, list[dict]] = {}
        for m in self._mappings:
            self._by_wp[m["wp_code"]] = m
            for c in m.get("account_codes", []):
                self._by_acct.setdefault(c, []).append(m)
            ns = m.get("note_section")
            if ns:
                self._by_note.setdefault(ns, []).append(m)

    def find_by_wp_code(self, wp_code: str):
        return self._by_wp.get(wp_code)

    def find_by_account_code(self, code: str):
        return self._by_acct.get(code, [])

    def find_by_note_section(self, ns: str):
        return self._by_note.get(ns, [])

    def get_all_mappings(self):
        return list(self._mappings)

    async def get_prefill_data(
        self, project_id: UUID, year: int, wp_code: str,
    ) -> dict | None:
        if not self.db:
            raise RuntimeError("db required")
        mapping = self.find_by_wp_code(wp_code)
        if not mapping:
            return None
        codes = mapping.get("account_codes", [])
        if not codes:
            return None
        result = await self.db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code.in_(codes),
                TrialBalance.is_deleted == sa.false(),
            )
        )
        rows = result.scalars().all()
        accounts = []
        t_u = Decimal("0")
        t_a = Decimal("0")
        for r in rows:
            u = r.unadjusted_amount or Decimal("0")
            a = r.audited_amount or Decimal("0")
            t_u += u
            t_a += a
            accounts.append({
                "code": r.standard_account_code,
                "name": r.account_name or "",
                "unadjusted": str(u),
                "audited": str(a),
                "opening": str(r.opening_balance or Decimal("0")),
                "rje": str(r.rje_adjustment or Decimal("0")),
                "aje": str(r.aje_adjustment or Decimal("0")),
            })
        return {
            "wp_code": wp_code,
            "wp_name": mapping.get("wp_name", ""),
            "account_name": mapping.get("account_name", ""),
            "report_row": mapping.get("report_row"),
            "note_section": mapping.get("note_section"),
            "accounts": accounts,
            "total_unadjusted": str(t_u),
            "total_audited": str(t_a),
        }

    async def recommend_workpapers(
        self, project_id: UUID, year: int,
        report_scope: str = "standalone",
    ) -> list[dict]:
        """根据试算表有余额的科目，智能推荐需要编制的底稿清单

        逻辑：
        1. 查询试算表中 audited_amount != 0 的科目
        2. 通过 wp_account_mapping 匹配关联底稿
        3. 补充通用必编底稿（B类风险评估、A类完成阶段）
        4. 合并报表额外推荐合并相关底稿
        """
        if not self.db:
            raise RuntimeError("db required")

        # 1. 获取有余额的科目
        result = await self.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.account_name,
                TrialBalance.audited_amount,
            ).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
                sa.or_(
                    TrialBalance.audited_amount != Decimal("0"),
                    TrialBalance.unadjusted_amount != Decimal("0"),
                ),
            )
        )
        active_codes = set()
        for row in result.fetchall():
            active_codes.add(row.standard_account_code)

        # 2. 匹配关联底稿
        recommended = []
        seen_wp = set()
        for code in active_codes:
            for m in self.find_by_account_code(code):
                if m["wp_code"] not in seen_wp:
                    seen_wp.add(m["wp_code"])
                    recommended.append({
                        **m,
                        "reason": "科目有余额",
                        "priority": "required",
                    })

        # 3. 通用必编底稿
        ALWAYS_REQUIRED = [
            {"wp_code": "B1", "wp_name": "业务承接评价表", "cycle": "B",
             "reason": "所有项目必编", "priority": "required"},
            {"wp_code": "B60", "wp_name": "总体审计策略和具体审计计划", "cycle": "B",
             "reason": "所有项目必编", "priority": "required"},
            {"wp_code": "A1", "wp_name": "财务报告程序表", "cycle": "A",
             "reason": "所有项目必编", "priority": "required"},
        ]
        for item in ALWAYS_REQUIRED:
            if item["wp_code"] not in seen_wp:
                seen_wp.add(item["wp_code"])
                recommended.append({
                    "wp_code": item["wp_code"],
                    "wp_name": item["wp_name"],
                    "cycle": item["cycle"],
                    "account_codes": [],
                    "account_name": "",
                    "report_row": None,
                    "note_section": None,
                    "reason": item["reason"],
                    "priority": item["priority"],
                })

        # 4. 合并报表额外推荐
        if report_scope == "consolidated":
            CONSOL_EXTRA = [
                {"wp_code": "A1-14", "wp_name": "完成阶段分析性复核（合并）",
                 "cycle": "A", "reason": "合并报表必编"},
                {"wp_code": "B12", "wp_name": "集团审计计划",
                 "cycle": "B", "reason": "合并报表必编"},
            ]
            for item in CONSOL_EXTRA:
                if item["wp_code"] not in seen_wp:
                    seen_wp.add(item["wp_code"])
                    recommended.append({
                        "wp_code": item["wp_code"],
                        "wp_name": item["wp_name"],
                        "cycle": item["cycle"],
                        "account_codes": [],
                        "account_name": "",
                        "report_row": None,
                        "note_section": None,
                        "reason": item["reason"],
                        "priority": "required",
                    })

        # 按循环排序
        recommended.sort(key=lambda x: (x.get("cycle", "Z"), x.get("wp_code", "")))

        logger.info(
            "recommend_workpapers: project=%s, active_codes=%d, recommended=%d",
            project_id, len(active_codes), len(recommended),
        )
        return recommended
