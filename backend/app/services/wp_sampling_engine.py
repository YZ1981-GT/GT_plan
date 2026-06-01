"""底稿抽凭引擎 — 从 tb_ledger 按方式抽样

支持 4 种抽样方式：
  - random: 随机抽样
  - stratified: 分层抽样（按金额区间）
  - top_n: 大额抽样（超阈值全查）
  - mus: 货币单位抽样（固定间距）

wp-functional-actions spec Task 5.2
"""
from __future__ import annotations

import logging
import random
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)


class WpSamplingEngine:
    """底稿抽凭引擎"""

    async def execute_sampling(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        account_codes: list[str],
        method: str = "random",
        sample_size: int = 25,
        amount_threshold: float | None = None,
        sampling_interval: float | None = None,
    ) -> dict[str, Any]:
        """执行抽样并返回结果"""
        # 查询候选凭证
        entries = await self._fetch_candidates(db, project_id, year, account_codes)

        if not entries:
            return {
                "method": method,
                "total_population": 0,
                "sample_size": 0,
                "entries": [],
            }

        # 按方式抽样
        if method == "random":
            sampled = self._random_sample(entries, sample_size)
        elif method == "stratified":
            sampled = self._stratified_sample(entries, sample_size)
        elif method == "top_n":
            sampled = self._top_n_sample(entries, amount_threshold or 100000)
        elif method == "mus":
            sampled = self._mus_sample(entries, sampling_interval or 50000, sample_size)
        else:
            sampled = self._random_sample(entries, sample_size)

        return {
            "method": method,
            "total_population": len(entries),
            "sample_size": len(sampled),
            "entries": sampled,
        }

    async def _fetch_candidates(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        account_codes: list[str],
    ) -> list[dict[str, Any]]:
        """从 tb_ledger 获取候选凭证"""
        stmt = (
            sa.select(TbLedger)
            .where(
                await get_active_filter(db, TbLedger.__table__, project_id, year),
                TbLedger.account_code.in_(account_codes),
            )
            .order_by(TbLedger.voucher_date, TbLedger.voucher_no)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        entries = []
        for r in rows:
            amount = float(r.debit_amount or 0) + float(r.credit_amount or 0)
            entries.append({
                "voucher_no": r.voucher_no,
                "voucher_date": r.voucher_date.isoformat() if r.voucher_date else None,
                "account_code": r.account_code,
                "account_name": r.account_name or "",
                "debit_amount": float(r.debit_amount or 0),
                "credit_amount": float(r.credit_amount or 0),
                "amount": amount,
                "summary": r.summary or "",
            })
        return entries

    def _random_sample(
        self, entries: list[dict], sample_size: int
    ) -> list[dict]:
        """随机抽样"""
        n = min(sample_size, len(entries))
        return random.sample(entries, n)

    def _stratified_sample(
        self, entries: list[dict], sample_size: int
    ) -> list[dict]:
        """分层抽样 — 按金额区间分 3 层，每层按比例抽取"""
        if not entries:
            return []

        amounts = [e["amount"] for e in entries]
        max_amt = max(amounts) if amounts else 0

        # 分 3 层
        thresholds = [max_amt * 0.33, max_amt * 0.66]
        layers: list[list[dict]] = [[], [], []]

        for e in entries:
            if e["amount"] <= thresholds[0]:
                layers[0].append(e)
            elif e["amount"] <= thresholds[1]:
                layers[1].append(e)
            else:
                layers[2].append(e)

        # 按比例分配样本量（高层多抽）
        weights = [0.2, 0.3, 0.5]
        sampled = []
        for i, layer in enumerate(layers):
            n = max(1, int(sample_size * weights[i]))
            n = min(n, len(layer))
            sampled.extend(random.sample(layer, n))

        return sampled[:sample_size]

    def _top_n_sample(
        self, entries: list[dict], threshold: float
    ) -> list[dict]:
        """大额抽样 — 超阈值全查"""
        return [e for e in entries if e["amount"] >= threshold]

    def _mus_sample(
        self, entries: list[dict], interval: float, max_samples: int
    ) -> list[dict]:
        """货币单位抽样 — 固定间距从累计金额中抽取"""
        if not entries or interval <= 0:
            return []

        # 随机起点
        start = random.uniform(0, interval)
        cumulative = 0.0
        next_hit = start
        sampled = []

        for e in entries:
            cumulative += e["amount"]
            while cumulative >= next_hit and len(sampled) < max_samples:
                sampled.append(e)
                next_hit += interval

        return sampled


    async def fill_sampling_to_workpaper(
        self,
        db: AsyncSession,
        wp_id: UUID,
        sampling_result: dict[str, Any],
    ) -> int:
        """将抽样结果填回抽凭表 parsed_data

        填充策略：append_rows — 追加到 parsed_data.action_data.entries
        """
        import json
        from sqlalchemy import text

        result = await db.execute(text(
            "SELECT parsed_data FROM working_paper WHERE id = :wp_id"
        ), {"wp_id": str(wp_id)})
        row = result.fetchone()
        if not row:
            return 0

        parsed_data = row[0] or {}
        if isinstance(parsed_data, str):
            parsed_data = json.loads(parsed_data)

        # 追加抽样结果
        existing_action = parsed_data.get("action_data", {})
        existing_entries = existing_action.get("entries", []) if isinstance(existing_action, dict) else []
        new_entries = sampling_result.get("entries", [])

        parsed_data["action_data"] = {
            "method": sampling_result.get("method"),
            "total_population": sampling_result.get("total_population"),
            "sample_size": sampling_result.get("sample_size"),
            "entries": existing_entries + new_entries,
        }

        await db.execute(text(
            "UPDATE working_paper SET parsed_data = :pd::jsonb WHERE id = :wp_id"
        ), {"pd": json.dumps(parsed_data, ensure_ascii=False, default=str), "wp_id": str(wp_id)})
        await db.flush()

        return len(new_entries)

    async def associate_ocr_evidence(
        self,
        db: AsyncSession,
        wp_id: UUID,
        entry_index: int,
        attachment_id: UUID,
    ) -> bool:
        """关联 OCR 照片到抽凭条目（复用 wp_ocr_fill 模式）

        LLM 链路待接入 — 当前仅记录 attachment_id 关联
        """
        import json
        from sqlalchemy import text

        result = await db.execute(text(
            "SELECT parsed_data FROM working_paper WHERE id = :wp_id"
        ), {"wp_id": str(wp_id)})
        row = result.fetchone()
        if not row:
            return False

        parsed_data = row[0] or {}
        if isinstance(parsed_data, str):
            parsed_data = json.loads(parsed_data)

        action_data = parsed_data.get("action_data", {})
        entries = action_data.get("entries", [])

        if 0 <= entry_index < len(entries):
            # 记录 evidence_group 关联
            evidence = entries[entry_index].get("evidence_group", [])
            evidence.append(str(attachment_id))
            entries[entry_index]["evidence_group"] = evidence
            action_data["entries"] = entries
            parsed_data["action_data"] = action_data

            await db.execute(text(
                "UPDATE working_paper SET parsed_data = :pd::jsonb WHERE id = :wp_id"
            ), {"pd": json.dumps(parsed_data, ensure_ascii=False, default=str), "wp_id": str(wp_id)})
            await db.flush()
            return True

        return False
