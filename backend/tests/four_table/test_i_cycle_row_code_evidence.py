"""I 循环 row_code 与 `report_config` 对账守卫（Wave 1 先打红）。

spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/
      Requirements 1.1 / 1.2 / 1.3 / 1.6 / 1.7 / 1.8，Property 1 / 2 / 4 / 5 / 42

**两类断言（memory 铁律「Wave 1 守卫必须分两类」）**

- **类 A（独立口径判据，现在应全绿）** —— 本文件自己连库查 `report_config` 得
  ``(row_code, applicable_standard) → (row_name, formula)``，不经被测模块；
  绿了才证明判据基础设施有效而非空转。
- **类 B（被测实现，现在应全红）** —— 断言 `I_CYCLE_ROW_CODES` 的取值命中期望语义。
  失败消息写明「尚未收敛（Wave 2 Task 4）」。

**连库形态（memory 铁律）** —— 一次 `asyncio.run` 取快照 + 全部断言同步。
pytest-asyncio 默认每个测试新建 loop，而 `app.core.database` 连接池绑定首个 loop
→ 第二个连库测试起报 ``'NoneType' object has no attribute 'send'``；若 fixture 里
``except → pytest.skip`` 就变成静默假绿。故这里用**专用一次性 engine**
（``poolclass=NullPool``）并在同一 loop 内 dispose，全程不碰共享池。
"""
from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

# ─────────────────────────────────────────────────────────────────────────────
# 判据真源（类 A 独立口径：由本文件按 report_config 实证冻结，不 import 被测模块）
# ─────────────────────────────────────────────────────────────────────────────

#: I 循环 → 正确 row_code（2026-08-09 `report_config` 四准则逐条对账）
EXPECTED_ROW_CODES: dict[str, str] = {
    "I1": "BS-032",
    "I2": "BS-033",
    "I3": "BS-034",
    "I4": "BS-035",
    "I5": "BS-037",
    "I6": "IS-006",
}

#: 正确 row_code → 期望 row_name（逐字取自 `report_config`）
EXPECTED_ROW_NAMES: dict[str, str] = {
    "BS-032": "无形资产",
    "BS-033": "开发支出",
    "BS-034": "商誉",
    "BS-035": "长期待摊费用",
    "BS-037": "其他非流动资产",
    "IS-006": "研发费用",
}

#: 正确 row_code → 期望 formula（四准则一致）
EXPECTED_FORMULAS: dict[str, str] = {
    "BS-032": "TB('1701','期末余额') - TB('1702','期末余额')",
    "BS-033": "TB('1704','期末余额')",
    "BS-034": "TB('1711','期末余额')",
    "BS-035": "TB('1801','期末余额')",
    "BS-037": "TB('1911','期末余额')",
    "IS-006": "TB('6604','本期发生额')",
}

#: 改动前被消费的错值（Wave 2 落地后这些必须消失；留证防回退）
#: 🔴 12 个取值里 11 个错，仅 ``I6.listed`` 恰好正确
LEGACY_WRONG_ROW_CODES: dict[str, dict[str, str]] = {
    "I1": {"listed": "BS-033", "soe": "BS-045"},
    "I2": {"listed": "BS-035", "soe": "BS-046"},
    "I3": {"listed": "BS-037", "soe": "BS-047"},
    "I4": {"listed": "BS-038", "soe": "BS-048"},
    "I5": {"listed": "BS-040", "soe": "BS-050"},
    "I6": {"listed": "IS-006", "soe": "IS-024"},
}

#: 错值实际指向的科目（说明「错在哪」，供报告与守卫消息用）
LEGACY_WRONG_MEANINGS: dict[str, str] = {
    "BS-038": "非流动资产合计（ROW 派生行）",
    "BS-040": "流动负债：（节标题，formula 为 NULL）",
    "BS-045": "应付账款",
    "BS-046": "预收款项",
    "BS-047": "合同负债",
    "BS-048": "应付职工薪酬",
    "BS-050": "其他应付款",
    "IS-024": "四、净利润（ROW 派生行）",
}

#: 四个 `applicable_standard` 全集
ALL_STANDARDS = (
    "listed_standalone",
    "listed_consolidated",
    "soe_standalone",
    "soe_consolidated",
)

_WAVE2 = "尚未收敛（Wave 2 Task 4）"

_BACKEND = Path(__file__).resolve().parents[2]
_ICA_PATH = _BACKEND / "app" / "services" / "four_table" / "i_cycle_accounts.py"
_ISPECS_PATH = _BACKEND / "app" / "services" / "four_table" / "i_cycle_specs.py"
_LEGACY_GUARD_PATH = _BACKEND / "tests" / "four_table" / "test_i_cycle_accounts.py"


def _code_level_source(src: str) -> str:
    """返回剥掉注释与 docstring 后的**代码**文本。

    Args:
        src: 源码**文本**（不是路径 —— 调用方通常已读出以便同时做 raw 侧断言）。

    为什么必须剥（memory 已记的坑）：改写错基线时，正确做法是在 docstring 里
    **留证**「改写前它断言 ``BS-045``（应付账款）」—— 那是资产不是残留。裸
    ``"BS-045" in src`` 会把这段说明数成 offender，逼人删掉正是下个会话需要的记载。

    **普通字符串字面量不剥** —— 参数化期望值 ``("I1", [...], "BS-032")`` 正是
    要判的对象，剥了判据就整体空转。
    """
    import io
    import tokenize

    # 1) AST 剥 docstring：收集每个 docstring 占据的行号
    doc_lines: set[int] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:  # pragma: no cover - 语法错时退化为只剥注释
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            body = getattr(node, "body", None) or []
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                lo = first.lineno
                hi = getattr(first, "end_lineno", lo) or lo
                doc_lines.update(range(lo, hi + 1))

    # 2) tokenize 剥 `#` 注释
    comment_spans: list[tuple[int, int, int]] = []  # (行, 起列, 止列)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                comment_spans.append((tok.start[0], tok.start[1], tok.end[1]))
    except (tokenize.TokenError, IndentationError):  # pragma: no cover
        pass

    lines = src.splitlines()
    by_line: dict[int, list[tuple[int, int]]] = {}
    for ln, c0, c1 in comment_spans:
        by_line.setdefault(ln, []).append((c0, c1))

    out: list[str] = []
    for idx, line in enumerate(lines, start=1):
        if idx in doc_lines:
            out.append("")
            continue
        for c0, _c1 in sorted(by_line.get(idx, []), reverse=True):
            line = line[:c0]
        out.append(line)
    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# 连库快照（一次 asyncio.run + 专用一次性 engine）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Snapshot:
    """`report_config` 中本 spec 关心的行。"""

    #: ``(row_code, applicable_standard) → (row_name, formula)``
    rows: dict[tuple[str, str], tuple[str, str | None]] = field(default_factory=dict)
    #: ``row_name → set[row_code]``（反查：某科目名挂在哪些行）
    by_name: dict[str, set[str]] = field(default_factory=dict)
    ok: bool = False
    error: str = ""


def _db_url() -> str:
    from app.core.config import settings

    return settings.DATABASE_URL


async def _load(snap: Snapshot) -> None:
    engine = create_async_engine(_db_url(), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                sa.text(
                    "SELECT row_code, applicable_standard, row_name, formula "
                    "FROM report_config "
                    "WHERE is_deleted = false "
                    "AND applicable_standard NOT LIKE 'project:%'"
                )
            )
            for r in res.fetchall():
                rc = (r.row_code or "").strip()
                std = (r.applicable_standard or "").strip()
                nm = (r.row_name or "").strip()
                snap.rows[(rc, std)] = (nm, r.formula)
                snap.by_name.setdefault(nm, set()).add(rc)
        snap.ok = True
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def snap() -> Snapshot:
    s = Snapshot()
    try:
        asyncio.run(_load(s))
    except Exception as e:  # noqa: BLE001
        s.error = f"{type(e).__name__}: {e}"
    return s


@pytest.fixture(scope="module")
def live(snap: Snapshot) -> Snapshot:
    """要求连库成功 —— 连不上直接 fail（**不 skip**，否则静默假绿）。"""
    if not snap.ok:
        pytest.fail(
            "连库失败，本文件的类 A 判据无法建立（禁 skip：会变成静默假绿）。\n"
            f"错误：{snap.error}"
        )
    return snap


# ─────────────────────────────────────────────────────────────────────────────
# 类 A —— 独立口径判据（现在应全绿）
# ─────────────────────────────────────────────────────────────────────────────


class TestClassAReportConfigEvidence:
    """本文件自行查 `report_config` 建立判据，不经被测模块。"""

    def test_snapshot_nonempty(self, live: Snapshot):
        """扫描面非空自检（防判据空转）。"""
        assert len(live.rows) > 500, (
            f"report_config 只取到 {len(live.rows)} 行，扫描面异常"
        )

    @pytest.mark.parametrize("code", sorted(EXPECTED_ROW_NAMES))
    def test_expected_row_name(self, live: Snapshot, code: str):
        """六个正确 row_code 的 row_name 逐条命中期望。"""
        want = EXPECTED_ROW_NAMES[code]
        for std in ALL_STANDARDS:
            got = live.rows.get((code, std))
            assert got is not None, f"{code} 在 {std} 下不存在"
            assert got[0] == want, f"{code}/{std} row_name={got[0]!r} 期望 {want!r}"

    @pytest.mark.parametrize("code", sorted(EXPECTED_FORMULAS))
    def test_expected_formula_identical_across_standards(
        self, live: Snapshot, code: str
    ):
        """六个正确 row_code 的 formula 四准则一致且等于期望值。"""
        want = EXPECTED_FORMULAS[code]
        seen: set[str] = set()
        for std in ALL_STANDARDS:
            got = live.rows.get((code, std))
            assert got is not None, f"{code} 在 {std} 下不存在"
            assert got[1] is not None, f"{code}/{std} formula 为 NULL"
            seen.add(str(got[1]).strip())
        assert len(seen) == 1, f"{code} 的 formula 跨准则不一致：{sorted(seen)}"
        assert seen.pop() == want, f"{code} formula 与期望不符"

    @pytest.mark.parametrize("code", sorted(LEGACY_WRONG_MEANINGS))
    def test_legacy_wrong_codes_point_elsewhere(self, live: Snapshot, code: str):
        """改动前那批错码确实指向别的科目（证明「错」这一判断有据）。"""
        i_names = set(EXPECTED_ROW_NAMES.values())
        for std in ALL_STANDARDS:
            got = live.rows.get((code, std))
            if got is None:
                continue
            assert got[0] not in i_names, (
                f"{code}/{std} 的 row_name={got[0]!r} 竟是 I 类科目名，"
                "说明 LEGACY_WRONG_MEANINGS 登记有误"
            )

    def test_i_cycle_names_have_unique_row_code(self, live: Snapshot):
        """六个 I 类科目名各自只挂一个 row_code（否则「唯一正确码」这一前提不成立）。"""
        problems = []
        for name in EXPECTED_ROW_NAMES.values():
            codes = live.by_name.get(name, set())
            if len(codes) != 1:
                problems.append(f"{name!r} → {sorted(codes)}")
        assert not problems, "以下 I 类科目名挂了多个 row_code：\n" + "\n".join(problems)

    def test_expected_mapping_is_consistent(self):
        """两张判据表自洽（EXPECTED_ROW_CODES 的值必须都在 EXPECTED_ROW_NAMES 里）。"""
        assert set(EXPECTED_ROW_CODES.values()) == set(EXPECTED_ROW_NAMES)
        assert set(EXPECTED_ROW_CODES.values()) == set(EXPECTED_FORMULAS)


# ─────────────────────────────────────────────────────────────────────────────
# 类 B —— 被测实现（Wave 2 前应全红）
# ─────────────────────────────────────────────────────────────────────────────


def _row_codes():
    from app.services.four_table.i_cycle_accounts import I_CYCLE_ROW_CODES

    return I_CYCLE_ROW_CODES


class TestProperty1RowCodeMatchesReportConfig:
    """Property 1：`I_CYCLE_ROW_CODES` 取值的 row_name 必须命中本循环期望语义。"""

    @pytest.mark.parametrize("wp", sorted(EXPECTED_ROW_CODES))
    @pytest.mark.parametrize("entity", ["listed", "soe"])
    def test_row_code_row_name_hits_expected(
        self, live: Snapshot, wp: str, entity: str
    ):
        from app.services.four_table.i_cycle_accounts import I_CYCLE_EXPECTED_NAMES

        code = (_row_codes().get(wp) or {}).get(entity, "")
        assert code, f"{wp}.{entity} 未声明 row_code"

        keywords = I_CYCLE_EXPECTED_NAMES.get(wp, ())
        assert keywords, f"{wp} 未声明期望语义"

        std = "soe_standalone" if entity == "soe" else "listed_standalone"
        got = live.rows.get((code, std))
        actual_name = got[0] if got else "<不存在>"
        hit = bool(got) and any(k in got[0] for k in keywords)

        assert hit, (
            f"{_WAVE2}：{wp}.{entity} 的 row_code={code} 在 {std} 下 "
            f"row_name={actual_name!r}（{LEGACY_WRONG_MEANINGS.get(code, '?')}），"
            f"不命中期望语义 {'/'.join(keywords)}；"
            f"正确值应为 {EXPECTED_ROW_CODES[wp]}"
        )

    @pytest.mark.parametrize("wp", sorted(EXPECTED_ROW_CODES))
    def test_row_code_equals_expected(self, wp: str):
        """取值必须逐字等于实证正确值（两侧同码）。"""
        table = _row_codes().get(wp) or {}
        want = EXPECTED_ROW_CODES[wp]
        got = {k: table.get(k) for k in ("listed", "soe")}
        assert got == {"listed": want, "soe": want}, (
            f"{_WAVE2}：{wp} 声明 {got}，期望两侧同为 {want}"
        )


class TestProperty2SameCodeAcrossStandards:
    """Property 2：I 类两准则同码（防被按 J1「按变体不同」范式误改成两码）。"""

    @pytest.mark.parametrize("wp", sorted(EXPECTED_ROW_CODES))
    def test_listed_equals_soe(self, wp: str):
        table = _row_codes().get(wp) or {}
        assert table.get("listed") == table.get("soe"), (
            f"{_WAVE2}：{wp} 两准则取值不同（listed={table.get('listed')} / "
            f"soe={table.get('soe')}）。I 类实证四准则同码同名同公式。"
        )

    def test_evidence_supports_same_code(self, live: Snapshot):
        """类 A 佐证：六个正确码在四准则下 row_name 与 formula 均相同。"""
        for code in EXPECTED_ROW_CODES.values():
            names = {live.rows[(code, s)][0] for s in ALL_STANDARDS}
            formulas = {str(live.rows[(code, s)][1]) for s in ALL_STANDARDS}
            assert len(names) == 1, f"{code} row_name 跨准则不一致：{sorted(names)}"
            assert len(formulas) == 1, f"{code} formula 跨准则不一致"


class TestProperty4DualSourceEliminated:
    """Property 4：I 循环 row_code 这一语义只允许一份声明。"""

    def test_i_cycle_specs_has_no_independent_row_code(self):
        if not _ISPECS_PATH.exists():
            return  # 已删除 = 合规
        src = _ISPECS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            fname = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if fname != "SemanticAccountSpec":
                continue
            for kw in node.keywords:
                if kw.arg == "row_code" and isinstance(kw.value, ast.Constant):
                    offenders.append(f"L{node.lineno}: row_code={kw.value.value!r}")
        assert not offenders, (
            f"{_WAVE2}：`i_cycle_specs.py` 仍有独立 row_code 字面量（双真源）：\n"
            + "\n".join(offenders)
            + "\n处置见 Task 5（迁移正文常量后删除该文件）"
        )

    def test_reverse_self_check_detector_works(self):
        """反向自检：检测器对含 row_code 的替身源码必须命中。"""
        fake = (
            "from x import SemanticAccountSpec\n"
            "S = SemanticAccountSpec(row_code='BS-999', slots=())\n"
        )
        tree = ast.parse(fake)
        found = [
            kw.value.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (getattr(node.func, "id", None) == "SemanticAccountSpec")
            for kw in node.keywords
            if kw.arg == "row_code" and isinstance(kw.value, ast.Constant)
        ]
        assert found == ["BS-999"], "检测器失效（AST 判据写坏了）"


class TestProperty5RowNameGateStillThere:
    """Property 5：行名校验闸必须仍在且真的会丢弃错行名的公式。"""

    def test_gate_rejects_wrong_row_name(self):
        from app.services.four_table.i_cycle_accounts import (
            I_CYCLE_EXPECTED_NAMES,
            row_name_matches,
        )

        assert row_name_matches("其他应付款", I_CYCLE_EXPECTED_NAMES["I5"]) is False
        assert row_name_matches("四、净利润", I_CYCLE_EXPECTED_NAMES["I6"]) is False
        assert row_name_matches("无形资产", I_CYCLE_EXPECTED_NAMES["I1"]) is True

    def test_gate_is_called_by_resolver(self):
        """源码级：`resolve_i_cycle_accounts` 函数体内必须调用行名闸。"""
        src = _ICA_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        target = None
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
                and node.name == "resolve_i_cycle_accounts"
            ):
                target = node
                break
        assert target is not None, "未找到 resolve_i_cycle_accounts（守卫需更新）"
        calls = {
            getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            for n in ast.walk(target)
            if isinstance(n, ast.Call)
        }
        assert "row_name_matches" in calls, (
            "`resolve_i_cycle_accounts` 未调用 row_name_matches —— "
            "行名闸是防回退护栏，不得删"
        )


class TestProperty42LegacyGuardBaselineRewritten:
    """Property 42：既有守卫的错基线必须改写（守卫在保护错的那一侧）。

    🔴 `test_i_cycle_accounts.py::TestResolveRowCode` 的 12 个参数化用例逐条断言错码，
    这是错码长期存活的直接原因。Wave 2 必须诚实改写，不得为了让它通过而回退真源。
    """

    def _legacy_src(self) -> str:
        assert _LEGACY_GUARD_PATH.exists(), f"{_LEGACY_GUARD_PATH} 不存在"
        return _LEGACY_GUARD_PATH.read_text(encoding="utf-8")

    def test_legacy_guard_has_no_wrong_expectations(self):
        """错码不得作为**代码级**期望值出现。

        🔴 判据必须剥 docstring 与注释 —— 改写后的 `TestResolveRowCode` docstring 里
        会写「改写前它断言 ``I1.soe='BS-045'``」作为留证，那是**资产不是残留**。
        裸 ``f'"{c}"' in src`` 会把留证文字数成 offender，逼人删掉正是下个会话需要的记载
        （同 memory 已记「源码守卫扫某字段有没有消费方必须剥 docstring」）。
        """
        code = _code_level_source(self._legacy_src())
        wrong = sorted(
            {
                c
                for t in LEGACY_WRONG_ROW_CODES.values()
                for c in t.values()
                if c not in EXPECTED_ROW_CODES.values()
            }
        )
        residue = [c for c in wrong if f'"{c}"' in code or f"'{c}'" in code]
        assert not residue, (
            f"{_WAVE2}：`test_i_cycle_accounts.py` 仍把错码当期望值（代码级）："
            f"{residue}\n"
            "这些码分别是："
            + "、".join(f"{c}={LEGACY_WRONG_MEANINGS.get(c, '?')}" for c in residue)
            + "\n处置见 Task 4b（诚实改写为正确值）"
        )

    def test_legacy_guard_expects_correct_codes(self):
        code = _code_level_source(self._legacy_src())
        missing = [
            c for c in sorted(EXPECTED_ROW_CODES.values()) if f'"{c}"' not in code
        ]
        assert not missing, (
            f"{_WAVE2}：`test_i_cycle_accounts.py` 未把正确码作为期望值：{missing}"
        )

    def test_reverse_self_check_scan_surface_nonempty(self):
        """反向自检：扫描面非空（该文件确实含参数化期望值）。"""
        code = _code_level_source(self._legacy_src())
        assert "TestResolveRowCode" in code, "扫描面异常：未找到 TestResolveRowCode"
        assert "resolve_row_code" in code, "扫描面异常：未找到 resolve_row_code 调用"

    def test_reverse_self_check_docstring_residue_is_expected(self):
        """反向自检（双向）：错码**确实**仍出现在 raw 源码里、但**不**出现在 code-level。

        这条把「剥 docstring 生效」钉死：
        - raw 有命中 ⇒ 证明留证文字确实存在（否则剥不剥都一样，判据退化成空转）
        - code 无命中 ⇒ 证明剥离真的起作用

        若哪天留证文字被删掉，raw 侧断言会打红提醒 —— 那段记载是防回退资产。
        """
        raw = self._legacy_src()
        code = _code_level_source(raw)
        witness = "BS-045"
        assert witness in raw, (
            f"扫描面异常：raw 源码里已无 {witness} 留证文字。"
            "该文字是「改写前断言错码」的历史记载，删掉后本自检失去意义"
        )
        assert witness not in code, (
            f"剥离失效：{witness} 仍出现在 code-level 源码里 —— "
            "说明它不在 docstring/注释里，而是真的代码级期望值"
        )
