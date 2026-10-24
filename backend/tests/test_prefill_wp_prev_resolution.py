"""`WP()` / `PREV()` 取数守卫（spec prefill-wp-prev-resolution-repair 起建，formula-fetch-followup-defect-closure R3 改写）。

改写原因（R3）：原文件以 ``prefill_engine._resolve_wp_formula`` / ``_resolve_prev_formula`` 为对象，二者已随
``2638b32fd`` 删除（预填改走统一预载层 ``formula_preloader.preload`` + L1 内核），且以「PREV 恒为 None」为前提 ——
三参 PREV 现在按上年同底稿取数（``prev_wp_field.PriorWpFieldResolver``），前提已不成立，HEAD 上整文件红。

按现行语义改写，保留仍成立的守卫意图：

* 真实库 ``parsed_data`` 没有 ``cells`` 键，取值路径不得读它（Task 1 / Property 5）；
* WP 锚点取值 SQL 对真实 schema 可执行，至少一条已对齐锚点真取到数，未对齐锚点仍为空（不在后端复刻前端派生列）；
* 三参 PREV：上年来源取不到时值为空且有原因（不为 0），取到时是数；两参 PREV = 科目 + 列，列名不认识报错；
* 底稿定位确定性排序、未对齐 / 取值失败留日志（不静默）、待对齐上限只许下调。

删掉的：对已删函数的源码抽取断言（函数体「只有 return None」、docstring 写明「无 year 维度」等），由当前取数路径
（``formula_preloader._load_wp`` / ``_load_note``、``prev_wp_field``）的同类守卫替代。

连库测试的两个坑：连接池绑定首个事件循环 ⇒ 用独立 ``NullPool`` 引擎、一次 ``asyncio.run`` 取齐快照、同一 loop 内释放；
断言消息只用 ASCII 符号 + 汉字（GBK 不可编码字符会让整条消息被转义）。
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
_PRELOADER = _BACKEND / "app" / "services" / "formula_preloader.py"
_PREV_WP_FIELD = _BACKEND / "app" / "services" / "prev_wp_field.py"
_ANCHOR_MAP_PY = _BACKEND / "app" / "services" / "prefill_anchor_map.py"
#: 🔴 路径是 `backend/data/` 不是 `backend/data/ledger_adapters/`
_PREFILL_MAPPING = _BACKEND / "data" / "prefill_formula_mapping.json"

#: characterization 实参 —— 必须是映射表里真实存在的三元组（由 TestProbeArgsAreRealPresets 实时校验）
_WP_PROBES: tuple[tuple[str, str, str], ...] = (
    ("D2", "明细表D2-2", "期末合计"),
    ("D1", "坏账准备明细表D1-4", "按票据种类小计-期末未审数"),
    ("D4", "主营业务收入明细表D4-2", "全年收入合计"),
    ("D7", "明细表D7-2", "期末合计"),
    # 待对齐清单（派生列）：必须仍取不到数，与上面 4 条构成「已对齐 / 未对齐」双向对照
    ("D1", "原值明细表（按类别）D1-2", "合计-期末未审数"),
)
_PREV_PROBES: tuple[tuple[str, str, str], ...] = (
    ("D2", "审定表D2-1", "审定数"),
    ("D4", "营业收入审定表D4-1", "审定数"),
)
_WP_PROBES_EXPECTED_NONE: frozenset[tuple[str, str, str]] = frozenset(
    {("D1", "原值明细表（按类别）D1-2", "合计-期末未审数")}
)
#: 统一预载层各数据源取数函数（零回归锚点：防重构时被顺手删掉）
_PRELOAD_LOADERS = ("_load_tb", "_load_adj", "_load_aux", "_load_wp", "_load_note", "_load_ledger",
                    "_load_ledger_count", "_load_tb_aux", "_load_prev")


def _iter_preset_formula_calls(fn_name: str) -> set[tuple[str, str, str]]:
    """从映射表实时解析 ``fn_name('a','b','c')`` 三元组。

    🔴 实参里可能含半角括号（`附注披露信息(上市公司)`）⇒ 禁用 ``\\(([^)]*)\\)``（会在第一个 ``)`` 截断、
    把 3 参读成 2 参并静默丢条目）；改为逐字符扫描 + 引号内配对。
    """
    doc = json.loads(_PREFILL_MAPPING.read_text(encoding="utf-8"))
    out: set[tuple[str, str, str]] = set()
    needle = fn_name + "("
    for block in doc.get("mappings") or []:
        for cell in block.get("cells") or []:
            expr = str(cell.get("formula") or "")
            idx = 0
            while True:
                i = expr.find(needle, idx)
                if i < 0:
                    break
                before = expr[i - 1] if i > 0 else "="
                idx = i + len(needle)
                if before.isalnum() or before == "_":
                    continue  # TB_SUM( 被 SUM( 一类前缀误配
                args: list[str] = []
                cur, in_q, j = "", False, idx
                while j < len(expr):
                    ch = expr[j]
                    if ch == "'":
                        in_q = not in_q
                    elif in_q:
                        cur += ch
                    elif ch == ",":
                        args.append(cur)
                        cur = ""
                    elif ch == ")":
                        args.append(cur)
                        break
                    j += 1
                if len(args) >= 3:
                    out.add((args[0].strip(), args[1].strip(), args[2].strip()))
    return out


# ─────────────────────────── 源码抽取 ───────────────────────────


def strip_comments(src: str) -> str:
    """剥掉注释与三引号字符串（docstring）—— 说明文字会如实写出被禁的 ``cells`` 字样，不剥会误报。

    保留代码里的单 / 双引号短字符串（``"cells"`` 这种真实读取形态正是要抓的目标）。
    """
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    out_lines: list[str] = []
    for line in src.splitlines():
        idx = line.find("#")
        if idx >= 0:
            before = line[:idx]
            if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                line = before
        out_lines.append(line)
    return "\n".join(out_lines)


def extract_func_body(src: str, name: str) -> str:
    """按缩进截取函数体（``async def`` / ``def``）。

    🔴 缩进正则写 ``[ \\t]*`` 不写 ``\\s*``（``re.M`` 下 ``\\s`` 含换行，函数体会截成空串）；
    🔴 先按圆括号配对跳过跨行参数列表，再按缩进截取（签名收尾行缩进为 0，直接按缩进扫只截到签名）。
    """
    pat = re.compile(rf"^([ \t]*)(?:async[ \t]+)?def[ \t]+{re.escape(name)}[ \t]*\(", re.M)
    m = pat.search(src)
    if m is None:
        return ""
    indent = len(m.group(1))
    depth, sig_end = 0, -1
    for i in range(m.end() - 1, len(src)):
        ch = src[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                colon, nl = src.find(":", i), src.find("\n", i)
                sig_end = (colon if 0 <= colon < nl else nl) if nl != -1 else len(src)
                break
    if sig_end < 0:
        return ""
    body: list[str] = []
    for line in src[sig_end:].splitlines()[1:]:
        if not line.strip():
            body.append(line)
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    return "\n".join(body)


# ─────────────────────────── 连库快照 ───────────────────────────


@dataclass
class _Snapshot:
    """一次 `asyncio.run` 取齐全部连库判据（避免多 loop 撞连接池）。"""

    total_parsed: int = 0
    cells_count: int = 0
    html_count: int = 0
    wp_code_count: int = 0
    probe_project_id: str | None = None
    probe_year: int = 0
    d_wp_count: int = 0
    wp_results: dict[tuple[str, str, str], object] = field(default_factory=dict)
    #: 三参 PREV：(值, 原因)
    prev_results: dict[tuple[str, str, str], tuple[object, str]] = field(default_factory=dict)
    #: 上年数据来源：(项目, 原因)
    prev_source: tuple[object, str] = (None, "")
    short_wp_result: object = None
    schema_probe_ok: bool = False
    schema_probe_error: str = ""
    schema_probe_negative_failed: bool = False
    #: `ANCHOR_MAP` 每条真跑一次的结果（`hit:金额` / 其余六态 / `EXC:...`）
    anchor_exec_results: dict[str, str] = field(default_factory=dict)
    error: str | None = None


_COUNT_SQL = """
    SELECT count(*) AS total,
           count(*) FILTER (WHERE parsed_data ? 'cells')     AS cells,
           count(*) FILTER (WHERE parsed_data ? 'html_data') AS html,
           count(*) FILTER (WHERE parsed_data ? 'wp_code')   AS wpc
    FROM working_paper
    WHERE is_deleted = false AND parsed_data IS NOT NULL AND parsed_data::text <> '{}'
"""
_PROBE_PROJECT_SQL = """
    SELECT wp.project_id::text, count(*) AS n
    FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id
    WHERE wp.is_deleted = false AND wi.wp_code LIKE 'D%'
    GROUP BY wp.project_id ORDER BY n DESC LIMIT 1
"""


async def _probe(db, snap: _Snapshot) -> None:
    from app.services.formula_preloader import _load_wp
    from app.services.prefill_anchor_map import ANCHOR_MAP, read_anchor_value
    from app.services.prev_wp_field import PriorWpFieldResolver
    from app.services.sampling_registry_service import resolve_project_year

    row = (await db.execute(sa.text(_COUNT_SQL))).first()
    snap.total_parsed, snap.cells_count, snap.html_count, snap.wp_code_count = (int(v or 0) for v in row)
    prow = (await db.execute(sa.text(_PROBE_PROJECT_SQL))).first()
    if prow is None:
        return
    snap.probe_project_id, snap.d_wp_count = prow[0], int(prow[1] or 0)
    pid = UUID(snap.probe_project_id)
    snap.probe_year = int(await resolve_project_year(db, pid) or 0)  # 取不到年度不猜今年（原写 COALESCE(…, 2025)）
    for args in _WP_PROBES:
        snap.wp_results[args] = (await _load_wp(db, pid, snap.probe_year, {args})).get(args[0], {}).get(args[2])
    snap.short_wp_result = (await _load_wp(db, pid, snap.probe_year, {("D1", "审定表D1-1")})).get("D1")
    resolver = PriorWpFieldResolver(db, pid, snap.probe_year)
    source = await resolver.source()
    snap.prev_source = (source.project_id, source.reason)
    for args in _PREV_PROBES:
        hit = await resolver.resolve(*args)
        snap.prev_results[args] = (hit.value, hit.reason)
    # 取值层每条映射真跑一次（抓 SQL 列名 / 类型错）：异常记 EXC 让断言打红，不吞成「无数据」
    for key, spec in ANCHOR_MAP.items():
        label = "|".join(key)
        try:
            async with db.begin_nested():
                res = await read_anchor_value(db, pid, key[0], spec)
            snap.anchor_exec_results[label] = (f"{res.status.value}:{res.value}" if res.value is not None
                                               else res.status.value)
        except Exception as exc:  # noqa: BLE001
            snap.anchor_exec_results[label] = f"EXC:{type(exc).__name__}: {exc}"
    # 反向自检：故意写错列名的同形查询必须失败；正向锚点：正确列名必须可执行
    try:
        async with db.begin_nested():
            await db.execute(sa.text("SELECT remark FROM checklist_responses WHERE workpaper_id = CAST(:x AS uuid) LIMIT 1"),
                             {"x": str(pid)})
    except Exception:  # noqa: BLE001
        snap.schema_probe_negative_failed = True
    try:
        async with db.begin_nested():
            await db.execute(sa.text("SELECT remark FROM checklist_responses WHERE wp_id = CAST(:x AS uuid) "
                                     "AND item_id = :i LIMIT 1"), {"x": str(pid), "i": "probe"})
        snap.schema_probe_ok = True
    except Exception as exc:  # noqa: BLE001
        snap.schema_probe_error = f"{type(exc).__name__}: {exc}"


async def _load_snapshot() -> _Snapshot:
    """取齐全部连库判据。🔴 用独立 NullPool 引擎、同一 loop 内释放（借共享池会在 loop 关闭后污染同进程其他连库测试）。"""
    snap = _Snapshot()
    engine = None
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings

        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            await _probe(db, snap)
    except Exception as exc:  # noqa: BLE001
        snap.error = f"{type(exc).__name__}: {exc}"
    finally:
        if engine is not None:
            try:
                await engine.dispose()
            except Exception:  # noqa: BLE001
                pass
    return snap


_SNAP: _Snapshot = asyncio.run(_load_snapshot())


@pytest.fixture(scope="module")
def snap() -> _Snapshot:
    if _SNAP.error:
        pytest.fail(f"连库快照加载失败，本文件的连库判据全部未执行（禁止静默 skip）：\n  {_SNAP.error}")
    return _SNAP


# ═════════════════════ cells 全库零命中实证 ═════════════════════


class TestCellsKeyAbsent:
    """`parsed_data.cells` 在任何写入路径下都不产生 —— 取值路径读它等于恒取不到。"""

    def test_scan_surface_is_not_empty(self, snap: _Snapshot) -> None:
        """反向锚点：扫描面非空（否则「cells 零命中」恒成立）。"""
        assert snap.total_parsed > 0, "working_paper 中未删且 parsed_data 非空的行数为 0，零命中断言空转。"
        assert snap.html_count > 0, f"parsed_data ? 'html_data' 计数为 0（total={snap.total_parsed}），查询条件疑似有误。"
        assert snap.wp_code_count > 0, f"parsed_data ? 'wp_code' 计数为 0（total={snap.total_parsed}），正向锚点不成立。"

    def test_cells_key_never_produced(self, snap: _Snapshot) -> None:
        assert snap.cells_count == 0, (
            f"parsed_data ? 'cells' 计数为 {snap.cells_count}（预期 0）：平台新增了写入路径，取值口径需重新评估，"
            "不要直接放宽本断言。")

    def test_cells_far_rarer_than_html_data(self, snap: _Snapshot) -> None:
        assert snap.cells_count < snap.html_count


# ═════════════════════ probe 实参是真实预设 ═════════════════════


class TestProbeArgsAreRealPresets:
    """probe 实参从映射表实时校验：预设改动后变成幻想实参会立即打红，而不是让 characterization 分不清病因。"""

    def test_mapping_file_exists_and_parses(self) -> None:
        assert _PREFILL_MAPPING.exists(), f"预设文件不存在：{_PREFILL_MAPPING}"
        assert len(_iter_preset_formula_calls("WP")) >= 50, "WP 三元组过少，解析疑似失效"
        assert len(_iter_preset_formula_calls("PREV")) >= 50, "PREV 三元组过少，解析疑似失效"

    def test_wp_probes_are_real_presets(self) -> None:
        real = _iter_preset_formula_calls("WP")
        assert not [p for p in _WP_PROBES if p not in real], "WP probe 实参不在映射表里"

    def test_prev_probes_are_real_presets(self) -> None:
        real = _iter_preset_formula_calls("PREV")
        assert not [p for p in _PREV_PROBES if p not in real], "PREV probe 实参不在映射表里"

    def test_paren_tolerant_parsing_selfcheck(self) -> None:
        """实参带半角括号的预设必须被完整解析成 3 参（该形态实测存在，如 D2 / D3 / D7 的披露 sheet）。"""
        with_paren = [t for t in _iter_preset_formula_calls("PREV") if "(" in t[1]]
        assert with_paren, "找不到 sheet 名含半角括号的 PREV 条目，本自检空转"
        assert all(t[2] for t in with_paren), "第三参为空，解析在括号处截断了"


# ═════════════════════ characterization（真实库） ═════════════════════


class TestResolverCharacterization:
    """WP：已对齐锚点真取到数、未对齐锚点仍为空；三参 PREV：取不到时有原因且不为 0；两参 WP 取不到。"""

    def test_probe_project_available(self, snap: _Snapshot) -> None:
        assert snap.probe_project_id is not None and snap.d_wp_count > 0, "库中找不到含 D 循环底稿的项目"
        assert snap.probe_year > 0, f"探针项目 {snap.probe_project_id} 没有审计年度（不猜今年），characterization 无法执行"

    def test_aligned_wp_anchors_now_resolve(self, snap: _Snapshot) -> None:
        """至少一条已对齐锚点真取到数（部分明细表确实未编制，不要求全部有值；一条都没有 = 链路是死的）。"""
        aligned = {k: v for k, v in snap.wp_results.items() if k not in _WP_PROBES_EXPECTED_NONE}
        assert aligned, "已对齐 probe 集合为空，characterization 空转"
        assert any(v is not None for v in aligned.values()), (
            f"全部已对齐锚点都取不到数（探针项目 {snap.probe_project_id}）：{aligned}\n"
            "排查：verify_prefill_wp_prev_live.py 看六态分布；全 NO_ITEM = 未编制（换项目，不改断言）；"
            "ERROR = 取值层 SQL 有缺陷（曾把 checklist_responses.wp_id 写成 workpaper_id）。")

    def test_unaligned_wp_anchors_stay_none(self, snap: _Snapshot) -> None:
        """待对齐锚点（前端派生列，不落库）必须仍为空：在后端复刻前端派生公式即双真源。"""
        leaked = {k: v for k, v in snap.wp_results.items() if k in _WP_PROBES_EXPECTED_NONE and v is not None}
        assert not leaked, f"待对齐锚点取到了值：{leaked}（正解见 OUT_OF_SCOPE_CHANGES['frontend_persist_derived_columns']）"

    def test_prev_three_args_value_or_reason(self, snap: _Snapshot) -> None:
        """三参 PREV 取上年同底稿数：有上年数据 ⇒ 值；没有 ⇒ 空 + 原因（不为 0，原因与上年来源一致）。"""
        assert snap.prev_results, "PREV probe 一条都没跑到"
        source_pid, source_reason = snap.prev_source
        for args, (value, reason) in snap.prev_results.items():
            if source_pid is None:
                assert value is None and reason == source_reason and reason, (
                    f"没有上年数据时 PREV{args} 必须为空并给出上年来源原因，实际 值={value!r} 原因={reason!r}")
            else:
                assert (value is None) == bool(reason), f"PREV{args} 值与原因必须二选一：值={value!r} 原因={reason!r}"
                assert value is None or isinstance(value, Decimal)

    def test_two_arg_wp_returns_nothing(self, snap: _Snapshot) -> None:
        """两参 WP 不是底稿锚点写法：取不到（不猜锚点）。"""
        assert snap.short_wp_result is None, f"两参 WP 取到了值：{snap.short_wp_result!r}"


class TestPrevTwoArgsIsAccountAndColumn:
    """两参 ``PREV('科目','列')``：第二参是列名，不认识的列报错（不按 0、不当底稿表名）。"""

    def test_unknown_column_raises(self) -> None:
        from app.services.formula_engine import FormulaContext, execute

        result = execute("PREV('D1','审定表D1-1')", FormulaContext())
        assert not result.ok and any("列名「审定表D1-1」未注册" in e for e in result.errors), result

    def test_registered_column_reads_prior_tb(self) -> None:
        from app.services.formula_engine import FormulaContext, execute

        # L1 的试算表数据按规范列名存（「审定数」是「期末余额」的别名，预载层 _load_tb 同口径）
        ctx = FormulaContext(prior_tb_data={"1121": {"期末余额": Decimal("800")}})
        result = execute("PREV('1121','审定数')", ctx)
        assert result.ok and result.value == Decimal("800"), result


# ═════════════════════ 源码守卫：取值路径不读 cells ═════════════════════


class TestResolverSourceGuard:
    """现行取值路径（统一预载层 ``_load_wp`` / ``_load_note``、三参 PREV 的 ``prev_wp_field``）不得读 ``cells``。"""

    @staticmethod
    def _preloader() -> str:
        return strip_comments(_PRELOADER.read_text(encoding="utf-8"))

    def test_extraction_is_not_vacuous(self) -> None:
        """反向自检：确实截到了 ``_load_wp`` 的函数体（正则失效时函数体为空，下面的断言会恒成立）。"""
        body = extract_func_body(self._preloader(), "_load_wp")
        assert body and len(body.splitlines()) >= 5, "未截到 _load_wp 的函数体，源码守卫空转"
        assert "read_anchor_value" in body and "resolve_anchor" in body, "截到的不是 WP 取值函数"

    def test_strip_comments_selfcheck(self) -> None:
        sample = ('def f():\n    """docstring 提到 cells 是说明文字"""\n    # 注释里也提到 cells\n'
                  '    x = data.get("cells", {})\n    return x\n')
        cleaned = strip_comments(sample)
        assert "docstring" not in cleaned and "注释里" not in cleaned, "说明文字未剥掉"
        assert '"cells"' in cleaned, "代码里的 \"cells\" 字符串被误剥了 —— 那正是要抓的目标形态"

    def test_value_paths_do_not_read_cells(self) -> None:
        src = self._preloader()
        offenders = [name for name in ("_load_wp", "_load_note", "_load_note_fallback", "_load_prev")
                     if re.search(r"""['"]cells['"]""", extract_func_body(src, name))]
        assert not offenders, f"以下取值函数在读 parsed_data['cells']（真实库零命中）：{offenders}"
        prev_src = strip_comments(_PREV_WP_FIELD.read_text(encoding="utf-8"))
        assert not re.search(r"""['"]cells['"]""", prev_src), "三参 PREV 在读 cells"

    def test_prev_three_args_recomputes_on_prior_source(self) -> None:
        """三参 PREV 按上年来源（同项目上年 → 上年项目）重算，不读本年底稿：取值函数不查 working_paper。"""
        src = strip_comments(_PREV_WP_FIELD.read_text(encoding="utf-8"))
        assert "resolve_prior_source" in src, "三参 PREV 不再经 prior_year_context 找上年来源"
        assert "project_id=source.project_id, year=source.year" in src, "三参 PREV 没有在上年来源上求值"
        for forbidden in ("WorkingPaper", "working_paper", "parsed_data"):
            assert forbidden not in src, f"三参 PREV 引用了 {forbidden}：底稿没有年度维度，读到的只能是本年"

    def test_preload_loaders_still_present(self) -> None:
        src = _PRELOADER.read_text(encoding="utf-8")
        missing = [n for n in _PRELOAD_LOADERS if not extract_func_body(src, n)]
        assert not missing, f"统一预载层取数函数不见了：{missing}"

    def test_note_loader_is_the_row_label_paradigm(self) -> None:
        """附注取值按行标签 + 列键匹配、不碰 cells（「JSON 内寻址」的既有范式）。"""
        body = extract_func_body(self._preloader(), "_load_note")
        assert body, "未截到 _load_note"
        assert '"label"' in body and not re.search(r"""['"]cells['"]""", body)


# ═════════════════════ 取值层 SQL 对真实 schema 可执行 ═════════════════════


class TestAnchorSqlSchemaContract:
    """取值层 SQL 必须真能在真实 schema 上执行（列名写错会被 fail-soft 吞成「无数据」，源码扫描抓不到）。"""

    def test_referenced_columns_exist(self, snap: _Snapshot) -> None:
        assert snap.schema_probe_ok, f"取值层 SQL 引用了真实 schema 里不存在的列：{snap.schema_probe_error}"
        assert snap.schema_probe_negative_failed, "反向自检失败：故意写错列名的查询没有报错，探测手段已失效"

    def test_read_anchor_value_executes_without_exception(self, snap: _Snapshot) -> None:
        assert snap.anchor_exec_results, f"一条 ANCHOR_MAP 取值都没跑到（快照错误：{snap.error}）"
        crashed = {k: v for k, v in snap.anchor_exec_results.items() if v.startswith("EXC:")}
        assert not crashed, "以下锚点取值层抛异常（接线错误，不是业务态）：\n" + "\n".join(
            f"  {k} -> {v}" for k, v in sorted(crashed.items()))

    def test_at_least_one_anchor_hits_in_real_db(self, snap: _Snapshot) -> None:
        hits = {k: v for k, v in snap.anchor_exec_results.items() if v.startswith("hit")}
        assert hits, "真实库里没有任何已对齐锚点取到数，六态分布：\n" + "\n".join(
            f"  {k} -> {v}" for k, v in sorted(snap.anchor_exec_results.items()))


# ═════════════════════ 确定性排序 / 留日志 / 上限只许下调 ═════════════════════


class TestDeterministicOrderingAndLogging:
    """底稿定位确定性 ORDER BY（真实库无「同项目同底稿编码多份」样本，行为层测不出，只能源码级钉死）；
    未对齐 / 取值失败必须留日志（fail-soft 但不静默 —— 列名写错曾因此藏了一整轮）。"""

    @staticmethod
    def _code_body(func_name: str) -> str:
        """函数代码体：用 AST 只剥函数自己的 docstring 与 ``#`` 注释，保留 SQL 三引号串
        （``strip_comments`` 会把 SQL 一起剥掉，「有没有 ORDER BY」就查不到目标文本）。"""
        import ast

        src = _ANCHOR_MAP_PY.read_text(encoding="utf-8")
        lines = src.splitlines()
        target = next((n for n in ast.walk(ast.parse(src))
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name), None)
        if target is None:
            return ""
        doc = target.body[0]
        blank: set[int] = set()
        if isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant) and isinstance(doc.value.value, str):
            blank = set(range(doc.lineno, (doc.end_lineno or doc.lineno) + 1))
        return "\n".join(lines[ln - 1] for ln in range(target.body[0].lineno, (target.end_lineno or 0) + 1)
                         if ln not in blank and not lines[ln - 1].strip().startswith("#"))

    def test_extraction_is_not_vacuous(self) -> None:
        body = self._code_body("read_anchor_value")
        assert body and "checklist_responses" in body, "未截到 read_anchor_value，本类断言空转"
        assert "SELECT" in body, "SQL 字符串被误剥了，ORDER BY / 列名断言会空转"

    def test_workpaper_lookup_is_deterministic(self) -> None:
        body = self._code_body("read_anchor_value")
        assert re.search(r"ORDER\s+BY\s+wp\.updated_at\s+DESC", body), "底稿定位缺 ORDER BY wp.updated_at DESC"
        assert re.search(r"ORDER\s+BY[^\n]*wp\.id\s+ASC", body), "缺 wp.id ASC 兜底（updated_at 相同时仍不确定）"

    def test_unaligned_and_failure_are_logged(self) -> None:
        body = extract_func_body(strip_comments(_PRELOADER.read_text(encoding="utf-8")), "_load_wp")
        assert body, "未截到 _load_wp"
        assert len(re.findall(r"logger\.warning\s*\(", body)) >= 2, "_load_wp 应至少 2 处 warning（未对齐 + 取值失败）"
        assert "exc_info=True" in body, "取值失败分支缺 exc_info=True —— 没有 traceback 定位不到是哪一层坏了"

    def test_failure_is_isolated_not_propagated(self) -> None:
        """fail-soft：异常被捕获、且取值在保存点里（PG 上一条语句失败会让后续预载全停在中止的事务里）。"""
        body = extract_func_body(strip_comments(_PRELOADER.read_text(encoding="utf-8")), "_load_wp")
        assert "except Exception" in body and "begin_nested" in body


class TestUnalignedCapCannotBeRaised:
    """待对齐上限只许下调：原断言只查 ``len(UNALIGNED) <= UNALIGNED_MAX``，把上限改大仍全绿。"""

    #: 交付时的实测值。只许下调 —— 上调即新增了对不齐的锚点。
    _CAP_CEILING = 4

    def test_cap_is_not_raised(self) -> None:
        from app.services.prefill_anchor_map import UNALIGNED, UNALIGNED_MAX

        assert UNALIGNED_MAX <= self._CAP_CEILING, (
            f"UNALIGNED_MAX 被抬到 {UNALIGNED_MAX}（交付时上限 {self._CAP_CEILING}）：正解是去修映射或落实前端持久化，"
            "不是把闸门开大。")
        assert UNALIGNED, "UNALIGNED 为空 —— 若确已全部对齐，应把 _CAP_CEILING 与 UNALIGNED_MAX 一并降到 0"
