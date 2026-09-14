"""审计检查聚合服务 — S1 + S2 + 去重 + 写缓存（Task 2.2）

`AuditCheckAggregator` 负责把多来源检查项合并为统一 `AuditCheckItem`，写入
`WorkingPaper.parsed_data.audit_checks` / `audit_checks_at`（一处读，统一缓存）。

来源（design §2）：
  S1 fine_rule                 ← parsed_data.fine_checks（Excel/OnlyOffice 快照）
  S2 cycle_recon               ← cycle_review_context / d2_review_context（审定↔明细↔TB）
  S3 note_validation           ← NoteValidationEngine.validate_all（项目级，Task 4.1）
  S4 qc                        ← QCEngine（含 QC-27/28）（项目级，Task 4.1）
  S5 unadjusted_misstatement   ← UnadjustedMisstatementService（项目级，Task 4.1）
  S6 reported                  ← 前端上报（tb_recon/adjustment_recon/report_cross_check/cross_sheet）

**Task 2.2 落地 S1（fine_checks 归并）+ S2（cycle_recon 结构化）+ 保留 S6 +
合并去重 + 写缓存**（`recompute_workpaper`）。**Task 4.1 落地 S3（note_validation）+
S4（qc）+ S5（unadjusted_misstatement）三个项目级真源**（`recompute_project` 中接入，
产出 `wp_code=PROJECT_WP_CODE` 的项目级项，不参与 per-wp 写缓存）。

fail-open 原则（design Error Handling / Property 7）：任一来源 S1/S2/S6 计算/读取异常
被隔离，不影响其余来源，异常来源相关项标记未覆盖（passed=null）而非误判通过，
绝不整体抛出。

写缓存原则（Property 8 / Req3.4）：`recompute_workpaper` 仅写 `parsed_data.audit_checks`
/`audit_checks_at` 两个键，**绝不改动** legacy `fine_checks`/`fine_summary`/
`fine_extracted_at` 及 checklist_responses / 底稿其他字段 / 表结构；是否 commit 由
调用方/端点决定，本函数 flush 即可（参照 fine-extract 持久化模式，注意事务边界）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm.attributes import flag_modified

from app.services.audit_check.models import (
    FRONTEND_REPORTABLE_SOURCES,
    PROJECT_WP_CODE,
    SEVERITY_BLOCKING,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    AuditCheckItem,
    AuditCheckSource,
    ProjectCheckSummary,
    from_fine_check_dict,
)
from app.services.cycle_review_context import (
    build_cycle_reconciliation_findings,
    extract_cycle_code,
)
from app.services.d2_review_context import build_d2_reconciliation_findings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 去重语义键（Property 5 / Req4.3）
# ═══════════════════════════════════════════

# 归一化勾稽语义（同一 (wp_code, 语义) 至多保留一条，cycle_recon > fine_rule）
_SEM_AUDITED_VS_TB = "audited_vs_tb"        # 审定表 ↔ 试算表（回写一致性）
_SEM_AUDITED_VS_DETAIL = "audited_vs_detail"  # 审定表 ↔ 明细表


def _dedup_key(item: AuditCheckItem) -> tuple[str, str] | None:
    """把「能明确判定为同一勾稽」的检查项归一化为语义键，否则返回 None（不参与去重）。

    保守原则（Req4.3）：只对能明确判定为「同一勾稽」的两侧做去重，拿不准一律返回
    None（都保留），绝不过度去重把不同检查误删。

    - cycle_recon：审定↔TB（code 含 `-RECON-TB`）→ audited_vs_tb；
                   审定↔明细（code 含 `-RECON-DETAIL`）→ audited_vs_detail；
                   其余（如 `-RECON-ADJ` 信息项）→ None（无对应 fine_rule 项，不去重）。
    - fine_rule：审定↔试算表类 balance check（code 含 `CHK-01` 且 check_type=balance）
                 → audited_vs_tb；审定↔明细类 cross_ref check（code 含 `CHK-03` 且
                 check_type=cross_ref）→ audited_vs_detail；其余 → None（保留）。
    """
    code = (item.code or "").upper()
    check_type = (item.check_type or "").lower()
    wp_code = item.wp_code or ""

    if item.source == AuditCheckSource.CYCLE_RECON.value:
        if "-RECON-TB" in code:
            return (wp_code, _SEM_AUDITED_VS_TB)
        if "-RECON-DETAIL" in code:
            return (wp_code, _SEM_AUDITED_VS_DETAIL)
        return None

    if item.source == AuditCheckSource.FINE_RULE.value:
        if check_type == "balance" and "CHK-01" in code:
            return (wp_code, _SEM_AUDITED_VS_TB)
        if check_type == "cross_ref" and "CHK-03" in code:
            return (wp_code, _SEM_AUDITED_VS_DETAIL)
        return None

    return None


def _merge_dedup(items: list[AuditCheckItem]) -> list[AuditCheckItem]:
    """合并去重：同一 (wp_code, 勾稽语义) 优先保留 cycle_recon，丢弃对应 fine_rule 项。

    保留全部 cycle_recon 项、全部 S6 上报项、以及未被 cycle_recon 覆盖同语义的 fine_rule
    项与所有语义键为 None 的项（保守不误删）。
    """
    cycle_keys: set[tuple[str, str]] = set()
    for it in items:
        if it.source == AuditCheckSource.CYCLE_RECON.value:
            k = _dedup_key(it)
            if k is not None:
                cycle_keys.add(k)

    result: list[AuditCheckItem] = []
    for it in items:
        if it.source == AuditCheckSource.FINE_RULE.value:
            k = _dedup_key(it)
            if k is not None and k in cycle_keys:
                # 同一勾稽已由 cycle_recon（专属组件最新态）覆盖，丢弃 fine_rule 快照项
                continue
        result.append(it)
    return result


# ═══════════════════════════════════════════
# 来源适配纯函数
# ═══════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finding_to_item(
    f: dict,
    *,
    source: str,
    wp_code: str,
    wp_id: str | None,
    sheet_hint: str | None,
    produced_at: str,
) -> AuditCheckItem:
    """把 cycle_review_context / d2_review_context 的结构化 finding dict 转 AuditCheckItem。

    finding dict 字段：code/passed/actual/expected/diff/message/severity/check_type。
    直接映射（Task 2.2）；description 复用 message（finding 无独立 description 字段）。
    """
    return AuditCheckItem(
        code=str(f.get("code", "")),
        source=source,
        wp_code=wp_code,
        wp_id=wp_id,
        sheet_hint=sheet_hint,
        severity=str(f.get("severity", SEVERITY_INFO)),
        check_type=str(f.get("check_type", "")),
        description=str(f.get("message", "")),
        message=str(f.get("message", "")),
        produced_at=produced_at,
        passed=f.get("passed"),
        actual=f.get("actual"),
        expected=f.get("expected"),
        diff=f.get("diff"),
    )


def _item_from_cache_dict(d: dict) -> AuditCheckItem:
    """把缓存 `parsed_data.audit_checks` 中的项 dict（to_dict 输出）还原为 AuditCheckItem。

    用于 S6 保留：只对已上报 source 的项调用；兼容 legacy `type` → `check_type`。
    """
    return AuditCheckItem(
        code=str(d.get("code", "")),
        source=str(d.get("source", "")),
        wp_code=str(d.get("wp_code", "")),
        wp_id=d.get("wp_id"),
        sheet_hint=d.get("sheet_hint"),
        severity=str(d.get("severity", SEVERITY_INFO)),
        check_type=str(d.get("check_type") or d.get("type", "")),
        description=str(d.get("description", "")),
        message=str(d.get("message", "")),
        produced_at=str(d.get("produced_at", "")),
        passed=d.get("passed"),
        actual=d.get("actual"),
        expected=d.get("expected"),
        diff=d.get("diff"),
    )


# ═══════════════════════════════════════════
# 项目级来源适配（S3 / S4 / S5，Task 4.1）
# ═══════════════════════════════════════════
#
# 三者均产出 wp_code=PROJECT_WP_CODE / wp_id=None 的项目级 AuditCheckItem，
# 直接 extend 进 recompute_project 的 all_items（不参与 per-wp 写缓存 —— 它们不
# 归属单张底稿的 parsed_data.audit_checks）。每个函数内部全程 fail-open：读取/
# 计算异常记 warning + exc_info，返回已产出部分（或空），绝不向外抛（Property 7）。
# 复用各自既有服务的真实判定口径（Req4.2），不新造勾稽逻辑。


def _norm_severity(value: str | None, default: str = SEVERITY_INFO) -> str:
    """把外部 severity 归一到 AuditCheckItem 的 blocking/warning/info。

    - QC 已用 blocking/warning/info（直接对齐）。
    - note_validation 用 error/warning（error→blocking / warning→warning）。
    - 其余未知值回退 default。
    """
    s = (value or "").strip().lower()
    if s in (SEVERITY_BLOCKING, SEVERITY_WARNING, SEVERITY_INFO):
        return s
    if s == "error":
        return SEVERITY_BLOCKING
    if s == "warn":
        return SEVERITY_WARNING
    return default


async def _resolve_template_type(db, project_id) -> str:
    """解析项目附注模板变体（soe/listed），供 NoteValidationEngine 加载正确规则集。

    读 Project.template_type；缺失/非法回退 'soe'（validate_all 默认口径）。fail-open。
    """
    try:
        from app.models.core import Project

        val = (
            await db.execute(
                sa.select(Project.template_type).where(Project.id == project_id)
            )
        ).scalar_one_or_none()
        if val in ("soe", "listed"):
            return val
    except Exception:  # noqa: BLE001 — fail-open，回退默认
        logger.warning(
            "audit_check S3 template_type resolve failed project_id=%s",
            project_id, exc_info=True,
        )
    return "soe"


async def _build_note_validation_items(
    db, project_id, year, *, produced_at: str
) -> list[AuditCheckItem]:
    """S3 note_validation ← NoteValidationEngine.validate_all（项目级）。

    validate_all 只返回「未通过」规则（findings=error 级，warning 级在宽松模式折叠进
    warning_summary），故映射到 passed=False 项：error→blocking / warning→warning，
    check_type="note"，code 用 `NOTE-{section}-{ctype}-{i}` 合成（finding 无自身编号）。
    通过的规则不逐条枚举（validate_all 不返回），不产出误导性 passed 项。
    """
    from app.services.note_validation_engine import NoteValidationEngine

    template_type = await _resolve_template_type(db, project_id)
    result = await NoteValidationEngine(db).validate_all(
        project_id, year, template_type=template_type
    )
    items: list[AuditCheckItem] = []

    # 逐条未通过项（宽松模式仅 error；严格模式含 warning，各带 severity 字段）
    for i, f in enumerate(result.get("findings") or []):
        if not isinstance(f, dict):
            continue
        section = str(f.get("note_section", "") or "")
        ctype = str(f.get("check_type", "") or "")
        msg = str(f.get("message", "") or "")
        items.append(
            AuditCheckItem(
                code=f"NOTE-{section or 'X'}-{ctype or 'X'}-{i}",
                source=AuditCheckSource.NOTE_VALIDATION.value,
                wp_code=PROJECT_WP_CODE,
                wp_id=None,
                sheet_hint=section or None,
                severity=_norm_severity(f.get("severity")),
                check_type="note",
                description=msg,
                message=msg,
                produced_at=produced_at,
                passed=False,
                actual=f.get("actual_value"),
                expected=f.get("expected_value"),
            )
        )

    # 宽松模式折叠的 warning 聚合桶（严格模式为空，不重复计）
    for b in result.get("warning_summary") or []:
        if not isinstance(b, dict):
            continue
        section = str(b.get("note_section", "") or "")
        ctype = str(b.get("check_type", "") or "")
        cnt = b.get("count", 0)
        msg = f"附注 {section} {ctype} 存在 {cnt} 项待关注"
        items.append(
            AuditCheckItem(
                code=f"NOTE-WARN-{section or 'X'}-{ctype or 'X'}",
                source=AuditCheckSource.NOTE_VALIDATION.value,
                wp_code=PROJECT_WP_CODE,
                wp_id=None,
                sheet_hint=section or None,
                severity=SEVERITY_WARNING,
                check_type="note",
                description=msg,
                message=msg,
                produced_at=produced_at,
                passed=False,
            )
        )

    return items


async def _build_qc_items(db, project_id, *, produced_at: str) -> list[AuditCheckItem]:
    """S4 qc ← 项目内各底稿最新 QC 结果（WpQcResult.findings）。

    读取每张底稿最新一次 WpQcResult（批量 latest-per-wp 子查询，无 N+1），逐条 finding
    转项目级 AuditCheckItem（wp_code=PROJECT_WP_CODE）：QC finding 即「未通过」问题项，
    passed=False；severity 已是 blocking/warning/info 直接对齐；check_type="qc"，code
    用 QC 规则编号（rule_id）。未跑过 QC 的底稿无结果 → 不产项（不误判通过）。
    """
    from app.models.workpaper_models import WorkingPaper, WpQcResult

    wp_id_rows = (
        await db.execute(
            sa.select(WorkingPaper.id).where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
    ).all()
    wp_ids = [r[0] for r in wp_id_rows]
    if not wp_ids:
        return []

    latest_subq = (
        sa.select(
            WpQcResult.working_paper_id,
            sa.func.max(WpQcResult.check_timestamp).label("max_ts"),
        )
        .where(WpQcResult.working_paper_id.in_(wp_ids))
        .group_by(WpQcResult.working_paper_id)
        .subquery()
    )
    q = sa.select(WpQcResult).join(
        latest_subq,
        sa.and_(
            WpQcResult.working_paper_id == latest_subq.c.working_paper_id,
            WpQcResult.check_timestamp == latest_subq.c.max_ts,
        ),
    )
    qc_results = (await db.execute(q)).scalars().all()

    items: list[AuditCheckItem] = []
    for qc in qc_results:
        for k, f in enumerate(qc.findings or []):
            if not isinstance(f, dict):
                continue
            rule_id = str(f.get("rule_id", "") or "")
            msg = str(f.get("message", "") or "")
            items.append(
                AuditCheckItem(
                    code=rule_id or f"QC-{k}",
                    source=AuditCheckSource.QC.value,
                    wp_code=PROJECT_WP_CODE,
                    wp_id=None,
                    sheet_hint=None,
                    severity=_norm_severity(f.get("severity")),
                    check_type="qc",
                    description=msg,
                    message=msg,
                    produced_at=produced_at,
                    passed=False,
                )
            )
    return items


async def _build_misstatement_items(
    db, project_id, year, *, produced_at: str
) -> list[AuditCheckItem]:
    """S5 unadjusted_misstatement ← UnadjustedMisstatementService.list_misstatements。

    存在未更正错报 → 一条 warning 提示项（passed=False，语义「未通过：存在需关注的未更正
    错报」，message 说明笔数/累计金额）；无错报 → 一条 passed=True 信息项（正向覆盖）。
    check_type="misstatement"。
    """
    from decimal import Decimal

    from app.services.misstatement_service import UnadjustedMisstatementService

    rows = await UnadjustedMisstatementService(db).list_misstatements(project_id, year)
    if not rows:
        return [
            AuditCheckItem(
                code="UM-NONE",
                source=AuditCheckSource.UNADJUSTED_MISSTATEMENT.value,
                wp_code=PROJECT_WP_CODE,
                wp_id=None,
                sheet_hint=None,
                severity=SEVERITY_INFO,
                check_type="misstatement",
                description="未发现未更正错报",
                message="未发现未更正错报",
                produced_at=produced_at,
                passed=True,
            )
        ]

    total = Decimal("0")
    for r in rows:
        try:
            total += Decimal(str(getattr(r, "misstatement_amount", 0) or 0))
        except Exception:  # noqa: BLE001 — 单条金额异常不影响汇总
            continue
    count = len(rows)
    msg = f"存在 {count} 笔未更正错报，累计金额 {total}"
    return [
        AuditCheckItem(
            code="UM-SUMMARY",
            source=AuditCheckSource.UNADJUSTED_MISSTATEMENT.value,
            wp_code=PROJECT_WP_CODE,
            wp_id=None,
            sheet_hint=None,
            severity=SEVERITY_WARNING,
            check_type="misstatement",
            description=msg,
            message=msg,
            produced_at=produced_at,
            passed=False,
            actual=float(total),
        )
    ]


class AuditCheckAggregator:
    """审计检查聚合器 — S1/S2 落地 + 去重 + 写缓存（Task 2.2）。"""

    async def recompute_workpaper(self, db, wp, idx, *, year) -> list[AuditCheckItem]:
        """对单张底稿重算后端可算真源（S1 fine_rule + S2 cycle_recon），保留已上报
        （S6），合并去重后写 `wp.parsed_data['audit_checks']` / `['audit_checks_at']`。

        Args:
            db: 数据库会话（仅用于写回；S2 各构建函数内部自建 session 读取）
            wp: WorkingPaper 实例
            idx: 底稿索引（wp_index，含 wp_code 等）
            year: 审计年度

        Returns:
            合并去重后的 AuditCheckItem 列表。
        """
        parsed_data = wp.parsed_data or {}
        wp_code = getattr(idx, "wp_code", "") or ""
        wp_id = str(wp.id)
        now_iso = _now_iso()

        items: list[AuditCheckItem] = []

        # ── S1 fine_rule ← parsed_data.fine_checks 归并 ──────────────────
        try:
            fine_checks = parsed_data.get("fine_checks", []) or []
            fine_extracted_at = str(parsed_data.get("fine_extracted_at", "") or "")
            for fc in fine_checks:
                if not isinstance(fc, dict):
                    continue
                items.append(
                    from_fine_check_dict(
                        fc,
                        wp_code=wp_code,
                        wp_id=wp_id,
                        produced_at=fine_extracted_at,
                    )
                )
        except Exception:  # noqa: BLE001 — fail-open，异常来源不影响其余
            logger.warning(
                "audit_check S1(fine_rule) recompute failed wp_id=%s", wp_id,
                exc_info=True,
            )

        # ── S2 cycle_recon ← cycle_review_context / d2_review_context ────
        try:
            cycle = extract_cycle_code(wp_code)
            sheet_hint = f"{cycle}-1" if cycle else None  # 审定表 sheet（定位用）
            if wp_code.upper().startswith("D2"):
                findings = await build_d2_reconciliation_findings(wp_id)
            else:
                findings = await build_cycle_reconciliation_findings(wp_id, wp_code)
            for f in findings or []:
                if not isinstance(f, dict):
                    continue
                items.append(
                    _finding_to_item(
                        f,
                        source=AuditCheckSource.CYCLE_RECON.value,
                        wp_code=wp_code,
                        wp_id=wp_id,
                        sheet_hint=sheet_hint,
                        produced_at=now_iso,
                    )
                )
        except Exception:  # noqa: BLE001
            logger.warning(
                "audit_check S2(cycle_recon) recompute failed wp_id=%s", wp_id,
                exc_info=True,
            )

        # ── S6 reported ← 保留前端已上报项（recompute 不清除 S6）──────────
        try:
            cached = parsed_data.get("audit_checks", []) or []
            for d in cached:
                if not isinstance(d, dict):
                    continue
                if d.get("source") in FRONTEND_REPORTABLE_SOURCES:
                    items.append(_item_from_cache_dict(d))
        except Exception:  # noqa: BLE001
            logger.warning(
                "audit_check S6(reported) merge failed wp_id=%s", wp_id,
                exc_info=True,
            )

        # ── 合并去重（同一勾稽单一口径，cycle_recon > fine_rule）──────────
        merged = _merge_dedup(items)

        # ── 写缓存（P8）：仅写 audit_checks / audit_checks_at 两个键 ───────
        try:
            pd = wp.parsed_data or {}
            pd["audit_checks"] = [it.to_dict() for it in merged]
            pd["audit_checks_at"] = now_iso
            wp.parsed_data = pd
            flag_modified(wp, "parsed_data")
            await db.flush()
        except Exception:  # noqa: BLE001 — 写回失败不阻断聚合汇总
            logger.warning(
                "audit_check recompute_workpaper cache write failed wp_id=%s", wp_id,
                exc_info=True,
            )

        return merged

    async def recompute_project(self, db, project_id, year) -> ProjectCheckSummary:
        """遍历项目底稿逐张 `recompute_workpaper` 并汇总。

        S3 note_validation / S4 qc / S5 未更正错报（项目级真源）留 Task 4.1，此处保留
        TODO 占位，不影响 per-wp（S1/S2/S6）聚合。

        Args:
            db: 数据库会话
            project_id: 项目 id
            year: 审计年度

        Returns:
            ProjectCheckSummary（基于全部底稿合并项汇总）。
        """
        from app.models.workpaper_models import WorkingPaper, WpIndex

        all_items: list[AuditCheckItem] = []
        now_iso = _now_iso()

        # per-wp 聚合（S1/S2/S6）—— 遍历底稿（WorkingPaper JOIN WpIndex）
        try:
            rows = (
                await db.execute(
                    sa.select(WorkingPaper, WpIndex)
                    .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                    .where(
                        WorkingPaper.project_id == project_id,
                        WorkingPaper.is_deleted == sa.false(),
                    )
                )
            ).all()
            for wp, idx in rows:
                try:
                    items = await self.recompute_workpaper(db, wp, idx, year=year)
                    all_items.extend(items)
                except Exception:  # noqa: BLE001 — 单底稿失败不阻断其余
                    logger.warning(
                        "audit_check recompute_workpaper failed wp_id=%s",
                        getattr(wp, "id", "?"), exc_info=True,
                    )
        except Exception:  # noqa: BLE001
            logger.warning(
                "audit_check per-workpaper recompute failed project_id=%s",
                project_id, exc_info=True,
            )

        # ── S3 note_validation（项目级）← NoteValidationEngine.validate_all ──
        try:
            all_items.extend(
                await _build_note_validation_items(
                    db, project_id, year, produced_at=now_iso
                )
            )
        except Exception:  # noqa: BLE001 — fail-open，异常来源不影响其余（Property 7）
            logger.warning(
                "audit_check S3(note_validation) recompute failed project_id=%s",
                project_id, exc_info=True,
            )

        # ── S4 qc（项目级）← 各底稿最新 WpQcResult.findings ──────────────────
        try:
            all_items.extend(
                await _build_qc_items(db, project_id, produced_at=now_iso)
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "audit_check S4(qc) recompute failed project_id=%s",
                project_id, exc_info=True,
            )

        # ── S5 unadjusted_misstatement（项目级）← list_misstatements ──────────
        try:
            all_items.extend(
                await _build_misstatement_items(
                    db, project_id, year, produced_at=now_iso
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "audit_check S5(unadjusted_misstatement) recompute failed project_id=%s",
                project_id, exc_info=True,
            )

        return ProjectCheckSummary.from_items(all_items)
