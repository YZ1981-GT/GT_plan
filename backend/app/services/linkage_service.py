"""联动查询服务 — 企业级联动核心

提供：
1. TB 行→调整分录关联查询（account_code JOIN adjustments）
2. TB 行→底稿关联查询（wp_account_mapping.json）
3. 影响预判（account_code → 受影响的 TB 行/报表行/底稿）
4. TB 变更历史记录
5. 事件级联日志记录

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 4.1-4.6, 7.1, 7.2, 8.1-8.4
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── wp_account_mapping.json 缓存 ──
_WP_MAPPING_CACHE: list[dict] | None = None
_WP_MAPPING_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"

# ── TB()/SUM_TB() 公式解析正则 ──
_RE_TB = re.compile(r"TB\('([^']+)'\s*(?:,\s*'[^']*')?\)")
_RE_SUM_TB = re.compile(r"SUM_TB\('([^']+)'\s*(?:,\s*'[^']*')?\)")


def _load_wp_mapping() -> list[dict]:
    """加载 wp_account_mapping.json（带缓存）"""
    global _WP_MAPPING_CACHE
    if _WP_MAPPING_CACHE is not None:
        return _WP_MAPPING_CACHE
    if not _WP_MAPPING_PATH.exists():
        _WP_MAPPING_CACHE = []
        return _WP_MAPPING_CACHE
    try:
        with open(_WP_MAPPING_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        _WP_MAPPING_CACHE = data.get("mappings", []) if isinstance(data, dict) else data
    except Exception as e:
        logger.warning("load wp_account_mapping failed: %s", e)
        _WP_MAPPING_CACHE = []
    return _WP_MAPPING_CACHE


def _extract_account_codes_from_formula(formula: str) -> list[str]:
    """从公式中提取引用的科目编码列表。

    支持：
    - TB('1002','期末余额') → ['1002']
    - SUM_TB('1400~1499','期末余额') → ['1400~1499']（范围表示）
    """
    codes: list[str] = []
    for m in _RE_TB.finditer(formula):
        codes.append(m.group(1))
    for m in _RE_SUM_TB.finditer(formula):
        codes.append(m.group(1))
    return codes


def _account_matches_range(account_code: str, range_spec: str) -> bool:
    """判断科目编码是否在范围内。

    range_spec 格式：'1400~1499' 表示前缀在 1400-1499 之间。
    """
    if "~" not in range_spec:
        # 精确匹配或前缀匹配
        return account_code == range_spec or account_code.startswith(range_spec)
    parts = range_spec.split("~")
    if len(parts) != 2:
        return False
    start, end = parts[0].strip(), parts[1].strip()
    prefix_len = len(start)
    code_prefix = account_code[:prefix_len]
    return start <= code_prefix <= end


class LinkageService:
    """联动查询服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ══════════════════════════════════════════════════════════════════════
    # Task 2.1: TB 行→调整分录关联查询
    # ══════════════════════════════════════════════════════════════════════

    async def get_adjustments_for_tb_row(
        self,
        project_id: UUID,
        year: int,
        row_code: str,
    ) -> list[dict]:
        """查询试算平衡表某行关联的调整分录列表。

        逻辑：通过 report_line_mapping 找到该行次对应的 standard_account_code，
        再 JOIN adjustments 表查找该科目的调整分录。
        """
        # Step 1: 从 report_line_mapping 获取该行次对应的标准科目编码
        account_codes_query = text("""
            SELECT DISTINCT standard_account_code
            FROM report_line_mapping
            WHERE project_id = :project_id
              AND report_line_code = :row_code
              AND is_confirmed = true
              AND is_deleted = false
        """)
        result = await self.db.execute(
            account_codes_query,
            {"project_id": str(project_id), "row_code": row_code},
        )
        account_codes = [r[0] for r in result.fetchall() if r[0]]

        if not account_codes:
            return []

        # Step 2: 查询这些科目的调整分录
        # 使用 account_mapping 将标准科目映射回客户科目
        adjustments_query = text("""
            SELECT a.id, a.adjustment_no, a.account_code, a.account_name,
                   a.debit_amount, a.credit_amount, a.summary,
                   a.adjustment_type, a.status, a.created_at,
                   a.entry_group_id
            FROM adjustments a
            JOIN account_mapping am ON am.project_id = a.project_id
                AND am.standard_account_code = a.account_code
                AND am.is_deleted = false
            WHERE a.project_id = :project_id
              AND a.year = :year
              AND a.is_deleted = false
              AND am.standard_account_code = ANY(:codes)
            UNION
            SELECT a.id, a.adjustment_no, a.account_code, a.account_name,
                   a.debit_amount, a.credit_amount, a.summary,
                   a.adjustment_type, a.status, a.created_at,
                   a.entry_group_id
            FROM adjustments a
            WHERE a.project_id = :project_id
              AND a.year = :year
              AND a.is_deleted = false
              AND a.account_code = ANY(:codes)
            ORDER BY created_at DESC
        """)

        try:
            result = await self.db.execute(
                adjustments_query,
                {
                    "project_id": str(project_id),
                    "year": year,
                    "codes": account_codes,
                },
            )
            rows = result.fetchall()
        except Exception:
            # Fallback: 简单查询（SQLite 不支持 ANY）
            placeholders = ", ".join(f":code_{i}" for i in range(len(account_codes)))
            fallback_query = text(f"""
                SELECT a.id, a.adjustment_no, a.account_code, a.account_name,
                       a.debit_amount, a.credit_amount, a.summary,
                       a.adjustment_type, a.status, a.created_at,
                       a.entry_group_id
                FROM adjustments a
                WHERE a.project_id = :project_id
                  AND a.year = :year
                  AND a.is_deleted = false
                  AND a.account_code IN ({placeholders})
                ORDER BY a.created_at DESC
            """)
            params = {"project_id": str(project_id), "year": year}
            for i, code in enumerate(account_codes):
                params[f"code_{i}"] = code
            result = await self.db.execute(fallback_query, params)
            rows = result.fetchall()

        return [
            {
                "id": str(r[0]),
                "adjustment_no": r[1],
                "account_code": r[2],
                "account_name": r[3],
                "debit_amount": float(r[4]) if r[4] else 0,
                "credit_amount": float(r[5]) if r[5] else 0,
                "summary": r[6],
                "adjustment_type": r[7],
                "status": r[8],
                "created_at": r[9].isoformat() if r[9] else None,
                "entry_group_id": str(r[10]) if r[10] else None,
            }
            for r in rows
        ]

    # ══════════════════════════════════════════════════════════════════════
    # Task 2.1: TB 行→底稿关联查询
    # ══════════════════════════════════════════════════════════════════════

    async def get_workpapers_for_tb_row(
        self,
        project_id: UUID,
        year: int,
        row_code: str,
    ) -> list[dict]:
        """查询试算平衡表某行关联的底稿列表。

        逻辑：通过 wp_account_mapping.json 查找该行次编码对应的底稿。
        """
        mappings = _load_wp_mapping()

        # 查找与 row_code 关联的底稿编码
        linked_wp_codes: list[str] = []
        for m in mappings:
            # wp_account_mapping 中 report_line_codes 或 row_codes 字段
            row_codes = m.get("report_line_codes", []) or m.get("row_codes", [])
            account_codes = m.get("account_codes", [])
            wp_code = m.get("wp_code", "")

            if row_code in row_codes and wp_code:
                linked_wp_codes.append(wp_code)

        # 如果没有直接匹配，尝试通过科目编码间接匹配
        if not linked_wp_codes:
            # 获取该行次对应的标准科目
            acct_query = text("""
                SELECT DISTINCT standard_account_code
                FROM report_line_mapping
                WHERE project_id = :project_id
                  AND report_line_code = :row_code
                  AND is_confirmed = true
                  AND is_deleted = false
            """)
            result = await self.db.execute(
                acct_query,
                {"project_id": str(project_id), "row_code": row_code},
            )
            std_codes = [r[0] for r in result.fetchall() if r[0]]

            for m in mappings:
                account_codes = m.get("account_codes", [])
                wp_code = m.get("wp_code", "")
                if wp_code and any(c in account_codes for c in std_codes):
                    linked_wp_codes.append(wp_code)

        if not linked_wp_codes:
            return []

        # 查询底稿详情
        placeholders = ", ".join(f":wp_{i}" for i in range(len(linked_wp_codes)))
        wp_query = text(f"""
            SELECT id, wp_code, wp_name, status, source_type
            FROM working_paper
            WHERE project_id = :project_id
              AND wp_code IN ({placeholders})
              AND is_deleted = false
        """)
        params: dict[str, Any] = {"project_id": str(project_id)}
        for i, code in enumerate(linked_wp_codes):
            params[f"wp_{i}"] = code

        result = await self.db.execute(wp_query, params)
        rows = result.fetchall()

        return [
            {
                "id": str(r[0]),
                "wp_code": r[1],
                "wp_name": r[2],
                "status": r[3],
                "source_type": r[4],
            }
            for r in rows
        ]

    # ══════════════════════════════════════════════════════════════════════
    # Task 2.2: 影响预判逻辑
    # ══════════════════════════════════════════════════════════════════════

    async def get_impact_preview(
        self,
        project_id: UUID,
        year: int,
        account_code: str,
        amount: float | None = None,
    ) -> dict:
        """影响预判：输入科目编码，返回受影响的 TB 行/报表行/底稿。

        逻辑：
        1. 查 account_mapping 得标准科目编码
        2. 查 report_config 得引用该科目的报表行次（解析 formula 中的 TB()/SUM_TB()）
        3. 查 wp_account_mapping 得关联底稿
        4. 检查是否有 status=final 的报表 → 设置警告标记
        """
        result: dict[str, Any] = {
            "affected_tb_rows": [],
            "affected_report_rows": [],
            "affected_workpapers": [],
            "has_final_report_warning": False,
            "unmapped_account": False,
        }

        # Step 1: 查 account_mapping 得标准科目编码
        mapping_query = text("""
            SELECT standard_account_code
            FROM account_mapping
            WHERE project_id = :project_id
              AND (original_account_code = :account_code
                   OR standard_account_code = :account_code)
              AND is_deleted = false
            LIMIT 1
        """)
        mapping_result = await self.db.execute(
            mapping_query,
            {"project_id": str(project_id), "account_code": account_code},
        )
        mapping_row = mapping_result.fetchone()

        standard_code = mapping_row[0] if mapping_row else account_code

        # 如果科目在映射中不存在，标记未映射
        if not mapping_row:
            # 再检查是否直接就是标准科目
            check_query = text("""
                SELECT COUNT(*) FROM account_mapping
                WHERE project_id = :project_id
                  AND standard_account_code = :account_code
                  AND is_deleted = false
            """)
            check_result = await self.db.execute(
                check_query,
                {"project_id": str(project_id), "account_code": account_code},
            )
            count = check_result.scalar() or 0
            if count == 0:
                result["unmapped_account"] = True
                return result

        # Step 2: 查 report_line_mapping 得受影响的 TB 行
        tb_rows_query = text("""
            SELECT DISTINCT rlm.report_line_code, rlm.report_line_name
            FROM report_line_mapping rlm
            WHERE rlm.project_id = :project_id
              AND rlm.standard_account_code = :standard_code
              AND rlm.is_confirmed = true
              AND rlm.is_deleted = false
        """)
        tb_result = await self.db.execute(
            tb_rows_query,
            {"project_id": str(project_id), "standard_code": standard_code},
        )
        for r in tb_result.fetchall():
            result["affected_tb_rows"].append({
                "row_code": r[0],
                "row_name": r[1],
            })

        # Step 3: 查 report_config 得引用该科目的报表行次
        # 获取项目的 applicable_standard
        project_query = text("""
            SELECT template_type, report_scope
            FROM projects
            WHERE id = :project_id
        """)
        proj_result = await self.db.execute(
            project_query, {"project_id": str(project_id)}
        )
        proj_row = proj_result.fetchone()
        applicable_standard = "soe_standalone"
        if proj_row and proj_row[0] and proj_row[1]:
            applicable_standard = f"{proj_row[0]}_{proj_row[1]}"

        # 查询所有有公式的报表行次
        rc_query = text("""
            SELECT row_code, row_name, formula, report_type
            FROM report_config
            WHERE applicable_standard = :standard
              AND formula IS NOT NULL
              AND formula != ''
              AND is_deleted = false
        """)
        rc_result = await self.db.execute(
            rc_query, {"standard": applicable_standard}
        )
        for r in rc_result.fetchall():
            formula = r[2] or ""
            referenced_codes = _extract_account_codes_from_formula(formula)
            for ref_code in referenced_codes:
                if _account_matches_range(standard_code, ref_code):
                    result["affected_report_rows"].append({
                        "row_code": r[0],
                        "row_name": r[1],
                        "report_type": r[3],
                    })
                    break

        # Step 4: 查 wp_account_mapping 得关联底稿
        mappings = _load_wp_mapping()
        for m in mappings:
            account_codes = m.get("account_codes", [])
            wp_code = m.get("wp_code", "")
            wp_name = m.get("wp_name", "")
            if standard_code in account_codes or account_code in account_codes:
                result["affected_workpapers"].append({
                    "wp_code": wp_code,
                    "wp_name": wp_name,
                })

        # Step 5: 检查是否有 status=final 的审计报告
        final_check_query = text("""
            SELECT COUNT(*) FROM audit_report
            WHERE project_id = :project_id
              AND year = :year
              AND status = 'final'
              AND is_deleted = false
        """)
        final_result = await self.db.execute(
            final_check_query,
            {"project_id": str(project_id), "year": year},
        )
        final_count = final_result.scalar() or 0
        if final_count > 0:
            result["has_final_report_warning"] = True

        return result

    # ══════════════════════════════════════════════════════════════════════
    # Task 2.4: TB 变更历史记录
    # ══════════════════════════════════════════════════════════════════════

    async def record_tb_change(
        self,
        project_id: UUID,
        year: int,
        row_code: str,
        operation_type: str,
        operator_id: UUID,
        operator_name: str,
        delta_amount: Decimal | None = None,
        audited_after: Decimal | None = None,
        source_adjustment_id: UUID | None = None,
    ) -> None:
        """记录试算平衡表变更历史。

        operation_type: adjustment_created/modified/deleted/manual_edit/reclassification
        """
        insert_query = text("""
            INSERT INTO tb_change_history
                (id, project_id, year, row_code, operation_type,
                 operator_id, operator_name, delta_amount, audited_after,
                 source_adjustment_id, created_at)
            VALUES
                (:id, :project_id, :year, :row_code, :operation_type,
                 :operator_id, :operator_name, :delta_amount, :audited_after,
                 :source_adjustment_id, :created_at)
        """)
        await self.db.execute(
            insert_query,
            {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "year": year,
                "row_code": row_code,
                "operation_type": operation_type,
                "operator_id": str(operator_id),
                "operator_name": operator_name,
                "delta_amount": float(delta_amount) if delta_amount is not None else None,
                "audited_after": float(audited_after) if audited_after is not None else None,
                "source_adjustment_id": str(source_adjustment_id) if source_adjustment_id else None,
                "created_at": datetime.now(timezone.utc),
            },
        )

    async def get_change_history(
        self,
        project_id: UUID,
        year: int,
        row_code: str,
    ) -> list[dict]:
        """获取试算平衡表某行的变更历史时间线。"""
        query = text("""
            SELECT id, operation_type, operator_id, operator_name,
                   delta_amount, audited_after, source_adjustment_id, created_at
            FROM tb_change_history
            WHERE project_id = :project_id
              AND year = :year
              AND row_code = :row_code
            ORDER BY created_at DESC
            LIMIT 100
        """)
        result = await self.db.execute(
            query,
            {
                "project_id": str(project_id),
                "year": year,
                "row_code": row_code,
            },
        )
        return [
            {
                "id": str(r[0]),
                "operation_type": r[1],
                "operator_id": str(r[2]),
                "operator_name": r[3],
                "delta_amount": float(r[4]) if r[4] is not None else None,
                "audited_after": float(r[5]) if r[5] is not None else None,
                "source_adjustment_id": str(r[6]) if r[6] else None,
                "created_at": r[7].isoformat() if r[7] else None,
            }
            for r in result.fetchall()
        ]

    # ══════════════════════════════════════════════════════════════════════
    # Task 2.8: 事件级联日志记录
    # ══════════════════════════════════════════════════════════════════════

    async def log_cascade(
        self,
        project_id: UUID,
        year: int | None,
        trigger_event: str,
        trigger_payload: dict | None,
        steps: list[dict],
        status: str,
        duration_ms: int,
    ) -> None:
        """记录事件级联执行日志。

        status: running/completed/degraded/failed
        steps: [{step, status, started_at, completed_at, error}]
        """
        insert_query = text("""
            INSERT INTO event_cascade_log
                (id, project_id, year, trigger_event, trigger_payload,
                 steps, status, started_at, completed_at, total_duration_ms)
            VALUES
                (:id, :project_id, :year, :trigger_event, :trigger_payload,
                 :steps, :status, :started_at, :completed_at, :total_duration_ms)
        """)
        now = datetime.now(timezone.utc)
        await self.db.execute(
            insert_query,
            {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "year": year,
                "trigger_event": trigger_event,
                "trigger_payload": json.dumps(trigger_payload) if trigger_payload else "{}",
                "steps": json.dumps(steps),
                "status": status,
                "started_at": now,
                "completed_at": now if status in ("completed", "degraded", "failed") else None,
                "total_duration_ms": duration_ms,
            },
        )

    # ══════════════════════════════════════════════════════════════════════
    # Task 4.7: 一致性校验
    # Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
    # ══════════════════════════════════════════════════════════════════════

    async def run_consistency_check(
        self,
        project_id: UUID,
        year: int,
    ) -> dict:
        """一致性校验：全量重算对比增量结果。

        对比逻辑：
        - 增量值：trial_balance 表中当前存储的 audited_amount
        - 全量值：从 tb_balance 重新计算 unadjusted + adjustments

        Returns:
            {
                "is_consistent": bool,
                "differences": [
                    {
                        "row_code": str,
                        "row_name": str,
                        "incremental_value": float,
                        "full_value": float,
                        "diff": float,
                    }
                ],
                "checked_at": str (ISO timestamp),
            }
        """
        differences: list[dict] = []

        # Step 1: Get current trial_balance rows (incremental values)
        tb_query = text("""
            SELECT row_code, row_name, audited_amount
            FROM trial_balance
            WHERE project_id = :project_id
              AND year = :year
              AND is_deleted = false
        """)
        try:
            result = await self.db.execute(
                tb_query,
                {"project_id": str(project_id), "year": year},
            )
            tb_rows = result.fetchall()
        except Exception:
            # Table may not exist or be empty
            tb_rows = []

        if not tb_rows:
            return {
                "is_consistent": True,
                "differences": [],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        # Step 2: Full recalculation from source data
        # Get unadjusted amounts from tb_balance via account_mapping → report_line_mapping
        full_values: dict[str, float] = {}

        # Get all report_line_mappings for this project
        rlm_query = text("""
            SELECT rlm.report_line_code, rlm.standard_account_code
            FROM report_line_mapping rlm
            WHERE rlm.project_id = :project_id
              AND rlm.is_confirmed = true
              AND rlm.is_deleted = false
        """)
        try:
            rlm_result = await self.db.execute(
                rlm_query, {"project_id": str(project_id)}
            )
            rlm_rows = rlm_result.fetchall()
        except Exception:
            rlm_rows = []

        # Build row_code → [standard_account_codes] mapping
        row_to_accounts: dict[str, list[str]] = {}
        for r in rlm_rows:
            row_code = r[0]
            acct = r[1]
            if row_code not in row_to_accounts:
                row_to_accounts[row_code] = []
            if acct:
                row_to_accounts[row_code].append(acct)

        # Get tb_balance closing amounts by account
        balance_query = text("""
            SELECT account_code, closing_balance
            FROM tb_balance
            WHERE project_id = :project_id
              AND year = :year
              AND is_deleted = false
        """)
        try:
            bal_result = await self.db.execute(
                balance_query,
                {"project_id": str(project_id), "year": year},
            )
            bal_rows = bal_result.fetchall()
        except Exception:
            bal_rows = []

        acct_balances: dict[str, float] = {}
        for r in bal_rows:
            acct_balances[r[0]] = float(r[1]) if r[1] else 0.0

        # Get adjustments by account
        adj_query = text("""
            SELECT account_code,
                   COALESCE(SUM(debit_amount), 0) AS total_debit,
                   COALESCE(SUM(credit_amount), 0) AS total_credit
            FROM adjustments
            WHERE project_id = :project_id
              AND year = :year
              AND is_deleted = false
              AND status != 'rejected'
            GROUP BY account_code
        """)
        try:
            adj_result = await self.db.execute(
                adj_query,
                {"project_id": str(project_id), "year": year},
            )
            adj_rows = adj_result.fetchall()
        except Exception:
            adj_rows = []

        acct_adj: dict[str, dict[str, float]] = {}
        for r in adj_rows:
            acct_adj[r[0]] = {"debit": float(r[1]), "credit": float(r[2])}

        # Calculate full values per row_code
        for row_code, accounts in row_to_accounts.items():
            total = 0.0
            for acct in accounts:
                unadj = acct_balances.get(acct, 0.0)
                adj = acct_adj.get(acct, {"debit": 0.0, "credit": 0.0})
                # audited = unadjusted + aje_dr - aje_cr
                audited = unadj + adj["debit"] - adj["credit"]
                total += audited
            full_values[row_code] = total

        # Step 3: Compare incremental vs full
        for row in tb_rows:
            row_code = row[0]
            row_name = row[1] or ""
            incremental = float(row[2]) if row[2] else 0.0
            full = full_values.get(row_code, 0.0)
            diff = abs(incremental - full)

            # Tolerance: 0.01 (rounding differences)
            if diff > 0.01:
                differences.append({
                    "row_code": row_code,
                    "row_name": row_name,
                    "incremental_value": round(incremental, 2),
                    "full_value": round(full, 2),
                    "diff": round(incremental - full, 2),
                })

        return {
            "is_consistent": len(differences) == 0,
            "differences": differences,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
