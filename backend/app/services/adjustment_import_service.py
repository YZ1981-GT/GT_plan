"""调整分录 Excel 导入：行 → 分录组 → 预检 / 导入（spec adjustment-hall-entry-review-closure 需求 2）。

旧通用导入端点（``routers/import_templates._import_adjustments``，薄壳）与项目级导入端点
（``routers/adjustment_import``）共用本模块。规则：

- 同编号多行合并为一笔（文件中不连续也合并）；
- 未填编号的连续行累计，借贷合计相等且大于 0 时切出一笔；遇到有编号的行或文件结束时，
  未闭合的累计组单独成一笔（导入时报不平衡）。原先每个无编号行各自成组 ⇒ 多行分录必失败；
- 类型取组内非空值，只能是 AJE / RJE（原先非法值静默按 AJE）；摘要取组内首个非空值；
- 金额去千分位与货币符号后按分舍入；无法识别 ⇒ 行级错误（原先静默按 0）；借贷都为 0 且无科目
  的空白行跳过，有科目但借贷都为 0 的行忽略并给出提示；
- 科目解析沿用原逻辑：一级码 > 二级码归一一级 > 名称反查（客户科目名称优先）；
- 预检不写库；导入逐笔 SAVEPOINT，覆盖模式「删旧 + 建新 + 钉编号」在同一保存点内。
行校验（负数、同行双向、平衡、非零）由 ``AdjustmentService.create_entry`` 调 ``entry_rule_errors``
执行，预检调同一函数，两边口径一致。
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.adjustment_entry_rules import entry_rule_errors, to_cents

logger = logging.getLogger(__name__)

_CURRENCY_CHARS = (",", "，", "¥", "￥", "$", " ")


def parse_amount(value: Any) -> Decimal:
    """单元格金额 → 按分舍入的 Decimal；空为 0；无法识别抛 ValueError。"""
    if value is None:
        return Decimal("0.00")
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return to_cents(value)
    text = str(value).strip()
    for ch in _CURRENCY_CHARS:
        text = text.replace(ch, "")
    return to_cents(text or None)


@dataclass
class ImportLine:
    row_idx: int          # 行号（有位置信息时为 Excel 行号，否则为解析后数据行序号）
    label: str            # 展示用：「AJE模板 第 5 行」/「第 3 行」
    code: str             # 解析出的标准（一级）科目码
    detail_code: str | None
    raw_code: str
    name: str
    debit: Decimal
    credit: Decimal

    # entry_rule_errors 读这三个属性
    @property
    def standard_account_code(self) -> str:
        return self.code

    @property
    def debit_amount(self) -> Decimal:
        return self.debit

    @property
    def credit_amount(self) -> Decimal:
        return self.credit


@dataclass
class ImportGroup:
    key: str                                  # 文件编号，或无编号自动分组的 "__auto_N"
    lines: list[ImportLine] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    description: str = ""
    pre_errors: list[str] = field(default_factory=list)  # 类型 / 金额解析错误（不进 create_entry）

    @property
    def numbered(self) -> bool:
        return not self.key.startswith("__auto_")

    @property
    def display_no(self) -> str:
        return self.key if self.numbered else "(无编号)"

    @property
    def adj_type(self) -> str:
        valid = [t for t in self.types if t in ("AJE", "RJE")]
        return valid[0] if valid else "AJE"

    def balanced_nonzero(self) -> bool:
        debit = sum((ln.debit for ln in self.lines), Decimal("0"))
        credit = sum((ln.credit for ln in self.lines), Decimal("0"))
        return not self.pre_errors and debit == credit and debit > 0

    def finalize(self) -> None:
        """组内类型一致性检查（全部行加入后调用）。"""
        bad = sorted({t for t in self.types if t not in ("AJE", "RJE")})
        if bad:
            self.pre_errors.append(f"类型「{'、'.join(bad)}」无效，只能是 AJE 或 RJE")
        elif not self.types:
            self.pre_errors.append("未填写类型（AJE 或 RJE）")
        elif len(set(self.types)) > 1:
            self.pre_errors.append("同一笔分录的类型不一致（AJE / RJE 混填）")


class AccountResolver:
    """本项目科目解析（一次装载科目表与映射；查询顺序 AccountChart → AccountMapping 不变）。"""

    def __init__(self, valid_codes: set[str], name_to_code: dict[str, str], client_to_std: dict[str, str]):
        self.valid_codes = valid_codes
        self.name_to_code = name_to_code
        self.client_to_std = client_to_std

    @classmethod
    async def load(cls, db: AsyncSession, project_id: UUID) -> "AccountResolver":
        from app.models.audit_platform_models import AccountChart, AccountMapping, AccountSource

        chart = (await db.execute(
            sa.select(AccountChart.account_code, AccountChart.account_name, AccountChart.source).where(
                AccountChart.project_id == project_id, AccountChart.is_deleted == False,  # noqa: E712
            )
        )).all()
        valid_codes: set[str] = set()
        name_to_code: dict[str, str] = {}
        for code, name, source in chart:
            if not code:
                continue
            if source == AccountSource.standard:
                valid_codes.add(code)
                if name:
                    name_to_code.setdefault(name, code)
            elif name:
                name_to_code[name] = code  # 客户科目名称优先（模板下拉里看到的就是它）
        mapping = (await db.execute(
            sa.select(AccountMapping.original_account_code, AccountMapping.standard_account_code).where(
                AccountMapping.project_id == project_id, AccountMapping.is_deleted == False,  # noqa: E712
            )
        )).all()
        return cls(valid_codes, name_to_code, {r[0]: r[1] for r in mapping if r[1]})

    @staticmethod
    def _first4(code: str) -> str:
        clean = code.strip()
        for sep in (".", "-", "/", "_", "\\", " "):
            clean = clean.split(sep)[0]
        return clean[:4] if len(clean) >= 4 else clean

    def _normalize_to_level1(self, code: str) -> str:
        """归一到一级编码: 1122.01 → 1122（查映射）；1231-01 保留；否则取前 4 位。"""
        if not code:
            return ""
        if code.startswith("1231-"):
            return code
        if code in self.client_to_std:
            return self.client_to_std[code]
        if code in self.valid_codes:
            return code
        return self._first4(code)

    def _resolve_code(self, code_val: str, name_val: str) -> str:
        if code_val and code_val in self.valid_codes:
            return code_val
        if name_val and name_val in self.name_to_code:
            level1 = self._normalize_to_level1(self.name_to_code[name_val])
            return level1 if level1 in self.valid_codes else self.name_to_code[name_val]
        if code_val:
            level1 = self._normalize_to_level1(code_val)
            if level1 in self.valid_codes:
                return level1
        return code_val or ""

    def resolve(self, sub_code: str, sub_name: str, level1_code: str) -> tuple[str, str | None]:
        """返回 (标准科目码, 明细科目码)；明细码与标准码相同时为 None（不冗余存）。"""
        if level1_code and level1_code in self.valid_codes:
            std_code = level1_code
        elif sub_code:
            std_code = self._resolve_code(sub_code, sub_name)
            if std_code and std_code not in self.valid_codes and self._first4(std_code) in self.valid_codes:
                std_code = self._first4(std_code)
        elif sub_name:
            std_code = self._resolve_code("", sub_name)
        else:
            std_code = ""
        # 明细码：用户填的二级编码优先，否则用二级名称反查出的原始码（可能是客户二级码）
        if sub_code:
            detail = sub_code
        else:
            detail = self.name_to_code.get(sub_name, "") if sub_name else ""
        return std_code, (detail if detail and detail != std_code else None)


def _row_fields(row: dict) -> tuple[str, str, str, str, str, str, Any, Any]:
    adj_no = str(row.get("编号", "") or row.get("分录编号", "") or "").strip()
    adj_type = str(row.get("类型", "") or row.get("调整类型", "") or "").strip().upper()
    desc = str(row.get("摘要", "") or "").strip()
    sub_name = str(
        row.get("二级科目名称", "") or row.get("科目名称", "")
        or row.get("借方科目名称", "") or row.get("贷方科目名称", "") or ""
    ).strip()
    sub_code = str(
        row.get("二级科目编码", "") or row.get("科目编码", "")
        or row.get("借方科目代码", "") or row.get("贷方科目代码", "") or ""
    ).strip()
    level1_code = str(row.get("一级科目编码", "") or "").strip()
    return adj_no, adj_type, desc, sub_name, sub_code, level1_code, row.get("借方金额"), row.get("贷方金额")


def build_import_groups(
    rows: Sequence[dict],
    resolver: AccountResolver,
    locations: Sequence[tuple[str, int]] | None = None,
) -> tuple[list[ImportGroup], list[str]]:
    """解析行 → 分录组（规则见模块说明）。返回 (分录组, 提示)。"""
    from app.services.import_template_service import infer_adjustment_type_from_sheet_name

    groups: dict[str, ImportGroup] = {}
    warnings: list[str] = []
    auto_n = 0
    running: ImportGroup | None = None
    for idx, row in enumerate(rows, 1):
        sheet, excel_row = (locations[idx - 1] if locations and idx - 1 < len(locations) else ("", idx))
        label = f"{sheet} 第 {excel_row} 行" if sheet else f"第 {excel_row} 行"
        adj_no, adj_type, desc, sub_name, sub_code, level1_code, raw_debit, raw_credit = _row_fields(row)
        amount_errors: list[str] = []
        try:
            debit = parse_amount(raw_debit)
        except ValueError:
            debit, amount_errors = Decimal("0"), [f"{label}借方金额无法识别：{raw_debit}"]
        try:
            credit = parse_amount(raw_credit)
        except ValueError:
            credit = Decimal("0")
            amount_errors.append(f"{label}贷方金额无法识别：{raw_credit}")
        has_account = bool(sub_name or sub_code or level1_code)
        if not amount_errors and debit == 0 and credit == 0:
            if has_account:
                warnings.append(f"{label}借贷金额均为 0，已忽略")
            continue  # 完全空行（无科目且借贷均 0）直接跳过
        if not adj_type and sheet:
            adj_type = infer_adjustment_type_from_sheet_name(sheet) or ""
        std_code, detail_code = resolver.resolve(sub_code, sub_name, level1_code)
        line = ImportLine(
            row_idx=excel_row, label=label, code=std_code, detail_code=detail_code,
            raw_code=sub_code or level1_code, name=sub_name, debit=debit, credit=credit,
        )
        if adj_no:
            running = None  # 有编号的行打断无编号行的累计
            group = groups.setdefault(adj_no, ImportGroup(key=adj_no))
        else:
            if running is None:
                auto_n += 1
                running = groups.setdefault(f"__auto_{auto_n}", ImportGroup(key=f"__auto_{auto_n}"))
            group = running
        group.lines.append(line)
        group.pre_errors.extend(amount_errors)
        if adj_type:
            group.types.append(adj_type)
        if desc and not group.description:
            group.description = desc
        if group is running and running.balanced_nonzero():
            running = None  # 无编号累计组借贷平衡 ⇒ 切出一笔
    for group in groups.values():
        group.finalize()
    return list(groups.values()), warnings


def group_errors(group: ImportGroup, resolver: AccountResolver) -> list[str]:
    """预检：一笔分录的全部问题（类型 / 金额解析 / 科目找不到 / 行规则）。"""
    errors = list(group.pre_errors)
    unresolved: set[str] = set()
    for ln in group.lines:
        # 填了科目却解析不出（或解析出的码不在本项目）⇒ 指明「找不到」，不再报笼统的「未选择科目」
        if (ln.name or ln.raw_code) and (not ln.code or ln.code not in resolver.valid_codes):
            unresolved.add(f"{ln.label}未选择科目")
            errors.append(f"{ln.label}科目「{ln.name or ln.raw_code}」在项目科目库中找不到")
    rule_errors = entry_rule_errors(group.lines, row_labels=[ln.label for ln in group.lines])
    errors += [e for e in rule_errors if e not in unresolved]
    return list(dict.fromkeys(errors))


def friendly_error(group: ImportGroup, resolver: AccountResolver, base_error: str) -> str:
    """导入失败时的提示：有找不到的科目就指明行与科目，否则沿用原错误。"""
    unmatched = [ln for ln in group.lines if not ln.code or ln.code not in resolver.valid_codes]
    if not unmatched:
        return base_error
    details = []
    for ln in unmatched[:3]:
        hint = f"二级名称='{ln.name}'" if ln.name else f"编码='{ln.raw_code}'"
        details.append(f"{ln.label} {hint} 在项目科目库中找不到")
    msg = ";  ".join(details)
    if len(unmatched) > 3:
        msg += f";  共 {len(unmatched)} 行有此问题"
    return f"{msg}。请打开模板【项目科目库】sheet 查找正确的二级科目名称,或先在 [试算表 → 映射规则] 完善映射"


async def _overwrite_action(db: AsyncSession, project_id: UUID, year: int, adj_no: str) -> tuple[str, str | None, Any]:
    """覆盖模式按文件编号判定：(create | replace | skip, 跳过原因, 被替换的分录组 id)。"""
    from app.models.audit_platform_models import Adjustment, ReviewStatus
    from app.services.adjustment_collaboration_service import has_active_collaboration

    existing = list((await db.execute(
        sa.select(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_no == adj_no,
            Adjustment.is_deleted == False,  # noqa: E712
        )
    )).scalars().all())
    if not existing:
        return "create", None, None
    head = existing[0]
    if head.review_status == ReviewStatus.approved:
        return "skip", "该编号已在集中登记复核通过（approved），需先撤回复核方可覆盖", None
    if head.review_status == ReviewStatus.pending_review:
        return "skip", "该编号已提交复核（待复核），需先撤回提交方可覆盖", None
    if await has_active_collaboration(db, project_id, head.entry_group_id):
        return "skip", "该编号存在进行中的协作补充，需待协作确认/退回后方可覆盖", None
    if (head.origin or "manual") == "workpaper":
        return "skip", "该编号来自底稿同步（origin=workpaper），请在来源底稿修改后重新同步", None
    return "replace", None, head.entry_group_id


async def preview_import(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    rows: Sequence[dict],
    *,
    mode: str = "append",
    locations: Sequence[tuple[str, int]] | None = None,
) -> dict:
    """预检：逐笔给出解析结果与问题，不写库。"""
    resolver = await AccountResolver.load(db, project_id)
    groups, warnings = build_import_groups(rows, resolver, locations)
    if not resolver.valid_codes:
        warnings.insert(0, "本项目还没有标准科目，请先在【试算表 → 科目映射】完成科目映射后再导入")
    items: list[dict] = []
    counts = {"total": 0, "ok": 0, "error": 0, "skip": 0, "replace": 0}
    for g in groups:
        errors = group_errors(g, resolver)
        action, skip_reason = "create", None
        if mode == "overwrite" and g.numbered:
            action, skip_reason, _ = await _overwrite_action(db, project_id, year, g.key)
        items.append({
            "key": g.key,
            "adjustment_no": g.display_no,
            "adjustment_type": g.adj_type,
            "description": g.description,
            "rows": [ln.row_idx for ln in g.lines],
            "lines": [
                {"label": ln.label, "account_code": ln.code, "account_name": ln.name,
                 "detail_account_code": ln.detail_code, "debit": str(ln.debit), "credit": str(ln.credit)}
                for ln in g.lines
            ],
            "total_debit": str(sum((ln.debit for ln in g.lines), Decimal("0"))),
            "total_credit": str(sum((ln.credit for ln in g.lines), Decimal("0"))),
            "action": action,
            "skip_reason": skip_reason,
            "errors": errors,
            "ok": not errors and action != "skip",
        })
        counts["total"] += 1
        if action == "skip":
            counts["skip"] += 1
        elif errors:
            counts["error"] += 1
        else:
            counts["ok"] += 1
            if action == "replace":
                counts["replace"] += 1
    return {"mode": mode, "groups": items, "warnings": warnings, "summary": counts}


async def import_rows(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    rows: Sequence[dict],
    user: Any,
    *,
    mode: str = "append",
    locations: Sequence[tuple[str, int]] | None = None,
) -> dict:
    """导入：逐笔 SAVEPOINT。返回 {imported, skipped, failed, failed_rows[, skipped_rows], created, warnings}。"""
    from app.models.audit_platform_models import Adjustment, AdjustmentType
    from app.models.audit_platform_schemas import AdjustmentCreate, AdjustmentLineItem
    from app.services import adjustment_service as adj_mod

    mode_norm = str(mode or "append").strip().lower()
    if mode_norm not in ("append", "overwrite"):
        logger.warning("调整分录导入收到非法 mode=%r，降级为 append", mode)
        mode_norm = "append"
    svc = adj_mod.AdjustmentService(db)  # 运行时取，测试可替换
    resolver = await AccountResolver.load(db, project_id)
    groups, warnings = build_import_groups(rows, resolver, locations)

    imported, failed, skipped = 0, 0, 0
    failed_rows: list[dict] = []
    skipped_rows: list[dict] = []
    created: list[dict] = []
    for g in groups:
        row_idxs = [ln.row_idx for ln in g.lines]
        if g.pre_errors:
            failed += 1
            failed_rows.append({"row": row_idxs[0] if row_idxs else 0, "adj_no": g.display_no,
                                "rows_in_group": row_idxs, "error": "；".join(g.pre_errors)})
            continue
        keyed = mode_norm == "overwrite" and g.numbered
        action, reason, replace_group_id = ("create", None, None)
        if keyed:
            action, reason, replace_group_id = await _overwrite_action(db, project_id, year, g.key)
            if action == "skip":
                skipped += 1
                skipped_rows.append({"row": row_idxs[0] if row_idxs else 0, "adj_no": g.key,
                                     "rows_in_group": row_idxs, "reason": reason})
                continue
        try:
            async with db.begin_nested():
                if action == "replace":
                    # 复用既有删除路径（软删 + 发 ADJUSTMENT_DELETED）；失败随保存点回滚，旧分录保留
                    await svc.delete_entry(project_id, replace_group_id)
                data = AdjustmentCreate(
                    adjustment_type=AdjustmentType(g.adj_type.lower()),
                    year=year,
                    description=g.description or "",
                    line_items=[
                        AdjustmentLineItem(
                            standard_account_code=line.code,
                            detail_account_code=line.detail_code,
                            account_name=line.name or None,
                            debit_amount=line.debit,
                            credit_amount=line.credit,
                        )
                        for line in g.lines
                    ],
                )
                result = await svc.create_entry(project_id, data, user.id)
                if keyed:
                    # 覆盖模式把编号钉为文件编号，使重复导入同一文件 by-key 幂等
                    await db.execute(
                        sa.update(Adjustment)
                        .where(Adjustment.entry_group_id == result.entry_group_id, Adjustment.is_deleted == False)  # noqa: E712
                        .values(adjustment_no=g.key)
                        .execution_options(synchronize_session=False)
                    )
                    await db.flush()
            imported += 1
            created.append({"key": g.key, "entry_group_id": str(getattr(result, "entry_group_id", "") or ""),
                            "adjustment_no": g.key if keyed else getattr(result, "adjustment_no", None)})
        except Exception as exc:  # noqa: BLE001 — 单笔失败计入结果，其余继续
            failed += 1
            failed_rows.append({"row": row_idxs[0] if row_idxs else 0, "adj_no": g.display_no,
                                "rows_in_group": row_idxs, "error": friendly_error(g, resolver, str(exc))})
            logger.warning("调整分录导入分录组 %s 失败: %s", g.key, exc)

    out: dict = {"imported": imported, "skipped": skipped, "failed": failed, "failed_rows": failed_rows}
    if skipped_rows:
        out["skipped_rows"] = skipped_rows
    out["created"] = created
    out["warnings"] = warnings
    return out
