"""公式引用是否存在 —— 按项目、年度、口径判定（spec formula-fetch-followup-defect-closure R5.2）。

地址库校验（``AddressRegistryService.validate_formula_refs``，各处保存前校验都走它）与 ACNR 单引用解析
（``full_resolve`` 的非底稿域）共用本模块，判定口径与求值一致：

* TB / SUM_TB / 两参 PREV：本年试算表有该码或其下级科目（前缀，与 ``formula_preloader._load_tb`` 同口径；区间按起止前缀），
  且列名已注册（``COLUMN_ALIASES``）。原先地址目录只认精确码 ⇒ 写一级科目码（求值按前缀合计、能取到数）保存时判悬空。
* ROW / SUM_ROW / REPORT：本项目适用准则的有效报表配置（含项目层，``load_effective_report_configs``）有该行；
  SUM_ROW 区间内至少一行；REPORT 的期间能识别（``period_kind``）。原先登记全部准则的全部行 ⇒ 别的准则才有的行也判存在。
* NOTE：本年度附注有该章节，且按严格求值同一套匹配（``formula_ref_preload.note_locate``：主表优先、合计行兜底、
  列名 / 期间语义）能定位到行与列 —— 只看结构，不要求单元格有值；本年度附注一节都没有（尚未生成）时按附注模板
  （章节 + 行名 + 表头）。原先只登记模板「合计」行 ⇒ 引用其他行一律判悬空，而附注已生成的章节反倒不看。
* AUX / WP / 三参 PREV：不在本模块（调用方沿用现有判定）。

请求内缓存：一个实例对同一项目年度只读一次试算表科目、报表配置、附注章节清单，每个附注章节只读一次。
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_ref_preload import (
    NOTE_RE,
    PREV_RE,
    PREV_TB_RE,
    REPORT_RE,
    ROW_RE,
    SUM_ROW_RE,
    _Q,
    _START,
    _note_table_data,
    note_locate,
    note_section_hint,
    note_section_missing,
    period_kind,
)

TB_RE = re.compile(_START + r"TB\(" + _Q + "," + _Q + r"\)")
SUM_TB_RE = re.compile(_START + r"SUM_TB\(" + _Q + "," + _Q + r"\)")

#: 本模块判定的函数 → 单引用写法（整串匹配）。PREV(TB(…)) 先于两参 PREV
_SINGLE: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PREV", PREV_TB_RE), ("PREV", PREV_RE), ("SUM_TB", SUM_TB_RE), ("TB", TB_RE),
    ("SUM_ROW", SUM_ROW_RE), ("ROW", ROW_RE), ("REPORT", REPORT_RE), ("NOTE", NOTE_RE),
)
CHECKED_FUNCS: frozenset[str] = frozenset(fn for fn, _ in _SINGLE)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass(frozen=True)
class RefVerdict:
    """一个引用的判定：``exists`` 为假时 ``reason`` 写明取不到的原因（与求值缺数同一说法）。"""

    exists: bool
    reason: str = ""


def parse_checked_ref(text: str) -> tuple[str, tuple[str, ...]] | None:
    """整串是本模块判定的单个引用 ⇒ ``(函数, 参数)``；否则 ``None``（复合表达式、AUX / WP / 三参 PREV、写法不全）。"""
    s = (text or "").strip()
    for fn, pattern in _SINGLE:
        m = pattern.fullmatch(s)
        if m:
            return fn, tuple(g for g in m.groups() if g is not None)
    return None


async def project_ref_scope(db: AsyncSession, project_id: Any) -> tuple[int, str]:
    """引用按项目取数的（审计年度, 附注口径）。

    年度经单一真源 ``resolve_project_year``（``audit_year`` → 审计期末年份），都没有时为 0（不猜今年）；口径读项目
    基本信息的 ``template_type``，非 soe / listed 按 soe（与前端 ``normalizeTemplateType`` 同口径）。只读：不经
    ``DisclosureEngine._get_active_template_type``（它会回填自定义模板快照并 flush）。
    """
    from app.models.core import Project
    from app.services.disclosure_engine import _extract_basic_info
    from app.services.note_section_catalog import normalize_template_type
    from app.services.sampling_registry_service import resolve_project_year

    pid = uuid.UUID(str(project_id))
    year = await resolve_project_year(db, pid)
    wizard_state = (
        await db.execute(sa.select(Project.wizard_state).where(Project.id == pid))
    ).scalar_one_or_none()
    template_type = _extract_basic_info(wizard_state if isinstance(wizard_state, dict) else None).get("template_type")
    return int(year or 0), normalize_template_type(template_type if isinstance(template_type, str) else None)


def _template_table_data(section: dict) -> dict | None:
    """附注模板一节 → 与 ``disclosure_notes.table_data`` 同形（主表 + ``_tables``）；行的合计标记两种写法都认。"""
    tables = [t for t in section.get("tables") or [] if isinstance(t, dict)]
    if not tables and isinstance(section.get("table_template"), dict):
        tables = [section["table_template"]]
    if not tables:
        return None

    def rows(table: dict) -> list[dict]:
        return [{"label": r.get("label"), "is_total": bool(r.get("is_total")) or r.get("row_type") == "total"}
                for r in table.get("rows") or [] if isinstance(r, dict)]

    shaped = [{"name": t.get("name") or "", "headers": t.get("headers"), "rows": rows(t)} for t in tables]
    return {**shaped[0], "_tables": shaped}


class FormulaRefChecker:
    """按项目、年度、口径判定单个引用是否存在（只读；读库失败照常抛出，由调用方决定是否降级）。"""

    def __init__(self, db: AsyncSession, project_id: Any, year: int, template_type: str = "soe") -> None:
        from app.services.note_section_catalog import normalize_template_type

        self.db = db
        try:
            self.project_id: uuid.UUID | None = uuid.UUID(str(project_id))
        except ValueError:
            self.project_id = None  # 不是项目编号：一律判不存在（不拿它查库）
        self._raw_project_id = project_id
        self.year = int(year or 0)
        self.template_type = normalize_template_type(template_type)
        self._tb_codes: list[str] | None = None
        self._report_codes: set[str] | None = None
        self._standard = ""
        self._note_sections: set[str] | None = None
        self._notes: dict[str, tuple[bool, Any]] = {}
        self._template: dict[str, dict] | None = None

    async def check(self, text: str) -> RefVerdict | None:
        """单个引用文本 → 判定；不属于本模块的写法返回 ``None``。"""
        parsed = parse_checked_ref(text)
        if parsed is None:
            return None
        if self.project_id is None:
            return RefVerdict(False, f"项目编号「{self._raw_project_id}」无效，无法确认引用是否存在")
        fn, args = parsed
        if fn in ("TB", "SUM_TB", "PREV"):
            return await self._check_tb(args[0].strip(), args[1].strip())
        if fn == "NOTE":
            return await self._check_note(args[0].strip(), args[1], args[2] if len(args) > 2 else "")
        if fn == "REPORT" and len(args) > 1 and period_kind(args[1]) is None:
            return RefVerdict(False, f"期间「{args[1]}」无法识别（本期写 期末 / 本期 / 本年，上期写 期初 / 上期 / 上年）")
        start = args[0].strip()
        end = args[1].strip() if fn == "SUM_ROW" else start
        return await self._check_rows(start, end, fn == "SUM_ROW")

    # ── 试算表 ──

    async def _check_tb(self, code: str, column: str) -> RefVerdict:
        from app.services.formula_engine import COLUMN_ALIASES

        if COLUMN_ALIASES.get(column) is None:
            return RefVerdict(False, f"列名「{column}」无法识别")
        codes = await self._load_tb_codes()
        if code.count("~") == 1:
            start, end = (p.strip() for p in code.split("~", 1))
            hit = bool(start) and any(start <= c[:len(start)] <= end for c in codes)
        else:
            hit = bool(code) and any(c.startswith(code) for c in codes)
        if hit:
            return RefVerdict(True)
        if not codes:
            return RefVerdict(False, f"本年度（{self.year}）试算表没有数据")
        return RefVerdict(False, f"本年度（{self.year}）试算表没有科目 {code} 及其下级科目")

    async def _load_tb_codes(self) -> list[str]:
        if self._tb_codes is None:
            from app.models.audit_platform_models import TrialBalance

            rows = (await self.db.execute(sa.select(TrialBalance.standard_account_code).where(
                TrialBalance.project_id == self.project_id, TrialBalance.year == self.year,
                TrialBalance.is_deleted == sa.false()))).scalars().all()
            self._tb_codes = sorted({c for c in rows if c})
        return self._tb_codes

    # ── 报表 ──

    async def _check_rows(self, start: str, end: str, is_range: bool) -> RefVerdict:
        codes = await self._load_report_codes()
        if (any(start <= c <= end for c in codes) if is_range else start in codes):
            return RefVerdict(True)
        where = f"本项目适用的报表（{self._standard}）"
        if is_range:
            return RefVerdict(False, f"{where}在行次 {start}~{end} 之间没有行")
        return RefVerdict(False, f"{where}没有行次 {start}")

    async def _load_report_codes(self) -> set[str]:
        if self._report_codes is None:
            from app.services.formula_settings.effective_report import load_effective_report_configs
            from app.services.report_config_service import ReportConfigService

            self._standard = await ReportConfigService.resolve_applicable_standard(self.db, self.project_id)
            rows = await load_effective_report_configs(self.db, standard=self._standard, project_id=self.project_id)
            self._report_codes = {r.row_code for r in rows if r.row_code}
        return self._report_codes

    # ── 附注 ──

    async def check_note_section(self, section: str) -> RefVerdict:
        """章节级引用（索引 ``Note:五、3``）：本年度附注有该章节；尚未生成时看附注模板。"""
        if self.project_id is None:
            return RefVerdict(False, f"项目编号「{self._raw_project_id}」无效，无法确认引用是否存在")
        section = (section or "").strip()
        sections = await self._load_note_sections()
        if sections:
            return RefVerdict(True) if section in sections else \
                RefVerdict(False, note_section_missing(self.year, section))
        if section in self._load_template():
            return RefVerdict(True)
        return RefVerdict(False, self._template_missing(section))

    def _template_missing(self, section: str) -> str:
        return (f"本年度（{self.year}）附注尚未生成，附注模板（{self.template_type}）也没有章节 {section}"
                f"{note_section_hint(section)}")

    async def _check_note(self, section: str, label: str, column: str) -> RefVerdict:
        sections = await self._load_note_sections()
        if sections:
            if section not in sections:
                return RefVerdict(False, note_section_missing(self.year, section))
            if section not in self._notes:
                self._notes[section] = await _note_table_data(self.db, self.project_id, self.year, section)
            _, table_data = self._notes[section]
            _row, _idx, _headers, reason = note_locate(table_data, section, label, column, require_values=False)
            return RefVerdict(not reason, reason)
        template = self._load_template().get(section)
        if template is None:
            return RefVerdict(False, self._template_missing(section))
        table_data = _template_table_data(template)
        if table_data is None:
            return RefVerdict(False, f"本年度（{self.year}）附注尚未生成，附注模板章节 {section} 没有表格")
        _row, _idx, _headers, reason = note_locate(table_data, section, label, column, require_values=False)
        return RefVerdict(not reason, reason and f"{reason}（本年度附注尚未生成，按附注模板判定）")

    async def _load_note_sections(self) -> set[str]:
        if self._note_sections is None:
            from app.models.report_models import DisclosureNote

            rows = (await self.db.execute(sa.select(DisclosureNote.note_section).where(
                DisclosureNote.project_id == self.project_id, DisclosureNote.year == self.year,
                DisclosureNote.is_deleted == sa.false()))).scalars().all()
            self._note_sections = {s for s in rows if s}
        return self._note_sections

    def _load_template(self) -> dict[str, dict]:
        if self._template is None:
            path = _DATA_DIR / f"note_template_{self.template_type}.json"
            raw = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
            sections = raw.get("sections", []) if isinstance(raw, dict) else raw
            self._template = {str(s.get("section_number") or "").strip(): s for s in sections
                              if isinstance(s, dict) and s.get("section_number")}
        return self._template
