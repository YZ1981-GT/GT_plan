"""审计检查统一模型层

`AuditCheckItem`：聚合各来源（精细化规则 / 审定勾稽 / 附注校验 / QC / 未更正错报 /
前端上报的运行时勾稽）后的统一检查项。序列化后与 legacy `fine_checks` 项字段
**超集兼容**（补齐 `type` 键 + 新增 source/wp_code/wp_id/sheet_hint/produced_at），
供前端统一渲染。

`ProjectCheckSummary`：项目级汇总，通过率口径 —— 分母为已判定数（passed 非 null），
未覆盖（passed=null）绝不计入分母/分子（Requirements 5.2 / Property 1）。

本模块只含纯数据模型与纯函数（`from_items` / `from_fine_check_dict` / `to_dict`），
可独立单测，不依赖 ORM / DB / 事件总线。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ═══════════════════════════════════════════
# 来源枚举 / 子集常量
# ═══════════════════════════════════════════

class AuditCheckSource(str, Enum):
    """检查项来源枚举。

    后端自算来源（S1-S5，由 AuditCheckAggregator 计算并写缓存）：
      FINE_RULE / CYCLE_RECON / NOTE_VALIDATION / QC / UNADJUSTED_MISSTATEMENT
    前端可上报来源（S6，由底稿组件经 report 端点上报的运行时勾稽真源）：
      TB_RECON / ADJUSTMENT_RECON / REPORT_CROSS_CHECK / CROSS_SHEET
    """

    FINE_RULE = "fine_rule"
    CYCLE_RECON = "cycle_recon"
    NOTE_VALIDATION = "note_validation"
    QC = "qc"
    UNADJUSTED_MISSTATEMENT = "unadjusted_misstatement"
    TB_RECON = "tb_recon"
    ADJUSTMENT_RECON = "adjustment_recon"
    REPORT_CROSS_CHECK = "report_cross_check"
    CROSS_SHEET = "cross_sheet"


# 后端自算 source（S1-S5）—— recompute 时由聚合器清除并重算这些 source 的项
BACKEND_COMPUTED_SOURCES: frozenset[str] = frozenset({
    AuditCheckSource.FINE_RULE.value,
    AuditCheckSource.CYCLE_RECON.value,
    AuditCheckSource.NOTE_VALIDATION.value,
    AuditCheckSource.QC.value,
    AuditCheckSource.UNADJUSTED_MISSTATEMENT.value,
})

# 前端可上报 source（S6）—— report 端点仅接受这些 source，recompute 不清除
FRONTEND_REPORTABLE_SOURCES: frozenset[str] = frozenset({
    AuditCheckSource.TB_RECON.value,
    AuditCheckSource.ADJUSTMENT_RECON.value,
    AuditCheckSource.REPORT_CROSS_CHECK.value,
    AuditCheckSource.CROSS_SHEET.value,
})

# 全部合法 source
ALL_SOURCES: frozenset[str] = BACKEND_COMPUTED_SOURCES | FRONTEND_REPORTABLE_SOURCES

# 项目级来源（无归属单张底稿）使用的 wp_code 占位
PROJECT_WP_CODE = "__PROJECT__"

# severity 取值
SEVERITY_BLOCKING = "blocking"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


# ═══════════════════════════════════════════
# 统一检查项
# ═══════════════════════════════════════════

@dataclass
class AuditCheckItem:
    """统一检查项。

    字段严格对齐 design「1. AuditCheckItem」；`passed` 三态：
      True=通过 / False=未通过 / None=未覆盖(pending)。
    """

    code: str                    # 检查项编号（源内唯一）
    source: str                  # 来源（AuditCheckSource 值之一）
    wp_code: str                 # 归属底稿编码（项目级来源用 PROJECT_WP_CODE）
    severity: str                # blocking | warning | info
    check_type: str              # balance | cross_ref | reconciliation | note | qc | ...
    description: str             # 检查项描述
    message: str                 # 判定消息
    produced_at: str             # ISO8601，本项判定时间（新鲜度）
    wp_id: str | None = None     # 归属底稿 id（项目级为 None）
    sheet_hint: str | None = None  # 跳转定位用 sheet 名/编码（可空）
    passed: bool | None = None   # True/False/None(未覆盖)
    actual: float | None = None
    expected: float | None = None
    diff: float | None = None

    def to_dict(self) -> dict:
        """序列化为 legacy `fine_checks` 项的**超集**。

        同时输出 legacy 键 `type`（= check_type）与新键 `check_type`，
        使 legacy 消费者与新面板都能读到（前端统一渲染）。
        """
        return {
            # legacy fine_checks 项字段（超集兼容）
            "code": self.code,
            "type": self.check_type,
            "severity": self.severity,
            "description": self.description,
            "passed": self.passed,
            "actual": self.actual,
            "expected": self.expected,
            "diff": self.diff,
            "message": self.message,
            # 新增字段
            "source": self.source,
            "check_type": self.check_type,
            "wp_code": self.wp_code,
            "wp_id": self.wp_id,
            "sheet_hint": self.sheet_hint,
            "produced_at": self.produced_at,
        }


def from_fine_check_dict(
    d: dict,
    *,
    wp_code: str,
    wp_id: str | None = None,
    produced_at: str = "",
    sheet_hint: str | None = None,
) -> AuditCheckItem:
    """把 legacy `fine_checks` 项 dict 转为 `AuditCheckItem`。

    legacy 项字段：code/type/severity/description/passed/actual/expected/diff/message。
    补齐：source=fine_rule、wp_code、produced_at（用 fine_extracted_at）。
    legacy 键 `type` → `check_type`。
    """
    return AuditCheckItem(
        code=str(d.get("code", "")),
        source=AuditCheckSource.FINE_RULE.value,
        wp_code=wp_code,
        wp_id=wp_id,
        sheet_hint=sheet_hint,
        severity=str(d.get("severity", SEVERITY_INFO)),
        check_type=str(d.get("type", "")),
        description=str(d.get("description", "")),
        message=str(d.get("message", "")),
        produced_at=produced_at,
        passed=d.get("passed"),
        actual=d.get("actual"),
        expected=d.get("expected"),
        diff=d.get("diff"),
    )


# ═══════════════════════════════════════════
# 项目汇总
# ═══════════════════════════════════════════

@dataclass
class ProjectCheckSummary:
    """项目级检查汇总。

    通过率口径（Requirements 5.2 / Property 1）：
      decided = passed 非 null 计数；pass_rate = passed / decided；
      decided == 0 时 pass_rate 为 None；分母绝不含 null / uncovered。
    """

    total: int = 0
    decided: int = 0
    passed: int = 0
    failed: int = 0
    uncovered: int = 0
    pass_rate: float | None = None
    blocking_open: int = 0

    @classmethod
    def from_items(cls, items: list[AuditCheckItem]) -> "ProjectCheckSummary":
        """从检查项列表纯计算汇总。

        - decided：passed ∈ {True, False} 的计数（未覆盖 None 不计入）
        - pass_rate：passed / decided（decided=0 → None）
        - blocking_open：severity=blocking 且 passed is False 的计数
        """
        total = len(items)
        passed = sum(1 for it in items if it.passed is True)
        failed = sum(1 for it in items if it.passed is False)
        uncovered = sum(1 for it in items if it.passed is None)
        decided = passed + failed
        pass_rate = (passed / decided) if decided > 0 else None
        blocking_open = sum(
            1 for it in items
            if it.severity == SEVERITY_BLOCKING and it.passed is False
        )
        return cls(
            total=total,
            decided=decided,
            passed=passed,
            failed=failed,
            uncovered=uncovered,
            pass_rate=pass_rate,
            blocking_open=blocking_open,
        )

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "decided": self.decided,
            "passed": self.passed,
            "failed": self.failed,
            "uncovered": self.uncovered,
            "pass_rate": self.pass_rate,
            "blocking_open": self.blocking_open,
        }
