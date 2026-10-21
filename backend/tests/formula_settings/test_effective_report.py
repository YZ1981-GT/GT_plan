"""报表有效配置（R1.1 / R1.2）：项目行替换、停用、项目独有行；无项目行时与原口径逐值相同；接入报表引擎。"""
from __future__ import annotations

from app.models.report_models import FinancialReportType
from app.services.formula_settings.effective import effective_slots
from app.services.formula_settings.effective_report import load_effective_report_configs
from app.services.report_engine import ReportEngine

from ._env import STD, add_global_row, add_project, add_project_row, make_db

FIELDS = ("report_type", "row_code", "row_name", "row_number", "formula", "formula_category", "applicable_standard")


def _vals(rows):
    return [tuple(getattr(r, f) for f in FIELDS) for r in rows]


async def test_without_project_rows_equals_standard_rows():
    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-002", "B", row_number=2)
        await add_global_row(db, "BS-001", "A", row_number=1)
        pid = await add_project(db, "无适配")
        await db.commit()
        plain = await load_effective_report_configs(db, standard=STD, project_id=None)
        eff = await load_effective_report_configs(db, standard=STD, project_id=pid)
        assert _vals(eff) == _vals(plain) and [r.row_code for r in eff] == ["BS-001", "BS-002"]


async def test_project_rows_replace_formula_keep_structure_and_append_own_rows():
    async with make_db() as factory, factory() as db:
        g = await add_global_row(db, "BS-001", "A", row_name="货币资金")
        await add_global_row(db, "BS-002", "B", row_number=2)
        pid = await add_project(db, "有适配")
        p1 = await add_project_row(db, pid, "BS-001", "ROW('X')", base_formula="A")
        p1.row_name = "旧行名"
        await add_project_row(db, pid, "BS-002", None, base_formula="B")  # 本项目停用
        own = await add_project_row(db, pid, "BS-099", "ROW('BS-001')")  # 本项目独有行
        own.row_number = 99
        await db.commit()
        rows = {r.row_code: r for r in await load_effective_report_configs(db, standard=STD, project_id=pid)}
        assert (rows["BS-001"].formula, rows["BS-001"].row_name, rows["BS-001"].id) == ("ROW('X')", "货币资金", p1.id)
        assert rows["BS-002"].formula is None
        assert rows["BS-099"].formula == "ROW('BS-001')"
        # 返回的是拷贝：改它不影响准则行
        rows["BS-001"].formula = "篡改"
        await db.refresh(g)
        assert g.formula == "A"
        eff = await effective_slots(db, "report", pid)
        assert eff["balance_sheet:BS-002"].disabled and eff["balance_sheet:BS-001"].layer == "project"


async def test_report_engine_loads_effective_configs():
    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-001", "A")
        pid = await add_project(db, "引擎")
        await add_project_row(db, pid, "BS-001", "ROW('Y')", base_formula="A")
        await db.commit()
        engine = ReportEngine(db)
        by_type = await engine._load_report_configs(STD, project_id=pid)
        assert by_type[FinancialReportType.balance_sheet][0].formula == "ROW('Y')"
        legacy = await engine._load_report_configs(STD)
        assert legacy[FinancialReportType.balance_sheet][0].formula == "A"


_G = "TB('1001','期末余额') + TB('1002','期末余额')"


async def test_account_scope_readers_follow_effective_definition_and_honor_disabled():
    """取数层四个读取方与报表生成同口径（R1.1 / R1.2 / R7.4）：

    无本项目行 → 准则行；本项目改过 → 本项目公式；本项目行公式为空（= 本项目停用）→ 不退回准则行，
    各自走调用方兜底（修复前四处都会退回准则行，停用对取数层无效）。
    """
    from types import SimpleNamespace

    from app.services.four_table.i_cycle_accounts import _fetch_report_line
    from app.services.four_table.report_line_accounts import _fetch_formula
    from app.services.four_table.semantic_account_resolver import _fetch_report_formula
    from app.services.report_account_mapping import resolve_report_line_account_codes

    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-002", _G, row_name="货币资金")
        inherit = await add_project(db, "继承")
        adapted = await add_project(db, "改过")
        await add_project_row(db, adapted, "BS-002", "TB('1012','期末余额')", base_formula=_G)
        disabled = await add_project(db, "停用")
        await add_project_row(db, disabled, "BS-002", None, base_formula=_G)
        await db.commit()

        async def read(pid):
            ctx = SimpleNamespace(db=db, project_id=pid)
            return (
                await resolve_report_line_account_codes(db, pid, "BS-002", fallback=["9999"],
                                                        applicable_standards=[STD]),
                await _fetch_formula(ctx, "BS-002", [STD]),
                await _fetch_report_formula(ctx, "BS-002"),
                (await _fetch_report_line(ctx, "BS-002", [STD]))[1],
            )

        assert await read(inherit) == (["1001", "1002"], _G, _G, _G)
        local = "TB('1012','期末余额')"
        assert await read(adapted) == (["1012"], local, local, local)
        assert await read(disabled) == (["9999"], None, None, None)
        # 同一项目的有效定义也是「停用」：取数层与报表生成 / 公式管理中心读到同一结论
        eff = await effective_slots(db, "report", disabled)
        assert eff["balance_sheet:BS-002"].disabled


async def test_consol_load_report_rows_reads_project_adaptation():
    """合并报表求值的行配置（consol_report_values.load_report_rows）带 project_id 时叠加本项目适配。"""
    from app.services.consol_report_values import load_report_rows

    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-001", "A", row_name="货币资金")
        await add_global_row(db, "BS-002", "B", row_number=2)
        pid = await add_project(db, "合并适配")
        await add_project_row(db, pid, "BS-001", "ROW('Y')", base_formula="A")
        await db.commit()
        plain = {r.row_code: r.formula for r in await load_report_rows(db, STD)}
        eff = {r.row_code: (r.formula, r.row_name) for r in await load_report_rows(db, STD, project_id=pid)}
        assert plain == {"BS-001": "A", "BS-002": "B"}
        assert eff == {"BS-001": ("ROW('Y')", "货币资金"), "BS-002": ("B", "BS-002")}


async def test_two_report_resolvers_agree_slot_by_slot():
    """报表域两条解析路径（报表引擎 / 合并读的 effective_report，接口 / 应用到项目读的 effective_slots）
    对每个公式位给出同一条公式（R1.2「同一个有效定义」）：继承、改过、停用、本项目独有四种情形。"""
    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-001", "A")
        await add_global_row(db, "BS-002", "B", row_number=2)
        await add_global_row(db, "BS-003", "C", row_number=3)
        pid = await add_project(db, "对拍")
        await add_project_row(db, pid, "BS-002", "ROW('BS-001')", base_formula="B")
        await add_project_row(db, pid, "BS-003", None, base_formula="C")
        own = await add_project_row(db, pid, "BS-099", "ROW('BS-002')")
        own.row_number = 99
        await db.commit()
        engine_view = {f"{r.report_type.value}:{r.row_code}": r.formula
                       for r in await load_effective_report_configs(db, standard=STD, project_id=pid)}
        slots = await effective_slots(db, "report", pid)
        slot_view = {k: (None if s.disabled or s.definition is None else s.definition.get("formula"))
                     for k, s in slots.items()}
        assert engine_view == slot_view == {
            "balance_sheet:BS-001": "A", "balance_sheet:BS-002": "ROW('BS-001')",
            "balance_sheet:BS-003": None, "balance_sheet:BS-099": "ROW('BS-002')",
        }
