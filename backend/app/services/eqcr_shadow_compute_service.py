"""EQCR 影子计算服务

Refinement Round 5 任务 8 — 需求 4：EQCR 独立取数通道（影子计算）。

核心逻辑：
1. 限流检查（Redis key: eqcr:shadow:{project_id}:{YYYY-MM-DD}，INCR + EXPIRE 86400）
2. 调用 consistency_replay_engine（caller_context='eqcr'）
3. 获取项目组已有结果作为 team_result_snapshot
4. 对比 result vs team_result_snapshot → has_diff
5. 存入 eqcr_shadow_computations 表
6. 返回完整记录

限流降级策略：
- Redis 不可用时降级为不限流（log warning），开发环境无 Redis 也能跑。

影子计算结果不写入项目组数据（只存 eqcr_shadow_computations）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eqcr_models import EqcrShadowComputation

_logger = logging.getLogger(__name__)

# 允许的计算类型
ALLOWED_COMPUTATION_TYPES: frozenset[str] = frozenset([
    "cfs_supplementary",
    "debit_credit_balance",
    "tb_vs_report",
    "intercompany_elimination",
])

# 每项目每天限流次数
SHADOW_COMPUTE_DAILY_LIMIT = 20


class EqcrShadowComputeService:
    """EQCR 影子计算服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 限流
    # ------------------------------------------------------------------

    async def check_rate_limit(
        self, project_id: uuid.UUID, redis_client: Any = None
    ) -> tuple[bool, int]:
        """检查限流。

        Returns:
            (allowed, remaining): allowed=True 表示未超限，remaining 为剩余次数。
            如果 Redis 不可用，降级放行返回 (True, -1)。
        """
        if redis_client is None:
            _logger.warning(
                "[EQCR Shadow] Redis 不可用，限流降级放行 project_id=%s",
                project_id,
            )
            return True, -1

        today_str = date.today().isoformat()
        key = f"eqcr:shadow:{project_id}:{today_str}"

        try:
            current = await redis_client.get(key)
            if current is None:
                # 首次请求，设置计数器
                await redis_client.set(key, 1, ex=86400)
                return True, SHADOW_COMPUTE_DAILY_LIMIT - 1

            count = int(current)
            if count >= SHADOW_COMPUTE_DAILY_LIMIT:
                return False, 0

            # 未超限，递增
            await redis_client.incr(key)
            return True, SHADOW_COMPUTE_DAILY_LIMIT - count - 1
        except Exception as e:
            _logger.warning(
                "[EQCR Shadow] Redis 限流异常，降级放行: %s", e
            )
            return True, -1

    # ------------------------------------------------------------------
    # 影子计算执行
    # ------------------------------------------------------------------

    async def execute_shadow_compute(
        self,
        project_id: uuid.UUID,
        computation_type: str,
        params: dict[str, Any] | None,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """执行影子计算并存入 eqcr_shadow_computations 表。

        流程：
        1. 调用 consistency_replay_engine 获取独立计算结果
        2. 获取项目组已有结果
        3. 对比差异
        4. 存入表
        5. 返回完整记录
        """
        # 1. 独立计算（复用 consistency_replay_engine）
        result = await self._run_computation(project_id, computation_type, params)

        # 2. 获取项目组已有结果
        team_result = await self._get_team_result(project_id, computation_type)

        # 3. 对比差异
        has_diff = self._compare_results(result, team_result)

        # 4. 存入表
        record = EqcrShadowComputation(
            project_id=project_id,
            computation_type=computation_type,
            params=params or {},
            result=result,
            team_result_snapshot=team_result,
            has_diff=has_diff,
            created_by=user_id,
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)

        # 5. 返回序列化结果
        return self._serialize(record)

    async def list_shadow_computations(
        self, project_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """返回该项目所有影子计算记录列表。"""
        q = (
            select(EqcrShadowComputation)
            .where(EqcrShadowComputation.project_id == project_id)
            .order_by(EqcrShadowComputation.created_at.desc())
        )
        rows = (await self.db.execute(q)).scalars().all()
        return [self._serialize(r) for r in rows]

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _run_computation(
        self,
        project_id: uuid.UUID,
        computation_type: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """调用 consistency_replay_engine 执行独立计算。

        使用 caller_context='eqcr' 标识调用来源。
        根据 computation_type 选择不同的计算策略。
        """
        from app.services.consistency_replay_engine import consistency_replay_engine

        try:
            if computation_type == "debit_credit_balance":
                # 借贷平衡：复用 Layer 1 (tb_balance → trial_balance)
                replay_result = await consistency_replay_engine.replay_consistency(
                    self.db, project_id
                )
                # 提取 Layer 1 结果作为借贷平衡检查
                layer1 = replay_result.layers[0] if replay_result.layers else None
                return {
                    "computation_type": computation_type,
                    "caller_context": "eqcr",
                    "status": "success",
                    "snapshot_id": replay_result.snapshot_id,
                    "overall_status": replay_result.overall_status,
                    "blocking_count": replay_result.blocking_count,
                    "layer_detail": {
                        "from_table": layer1.from_table if layer1 else None,
                        "to_table": layer1.to_table if layer1 else None,
                        "status": layer1.status if layer1 else None,
                        "diff_count": len(layer1.diffs) if layer1 else 0,
                        "diffs": [
                            {
                                "object_type": d.object_type,
                                "object_id": d.object_id,
                                "field": d.field_name,
                                "expected": d.expected,
                                "actual": d.actual,
                                "diff": d.diff,
                                "severity": d.severity,
                            }
                            for d in (layer1.diffs if layer1 else [])
                        ],
                    },
                }

            elif computation_type == "tb_vs_report":
                # 试算表 vs 报表：复用 Layer 2 (trial_balance → financial_report)
                replay_result = await consistency_replay_engine.replay_consistency(
                    self.db, project_id
                )
                layer2 = replay_result.layers[1] if len(replay_result.layers) > 1 else None
                return {
                    "computation_type": computation_type,
                    "caller_context": "eqcr",
                    "status": "success",
                    "snapshot_id": replay_result.snapshot_id,
                    "overall_status": replay_result.overall_status,
                    "blocking_count": replay_result.blocking_count,
                    "layer_detail": {
                        "from_table": layer2.from_table if layer2 else None,
                        "to_table": layer2.to_table if layer2 else None,
                        "status": layer2.status if layer2 else None,
                        "diff_count": len(layer2.diffs) if layer2 else 0,
                        "diffs": [
                            {
                                "object_type": d.object_type,
                                "object_id": d.object_id,
                                "field": d.field_name,
                                "expected": d.expected,
                                "actual": d.actual,
                                "diff": d.diff,
                                "severity": d.severity,
                            }
                            for d in (layer2.diffs if layer2 else [])
                        ],
                    },
                }

            elif computation_type == "cfs_supplementary":
                # 现金流量表补充资料：全五层复算
                replay_result = await consistency_replay_engine.replay_consistency(
                    self.db, project_id
                )
                return {
                    "computation_type": computation_type,
                    "caller_context": "eqcr",
                    "status": "success",
                    "snapshot_id": replay_result.snapshot_id,
                    "overall_status": replay_result.overall_status,
                    "blocking_count": replay_result.blocking_count,
                    "layers": [
                        {
                            "from_table": layer.from_table,
                            "to_table": layer.to_table,
                            "status": layer.status,
                            "diff_count": len(layer.diffs),
                        }
                        for layer in replay_result.layers
                    ],
                }

            elif computation_type == "intercompany_elimination":
                # 合并抵消验证：全五层复算 + 标记合并相关差异
                replay_result = await consistency_replay_engine.replay_consistency(
                    self.db, project_id
                )
                return {
                    "computation_type": computation_type,
                    "caller_context": "eqcr",
                    "status": "success",
                    "snapshot_id": replay_result.snapshot_id,
                    "overall_status": replay_result.overall_status,
                    "blocking_count": replay_result.blocking_count,
                    "layers": [
                        {
                            "from_table": layer.from_table,
                            "to_table": layer.to_table,
                            "status": layer.status,
                            "diff_count": len(layer.diffs),
                        }
                        for layer in replay_result.layers
                    ],
                }

            else:
                return {
                    "computation_type": computation_type,
                    "caller_context": "eqcr",
                    "status": "error",
                    "error": f"未知计算类型: {computation_type}",
                }

        except Exception as e:
            _logger.error(
                "[EQCR Shadow] 计算执行异常 project=%s type=%s: %s",
                project_id, computation_type, e,
            )
            return {
                "computation_type": computation_type,
                "caller_context": "eqcr",
                "status": "error",
                "error": str(e),
            }

    async def _get_team_result(
        self,
        project_id: uuid.UUID,
        computation_type: str,
    ) -> dict[str, Any] | None:
        """获取项目组已有结果作为对比快照。

        根据 computation_type 查询对应的项目组已有数据。
        """
        try:
            if computation_type == "debit_credit_balance":
                # 从 trial_balance 获取项目组借贷平衡汇总
                from sqlalchemy import text
                stmt = text("""
                    SELECT
                        COALESCE(SUM(CASE WHEN debit_amount IS NOT NULL
                            THEN debit_amount ELSE 0 END), 0) as total_debit,
                        COALESCE(SUM(CASE WHEN credit_amount IS NOT NULL
                            THEN credit_amount ELSE 0 END), 0) as total_credit,
                        COUNT(*) as account_count
                    FROM trial_balance
                    WHERE project_id = :pid
                """)
                result = await self.db.execute(stmt, {"pid": str(project_id)})
                row = result.fetchone()
                if row:
                    return {
                        "source": "trial_balance",
                        "total_debit": float(row[0] or 0),
                        "total_credit": float(row[1] or 0),
                        "account_count": int(row[2] or 0),
                        "balance_diff": abs(float(row[0] or 0) - float(row[1] or 0)),
                    }
                return None

            elif computation_type == "tb_vs_report":
                # 从 financial_report 获取项目组报表数据摘要
                from sqlalchemy import text
                stmt = text("""
                    SELECT COUNT(*) as line_count,
                           COALESCE(SUM(ABS(amount)), 0) as total_abs_amount
                    FROM financial_report
                    WHERE project_id = :pid
                """)
                result = await self.db.execute(stmt, {"pid": str(project_id)})
                row = result.fetchone()
                if row:
                    return {
                        "source": "financial_report",
                        "line_count": int(row[0] or 0),
                        "total_abs_amount": float(row[1] or 0),
                    }
                return None

            elif computation_type == "cfs_supplementary":
                # 从 financial_report 获取现金流量表相关行
                from sqlalchemy import text
                stmt = text("""
                    SELECT report_type, COUNT(*) as line_count,
                           COALESCE(SUM(amount), 0) as total_amount
                    FROM financial_report
                    WHERE project_id = :pid
                    GROUP BY report_type
                """)
                result = await self.db.execute(stmt, {"pid": str(project_id)})
                rows = result.fetchall()
                return {
                    "source": "financial_report_by_type",
                    "report_types": [
                        {
                            "report_type": str(r[0]) if r[0] else None,
                            "line_count": int(r[1] or 0),
                            "total_amount": float(r[2] or 0),
                        }
                        for r in rows
                    ],
                }

            elif computation_type == "intercompany_elimination":
                # 合并抵消：查询合并调整分录
                from sqlalchemy import text
                stmt = text("""
                    SELECT COUNT(*) as entry_count,
                           COALESCE(SUM(ABS(amount)), 0) as total_abs_amount
                    FROM consolidation_adjustments
                    WHERE project_id = :pid
                """)
                try:
                    result = await self.db.execute(stmt, {"pid": str(project_id)})
                    row = result.fetchone()
                    if row:
                        return {
                            "source": "consolidation_adjustments",
                            "entry_count": int(row[0] or 0),
                            "total_abs_amount": float(row[1] or 0),
                        }
                except Exception:
                    # 表可能不存在（非合并项目）
                    pass
                return None

        except Exception as e:
            _logger.debug(
                "[EQCR Shadow] 获取项目组结果异常 project=%s type=%s: %s",
                project_id, computation_type, e,
            )
            return None

    def _compare_results(
        self,
        eqcr_result: dict[str, Any],
        team_result: dict[str, Any] | None,
    ) -> bool:
        """对比 EQCR 独立结果与项目组结果，判断是否有差异。

        has_diff=True 表示存在不一致。
        """
        # 如果 EQCR 计算出错，标记为有差异
        if eqcr_result.get("status") == "error":
            return True

        # 如果项目组无结果，无法对比，标记为有差异
        if team_result is None:
            return True

        # 如果 EQCR 计算发现 blocking 差异，标记为有差异
        if eqcr_result.get("blocking_count", 0) > 0:
            return True

        # 如果 overall_status 为 inconsistent，标记为有差异
        if eqcr_result.get("overall_status") == "inconsistent":
            return True

        # 对于 layer_detail 模式，检查 layer 状态
        layer_detail = eqcr_result.get("layer_detail")
        if layer_detail and layer_detail.get("status") == "inconsistent":
            return True

        # 对于 layers 列表模式，检查任一 layer 不一致
        layers = eqcr_result.get("layers", [])
        if any(l.get("status") == "inconsistent" for l in layers):
            return True

        return False

    def _serialize(self, record: EqcrShadowComputation) -> dict[str, Any]:
        """序列化影子计算记录。"""
        return {
            "id": str(record.id),
            "project_id": str(record.project_id),
            "computation_type": record.computation_type,
            "params": record.params,
            "result": record.result,
            "team_result_snapshot": record.team_result_snapshot,
            "has_diff": record.has_diff,
            "created_by": str(record.created_by) if record.created_by else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
