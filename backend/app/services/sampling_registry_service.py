"""抽样登记服务 — CAS 1314 记录表的可查询侧投影（sampling-compliance-closure R5）

背景（2026-08-04 实证）：`sampling_records` 0 行、`sampled_vouchers` 1 行
（唯一写入点是 `ledger_penetration` 的穿透页手工标记，与抽凭引擎完全不通），
而 CAS 1314 要求的记录项（总体描述 / 样本量依据 / 偏差笔数 / 推断错报 / 错报上限 /
结论）正是这两张表的字段。真实留痕全在 `workpaper_extraction_log.extraction_criteria`
JSONB 里 → 无法在项目层面一次性查询归档完整性，且重复抽凭只能在单个底稿内发现。

**权威 / 投影分工（勿混）**：
- 权威 = `workpaper_extraction_log.extraction_criteria`（批次维度唯一，含 evaluation）
- 投影 = 本模块写入的 `sampling_records` / `sampled_vouchers`（供项目级/QC 级查询）
两者由同一次写入同时更新。这是平台既有的「JSON 承载 + 列投影」范式，不是双真源。

**fail-open 边界**：本模块全部写入失败一律 `logger.warning` 后返回，不得让审计师的
回填/评价整体失败 —— 投影坏了不影响权威留痕。但**必须留 WARNING**，否则 fail-open
就变成静默黑洞（守卫用 caplog 钉死）。

Validates: Requirements 5.1, 5.2, 5.5, 5.6
Properties: Property 11, Property 12, Property 14
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import SampledVoucher, SamplingRecord

logger = logging.getLogger(__name__)

# 抽样方法 → 中文名（用于生成 sampling_purpose / population_description 的可读文本）
_METHOD_LABELS = {
    "random": "随机抽样",
    "stratified": "金额分层抽样",
    "specific_item": "特定项目选取",
    "systematic": "系统（等距）抽样",
    "mus": "货币单元抽样（MUS）",
}

_DIRECTION_LABELS = {"all": "借贷不限", "debit": "仅借方", "credit": "仅贷方"}


def _as_decimal(value: Any) -> Decimal | None:
    """安全转 Decimal；不可解析返回 None（**不返回 0** —— 「取不到」与「是 0」不同）。"""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


# ─── 纯函数：留痕 → 记录表字段映射 ────────────────────────────────────────────


def build_population_description(criteria: dict) -> str:
    """把抽样过滤条件渲染成中文总体描述（CAS 1314 要求记录「总体」）。

    纯函数，便于单测。取不到任何条件时返回明确的「未记录过滤条件」而非空串 ——
    空串在归档核对时无法与「有条件但渲染失败」区分。
    """
    filters = criteria.get("filters") if isinstance(criteria.get("filters"), dict) else {}
    parts: list[str] = []

    codes = filters.get("account_codes") or []
    if codes:
        parts.append("科目 " + "、".join(str(c) for c in codes))

    periods = filters.get("period_range") or []
    if periods and len(periods) < 12:
        parts.append("会计期间 " + "、".join(str(p) for p in periods) + " 月")
    elif periods:
        parts.append("全年度")

    amount_min = filters.get("amount_min")
    amount_max = filters.get("amount_max")
    if amount_min not in (None, "") and amount_max not in (None, ""):
        parts.append(f"金额 {amount_min}~{amount_max}")
    elif amount_min not in (None, ""):
        parts.append(f"金额 ≥ {amount_min}")
    elif amount_max not in (None, ""):
        parts.append(f"金额 ≤ {amount_max}")

    direction = filters.get("direction_filter")
    if direction and direction != "all":
        parts.append(_DIRECTION_LABELS.get(str(direction), str(direction)))

    vtypes = filters.get("voucher_type_filter") or []
    if vtypes:
        parts.append("凭证类型 " + "、".join(str(v) for v in vtypes))

    keyword = filters.get("summary_keyword")
    if keyword:
        parts.append(f"摘要含「{keyword}」")

    unit = criteria.get("sampling_unit") or filters.get("sampling_unit")
    if unit == "voucher":
        parts.append("抽样单位=整张凭证")

    if not parts:
        return "未记录过滤条件（抽样时点留痕缺失）"
    return "序时账；" + "；".join(parts)


def build_sampling_purpose(criteria: dict) -> str:
    """抽样目的：方法 + 阶段 + 重抽原因（若有）。"""
    method = str(criteria.get("sampling_method") or "")
    label = _METHOD_LABELS.get(method, method or "未记录方法")
    phase = criteria.get("phase")
    phase_label = {"preliminary": "预审", "final": "年审"}.get(str(phase), str(phase or ""))
    text = f"{label}抽凭"
    if phase_label:
        text += f"（{phase_label}阶段）"
    reason = criteria.get("resample_reason")
    if reason:
        text += f"；重抽原因：{reason}"
    return text


def build_method_description(criteria: dict) -> str:
    """样本量与抽样间隔的确定依据（CAS 1314 要求记录「样本量确定依据」）。"""
    parts: list[str] = []
    method = str(criteria.get("sampling_method") or "")
    parts.append(f"方法={_METHOD_LABELS.get(method, method or '未记录')}")
    if criteria.get("confidence_level") not in (None, ""):
        parts.append(f"置信度={criteria['confidence_level']}")
    if criteria.get("tolerable_misstatement") not in (None, ""):
        parts.append(f"可容忍错报={criteria['tolerable_misstatement']}")
    if criteria.get("expected_misstatement") not in (None, ""):
        parts.append(f"预期错报={criteria['expected_misstatement']}")
    if criteria.get("suggested_sample_size") not in (None, ""):
        parts.append(f"系统建议样本量={criteria['suggested_sample_size']}")
    if criteria.get("sampling_interval") not in (None, ""):
        parts.append(f"抽样间隔={criteria['sampling_interval']}")
    if criteria.get("random_seed") not in (None, ""):
        parts.append(f"随机种子={criteria['random_seed']}")
    if criteria.get("algo_version"):
        parts.append(f"算法版本={criteria['algo_version']}")
    if criteria.get("dataset_id"):
        parts.append(f"抽样框版本={criteria['dataset_id']}")
    return "；".join(parts)


#: 处置方式 → 中文标签（投影到 `conclusion` 文本，UI 全中文化）
_UNCHECKED_MODE_LABELS = {
    "treated_as_deviation": "视同偏差",
    "alternative_performed": "已实施替代程序",
}

#: 偏差性质 → 中文标签。与 C 类控制测试 `useDeviationDecisionTree.getStepOptions(2)`
#: 逐字一致（前端 `samplingDeviationNature.ts` 是标签真源并有交叉锁死守卫）。
_DEVIATION_NATURE_LABELS = {
    "systematic": "系统性偏差",
    "human": "人为偏差",
    "random": "随机性偏差",
}

#: 需要填写原因与影响评估的性质：这两类不宜简单外推（准则要求考虑扩大范围或改变方法）。
_NATURE_REQUIRING_EXPLANATION = ("systematic", "human")


def build_conclusion_supplements(evaluation: dict) -> list[str]:
    """把 Wave 2 三项结构化评价渲染成结论补充说明（纯函数）。

    **为什么拼进 `conclusion` 而不加列**：这三项都是说明性内容，且 QC 与归档两个消费场景
    都是整行读出后渲染、不做按列过滤。加列会让迁移 V 号顺延、投影表列数膨胀，收益为零。

    每条带前缀标签，便于归档件与 QC finding 里定位来源。空结构一律跳过（不产生
    「未记录」之类的噪声文本 —— 缺失本身由 `evaluate_sampling_completeness` 判定）。
    """
    parts: list[str] = []

    disposition = evaluation.get("unchecked_disposition")
    if isinstance(disposition, dict) and disposition:
        by_mode: dict[str, int] = {}
        for item in disposition.values():
            if isinstance(item, dict):
                mode = str(item.get("mode") or "")
                if mode in _UNCHECKED_MODE_LABELS:
                    by_mode[mode] = by_mode.get(mode, 0) + 1
        if by_mode:
            detail = "、".join(
                f"{_UNCHECKED_MODE_LABELS[m]} {n} 笔" for m, n in sorted(by_mode.items())
            )
            parts.append(f"【未检查样本处置】{detail}")

    nature = evaluation.get("deviation_nature_summary")
    if isinstance(nature, dict) and nature:
        segs = []
        for key, label in _DEVIATION_NATURE_LABELS.items():
            item = nature.get(key)
            if isinstance(item, dict) and (item.get("count") or 0):
                segs.append(f"{label} {item.get('count')} 笔（{item.get('amount')} 元）")
        if segs:
            text = "、".join(segs)
            flagged = [
                _DEVIATION_NATURE_LABELS[k]
                for k in _NATURE_REQUIRING_EXPLANATION
                if (nature.get(k) or {}).get("count")
            ]
            if flagged:
                # 准则要求：这类偏差不宜简单外推，需考虑扩大范围或改变审计方法
                text += f"；存在{'、'.join(flagged)}，不宜简单外推"
            parts.append(f"【偏差性质】{text}")

    strata = evaluation.get("stratified_evaluation")
    if isinstance(strata, dict) and strata.get("enabled"):
        seg = (
            f"层内外推 {strata.get('projected_by_strata')} 元"
            f"（合并口径 {strata.get('projected_legacy')} 元）"
        )
        if strata.get("unclassified_count"):
            seg += f"；未归层样本 {strata.get('unclassified_count')} 笔"
        if strata.get("unsampled_strata_count"):
            seg += f"；未抽样层 {strata.get('unsampled_strata_count')} 个"
        if strata.get("fallback"):
            seg += "；层内评价异常已回退合并口径"
        parts.append(f"【分层评价】{seg}")

    reason = evaluation.get("reconcile_override_reason")
    if reason:
        parts.append(f"【总体完整性核对放行理由】{reason}")

    return parts


def build_record_fields(
    *,
    criteria: dict,
    total_matched: int | None,
    filled_count: int | None,
) -> dict[str, Any]:
    """把批次留痕投影为 `sampling_records` 的字段字典（纯函数）。"""
    evaluation = criteria.get("evaluation")
    ev = evaluation if isinstance(evaluation, dict) else {}
    coverage = criteria.get("coverage_stats")
    cov = coverage if isinstance(coverage, dict) else {}
    return {
        "sampling_purpose": build_sampling_purpose(criteria),
        "population_description": build_population_description(criteria),
        "population_total_amount": _as_decimal(cov.get("population_amount")),
        "population_total_count": _as_int(total_matched),
        "sample_size": int(filled_count or 0),
        "sampling_method_description": build_method_description(criteria),
        "sampling_method": (str(criteria.get("sampling_method")) or None) if criteria.get("sampling_method") else None,
        "random_seed": _as_int(criteria.get("random_seed")),
        "dataset_id": _as_uuid(criteria.get("dataset_id")),
        "deviations_found": _as_int(ev.get("deviation_count")),
        "misstatements_found": _as_decimal(ev.get("known_high_value")),
        "projected_misstatement": _as_decimal(ev.get("projected")),
        "upper_misstatement_limit": _as_decimal(ev.get("upper_limit")),
        "conclusion": _compose_conclusion(ev, criteria),
    }


def _compose_conclusion(ev: dict, criteria: dict) -> str | None:
    """结论正文 + Wave 2 三项结构化摘要（拼接，见 build_conclusion_supplements）。"""
    base = ev.get("conclusion_message") or criteria.get("conclusion")
    supplements = build_conclusion_supplements(ev)
    if not supplements:
        return base
    head = str(base) if base else ""
    return "\n".join([head, *supplements]) if head else "\n".join(supplements)


# ─── 写入：批次登记 ───────────────────────────────────────────────────────────


async def register_sampling_batch(
    db: AsyncSession,
    *,
    log: Any,
    created_by: UUID | None = None,
) -> UUID | None:
    """回填成功后写/更新一条 `sampling_records`（按 batch_id upsert）。

    fail-open：异常时 warning 后返回 None，不影响回填主流程。
    """
    try:
        criteria = log.extraction_criteria if isinstance(log.extraction_criteria, dict) else {}
        fields = build_record_fields(
            criteria=criteria,
            total_matched=getattr(log, "total_matched", None),
            filled_count=getattr(log, "filled_count", None),
        )
        batch_id = getattr(log, "batch_id", None)

        existing = None
        if batch_id is not None:
            existing = (
                await db.execute(
                    sa.select(SamplingRecord).where(
                        SamplingRecord.batch_id == batch_id,
                        SamplingRecord.is_deleted == sa.false(),
                    )
                )
            ).scalar_one_or_none()

        if existing is not None:
            for key, value in fields.items():
                setattr(existing, key, value)
            await db.flush()
            return existing.id

        record = SamplingRecord(
            project_id=log.project_id,
            working_paper_id=log.workpaper_id,
            batch_id=batch_id,
            created_by=created_by or getattr(log, "user_id", None),
            **fields,
        )
        db.add(record)
        await db.flush()
        return record.id
    except Exception:  # noqa: BLE001 — 投影失败不得阻断回填（但必须留 WARNING）
        logger.warning(
            "抽样批次登记失败（sampling_records 投影未写入，权威留痕不受影响）"
            " workpaper=%s batch=%s",
            getattr(log, "workpaper_id", None),
            getattr(log, "batch_id", None),
            exc_info=True,
        )
        return None


async def register_sampled_vouchers(
    db: AsyncSession,
    *,
    log: Any,
    year: int,
    sampling_record_id: UUID | None = None,
) -> int:
    """把本批次实际回填的凭证登记进 `sampled_vouchers`（项目级已抽凭证清单）。

    走 `ON CONFLICT DO NOTHING` 配 V139 的部分唯一索引
    `(project_id, year, voucher_no, working_paper_id, batch_id) WHERE NOT is_deleted`：
    同批次重复回填不增行；**不同 batch_id 的同一凭证允许共存** —— 那正是
    「该凭证被抽过两次」这一需要被发现的事实。

    fail-open：异常时 warning 后返回 0。
    """
    try:
        criteria = log.extraction_criteria if isinstance(log.extraction_criteria, dict) else {}
        voucher_nos = criteria.get("filled_voucher_nos") or []
        nos = [str(v).strip() for v in voucher_nos if str(v).strip()]
        if not nos:
            return 0

        filters = criteria.get("filters") if isinstance(criteria.get("filters"), dict) else {}
        codes = filters.get("account_codes") or []
        account_code = str(codes[0]) if codes else None
        batch_id = getattr(log, "batch_id", None)

        rows = [
            {
                "project_id": log.project_id,
                "year": year,
                "voucher_no": no,
                "account_code": account_code,
                "working_paper_id": log.workpaper_id,
                "sampling_record_id": sampling_record_id,
                "batch_id": batch_id,
                "sampled_by": getattr(log, "user_id", None),
                "note": build_sampling_purpose(criteria),
            }
            # 同一批次内去重（前端已去重，此处兜底防唯一索引报错路径）
            for no in dict.fromkeys(nos)
        ]

        stmt = pg_insert(SampledVoucher.__table__).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=[
                "project_id",
                "year",
                "voucher_no",
                "working_paper_id",
                "batch_id",
            ],
            index_where=sa.text("is_deleted = false"),
        )
        result = await db.execute(stmt)
        await db.flush()
        return int(result.rowcount or 0)
    except Exception:  # noqa: BLE001
        logger.warning(
            "已抽凭证登记失败（sampled_vouchers 投影未写入，权威留痕不受影响）"
            " workpaper=%s batch=%s",
            getattr(log, "workpaper_id", None),
            getattr(log, "batch_id", None),
            exc_info=True,
        )
        return 0


async def undo_sampling_registration(
    db: AsyncSession,
    *,
    batch_id: UUID | None,
) -> dict[str, int]:
    """撤销回填时软删该批次的两张投影行（R1）。

    **为什么必须做**：改造前 `voucher_undo` 只写 `workpaper_extraction_log.is_undone`，
    两张投影表原封不动。而投影已在产出真实数据（2026-08-05 实测 `sampled_vouchers` 21 行
    引擎登记），四个消费方全部被污染：

    - `project_level_extracted_voucher_nos` 仍返回已撤销批次的凭证号 ⇒ 审计师选「全项目
      排除」时那些凭证**再也抽不到**，且界面上看不出原因（不可见的选择偏差）
    - `cross_workpaper_duplicate_vouchers` 基于已撤销批次误报重复，逼审计师对不存在的
      重复做判断并留痕
    - `project_sampling_coverage` 把撤销批次算进 batch/sample 计数与 duplicated
    - 归档/QC 侧看到一条「已评价」的记录，而回填其实已撤销

    **为什么按 batch_id 而不是 workpaper_id**：同一底稿可以有多个批次（预审/年审、
    不同科目分别抽），按底稿宽删会连带删掉仍然有效的其它批次登记。

    **为什么软删而不是物理删**：撤销本身是需要留痕的审计动作；物理删会让「这批样本曾被
    抽取过又撤销」这一事实彻底消失。全部查询方均已带 `is_deleted == false` 条件。

    **撤销后重新回填不需要「复活」**（2026-08-05 实证）：`record_extraction_log` 的幂等
    去重只命中 `is_undone=false` 的 log，撤销后再次回填会新建 log 并生成**新的 uuid4
    batch_id** ⇒ V139 部分唯一索引下新行与软删旧行的 batch_id 不同、天然不冲突。

    fail-open：异常时 WARNING 后返回零计数，绝不让投影失败使审计师的撤销整体失败。

    Args:
        batch_id: 被撤销批次的 batch_id。为 None 时**零操作**（见上「为什么按 batch_id」）。

    Returns:
        `{"records": n, "vouchers": n}` 实际软删行数。
    """
    if batch_id is None:
        logger.warning(
            "撤销批次缺少 batch_id，跳过抽样登记投影撤销"
            "（不按 workpaper_id 宽删，避免误删同底稿其它批次）"
        )
        return {"records": 0, "vouchers": 0}
    try:
        rec_res = await db.execute(
            sa.update(SamplingRecord.__table__)
            .where(
                SamplingRecord.batch_id == batch_id,
                SamplingRecord.is_deleted == sa.false(),
            )
            .values(is_deleted=True)
        )
        vou_res = await db.execute(
            sa.update(SampledVoucher.__table__)
            .where(
                SampledVoucher.batch_id == batch_id,
                SampledVoucher.is_deleted == sa.false(),
            )
            .values(is_deleted=True)
        )
        await db.flush()
        return {
            "records": int(rec_res.rowcount or 0),
            "vouchers": int(vou_res.rowcount or 0),
        }
    except Exception:  # noqa: BLE001 — 投影撤销失败不得阻断审计师的撤销操作
        logger.warning(
            "抽样登记投影撤销失败（两张投影表未软删，权威留痕已标记撤销）batch=%s",
            batch_id,
            exc_info=True,
        )
        return {"records": 0, "vouchers": 0}


async def update_sampling_record_evaluation(
    db: AsyncSession,
    *,
    batch_id: UUID | None,
    evaluation: dict,
) -> bool:
    """把评价结果投影进 `sampling_records`（偏差/推断错报/UML/结论四项）。

    fail-open：异常时 warning 后返回 False。
    """
    if batch_id is None:
        return False
    try:
        record = (
            await db.execute(
                sa.select(SamplingRecord).where(
                    SamplingRecord.batch_id == batch_id,
                    SamplingRecord.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()
        if record is None:
            return False
        record.deviations_found = _as_int(evaluation.get("deviation_count"))
        record.misstatements_found = _as_decimal(evaluation.get("known_high_value"))
        record.projected_misstatement = _as_decimal(evaluation.get("projected"))
        record.upper_misstatement_limit = _as_decimal(evaluation.get("upper_limit"))
        # 与 build_record_fields 走同一拼接：否则每次评价更新都会把三项结构化摘要抹掉，
        # 而 `register_sampling_batch` 只在回填时跑一次 ⇒ 摘要永久丢失。
        composed = _compose_conclusion(evaluation, {})
        if composed:
            record.conclusion = composed
        await db.flush()
        return True
    except Exception:  # noqa: BLE001
        logger.warning(
            "抽样评价投影失败（sampling_records 未更新，权威留痕不受影响）batch=%s",
            batch_id,
            exc_info=True,
        )
        return False


async def resolve_project_year(db: AsyncSession, project_id: UUID) -> int | None:
    """反解项目审计年度（`sampled_vouchers.year` 必填，而回填载荷不带 year）。

    优先 `audit_year`；缺省回退审计期结束年份；两者皆缺返回 None
    （调用方按"无法判定"处理）。**禁用 `datetime.now().year` 兜底** ——
    跨年归档时会解析到错误年度，把样本登记到不存在的年度上。

    本函数是该解析的单一真源：`voucher_sampling._resolve_project_year` 委托到此。
    """
    from app.models.core import Project

    try:
        row = (
            await db.execute(
                sa.select(Project.audit_year, Project.audit_period_end).where(
                    Project.id == project_id
                )
            )
        ).one_or_none()
        if row is None:
            return None
        audit_year, period_end = row
        if audit_year is not None:
            return int(audit_year)
        if period_end is not None:
            return int(period_end.year)
    except Exception:  # noqa: BLE001
        logger.warning("项目审计年度反解失败 project=%s", project_id)
    return None


# ─── 查询：跨底稿排除 + 项目级概览 ───────────────────────────────────────────


async def project_level_extracted_voucher_nos(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> list[str]:
    """项目级已抽凭证号（R5.5：跨底稿排除的来源）。

    仅取抽凭引擎登记的行（`batch_id IS NOT NULL`）—— `ledger_penetration` 的穿透页
    手工标记不是「已执行抽凭程序」，不应据此排除。

    fail-open：查询失败返回空清单 + WARNING，不阻断抽样。判据有三条 ——
    ①本函数读的是**投影表**，权威留痕不依赖它；②`batch_id` 是 V139 新增列，未应用
    迁移的环境下这条查询会直接把整个 `/voucher-extract` 打成 500，审计师一选「全项目
    排除」就无法抽样；③降级为「不排除」不会让重复抽凭被掩盖 ——
    `cross_workpaper_duplicate_vouchers` 是独立且不受 `exclude_scope` 门控的检测，
    重复项仍会在预览前弹窗提示审计师（R8）。
    """
    try:
        rows = (
            await db.execute(
                sa.select(sa.distinct(SampledVoucher.voucher_no)).where(
                    SampledVoucher.project_id == project_id,
                    SampledVoucher.year == year,
                    SampledVoucher.is_deleted == sa.false(),
                    SampledVoucher.batch_id.isnot(None),
                )
            )
        ).scalars().all()
        return [r for r in rows if r]
    except Exception:  # noqa: BLE001 — 排除是增强，失败不得阻断抽样
        logger.warning(
            "项目级已抽凭证查询失败，本次不做跨底稿排除"
            "（重复项仍由 cross_workpaper_duplicate_vouchers 弹窗提示）"
            " project=%s year=%s",
            project_id,
            year,
            exc_info=True,
        )
        return []


async def cross_workpaper_duplicate_vouchers(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    voucher_nos: list[str],
    exclude_workpaper_id: UUID | None,
) -> list[dict[str, Any]]:
    """本次样本中已被**其它底稿**抽取登记过的凭证（R8.1，供前端弹窗让审计师判断）。

    重复抽同一张凭证有时是**有意的**（不同循环从不同认定角度检查同一笔交易），有时是
    **样本浪费**（覆盖率虚高）—— 这个判断必须交给审计师并留痕，不能由配置项静默决定。

    范围（R8.2 / R8.3）：
    - 排除当前底稿自身的登记（同一底稿内重复由 `exclude_extracted` 处理）
    - 只统计 `batch_id IS NOT NULL` 的行 —— `ledger_penetration` 穿透页的手工标记
      不是「已执行抽凭程序」，据它提示会产生大量噪声

    失败降级（R8.9）：返回空清单 + WARNING，绝不阻断抽样。

    Returns:
        `[{"voucher_no": str, "wp_codes": [str], "batch_count": int}]`，按凭证号排序。
    """
    nos = [str(v).strip() for v in (voucher_nos or []) if str(v).strip()]
    if not nos:
        return []
    try:
        from app.models.workpaper_models import WorkingPaper, WpIndex

        conds = [
            SampledVoucher.project_id == project_id,
            SampledVoucher.year == year,
            SampledVoucher.is_deleted == sa.false(),
            SampledVoucher.batch_id.isnot(None),
            SampledVoucher.voucher_no.in_(nos),
        ]
        if exclude_workpaper_id is not None:
            # 排除当前底稿；NULL working_paper_id 的登记行也保留（来源未知的引擎登记，
            # 仍属"别处抽过"的事实）
            conds.append(
                sa.or_(
                    SampledVoucher.working_paper_id.is_(None),
                    SampledVoucher.working_paper_id != exclude_workpaper_id,
                )
            )

        # wp_code 在 wp_index（working_paper 表无该列，须 JOIN）
        stmt = (
            sa.select(
                SampledVoucher.voucher_no,
                WpIndex.wp_code,
                SampledVoucher.batch_id,
            )
            .select_from(SampledVoucher)
            .join(
                WorkingPaper,
                WorkingPaper.id == SampledVoucher.working_paper_id,
                isouter=True,
            )
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id, isouter=True)
            .where(*conds)
        )
        rows = (await db.execute(stmt)).all()
        if not rows:
            return []

        grouped: dict[str, dict[str, Any]] = {}
        for voucher_no, wp_code, batch_id in rows:
            entry = grouped.setdefault(
                voucher_no, {"wp_codes": set(), "batches": set()}
            )
            if wp_code:
                entry["wp_codes"].add(str(wp_code))
            if batch_id is not None:
                entry["batches"].add(str(batch_id))

        return [
            {
                "voucher_no": no,
                "wp_codes": sorted(data["wp_codes"]),
                "batch_count": len(data["batches"]),
            }
            for no, data in sorted(grouped.items())
        ]
    except Exception:  # noqa: BLE001 — 检测是增强，失败不得阻断抽样
        logger.warning(
            "跨底稿重复抽凭检测失败，本次不提示（project=%s year=%s wp=%s）",
            project_id,
            year,
            exclude_workpaper_id,
            exc_info=True,
        )
        return []


async def project_sampling_coverage(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> dict[str, Any]:
    """项目级抽样登记概览（R5.6）。

    - by_workpaper：按底稿汇总批次数 / 样本数
    - duplicated：被 ≥2 个底稿抽取的凭证（跨循环重复抽凭，此前项目层面发现不了）
    """
    by_wp_rows = (
        await db.execute(
            sa.select(
                SamplingRecord.working_paper_id,
                sa.func.count(sa.distinct(SamplingRecord.batch_id)).label("batch_count"),
                sa.func.coalesce(sa.func.sum(SamplingRecord.sample_size), 0).label("sample_count"),
            )
            .where(
                SamplingRecord.project_id == project_id,
                SamplingRecord.is_deleted == sa.false(),
            )
            .group_by(SamplingRecord.working_paper_id)
        )
    ).all()

    dup_rows = (
        await db.execute(
            sa.select(
                SampledVoucher.voucher_no,
                sa.func.count(sa.distinct(SampledVoucher.working_paper_id)).label("wp_count"),
            )
            .where(
                SampledVoucher.project_id == project_id,
                SampledVoucher.year == year,
                SampledVoucher.is_deleted == sa.false(),
                SampledVoucher.batch_id.isnot(None),
            )
            .group_by(SampledVoucher.voucher_no)
            .having(sa.func.count(sa.distinct(SampledVoucher.working_paper_id)) >= 2)
            .order_by(sa.func.count(sa.distinct(SampledVoucher.working_paper_id)).desc())
            .limit(500)
        )
    ).all()

    return {
        "by_workpaper": [
            {
                "working_paper_id": str(r.working_paper_id) if r.working_paper_id else None,
                "batch_count": int(r.batch_count or 0),
                "sample_count": int(r.sample_count or 0),
            }
            for r in by_wp_rows
        ],
        "duplicated": [
            {"voucher_no": r.voucher_no, "workpaper_count": int(r.wp_count or 0)}
            for r in dup_rows
        ],
    }
