"""跨循环「wp_code → 报表行」索引守卫。

Feature: procedure-trim-report-line-account-resolution — Task 1（Wave 1 打红）
Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 7.1
Validates: Property 1（零新增映射知识）, Property 2（交叉锁死）,
           Property 3（无落点与不适用两态可区分）, Property 5（wp_code 归一）

═══ 断言分两类（防「全红分不清是功能未做还是守卫写坏」）═══

- **类 A = 独立口径判据**：本文件自己从 ``four_table`` per-cycle 声明读出的 ``row_code``
  实际取值、真实库 ``report_config`` 的行存在性、真实库 ``procedure_instances.wp_code``
  的 distinct 形态、剥注释 helper 的反向自检。**现在就应全绿**，绿了才证明判据基础设施
  有效而非空转。
- **类 B = 被测实现**：``report_line_index`` 模块的存在与行为。**Task 4 之前应全红**，
  失败消息写明「尚未实现（Task 4）」。

🔴 **类 A 一律动态读取，不冻结字面量清单。** 并发会话正在改 ``d_cycle_specs`` /
``g_cycle_specs`` / ``i_cycle_specs`` / ``k_cycle_specs`` / ``m_cycle_specs``（本轮
``git status`` 实测 M 状态），若守卫把 ``row_code`` 抄成硬编码基线，别人改一个号本文件
就假红。交叉锁死的正确形态是「守卫从 per-cycle 读一侧、索引从 dispatch 取另一侧、两侧
比对」—— 任一侧单独改动即打红，两侧同时跟随则恒绿。

🔴 禁在模块顶层 import 生产模块 —— 顶层 import 失败会让整个文件 collection error、
零断言执行，那时"全红"既可能是功能没做也可能是守卫写坏。改为测试内 try-import 后
``pytest.fail``（不是 skip）。

═══ 真实库实证（2026-08-15，只读）═══

- per-cycle 声明共覆盖 **81 个 wp_code**（D7 E1 F5 G14 H10 I6 J2 K13 L8 M10 N5），
  其中 ``row_code is None`` 的有 5 个：``G2`` ``G3`` ``H5`` ``L2`` ``L6``
  —— 它们是 Property 3「无报表行落点」的真实样本，不是缺陷。
- ``procedure_instances`` 有 **332 个 distinct wp_code**，其中 **19 个区间型**
  （``D2-1至D2-4`` / ``E1-14至E1-15`` / ``F2-1至F2-14`` …），
  **0 个**不可按「字母段 + 数字段」归一。
- **已知实证：J 循环声明的 row_code 与循环语义不符**（本 spec 不修，登记独立议题）——
  ``J1.row_code_listed = BS-051`` 而 ``report_config`` 的 ``BS-051`` 行名是
  **持有待售负债**（公式 ``TB('2245')``）；``J1.row_code_soe = BS-069`` 行名是
  **非流动负债合计**且公式全为 ``ROW()`` 引用。索引「零字面量委托取值」故会如实取到
  这两个号 —— 索引本身正确（它就该跟随声明），金额侧则由 Property 9 的 ``ROW()``
  拒解析接住 soe 侧、由 ``row_name`` 溯源（R6.1）让审计师看见 listed 侧的行名不符。
"""
from __future__ import annotations

import ast
import asyncio
import io
import re
import tokenize
from pathlib import Path

import pytest
import sqlalchemy as sa

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_INDEX_PATH = _BACKEND / "app" / "services" / "four_table" / "report_line_index.py"
_FRONTEND_TRIM_VUE = (
    _BACKEND.parent / "audit-platform" / "frontend" / "src" / "views" / "ProcedureTrimming.vue"
)

#: 报表行编码字面量形态（本文件用于「零字面量」检测，也用于形态校验）
_ROW_CODE_LITERAL_RE = re.compile(r"\b(?:BS|IS|IMP)-\d+\b")

_NOT_IMPLEMENTED = "尚未实现（Task 4）。本条红是预期的 Wave 1 打红结果"


# ═══════════════════════════════════════════════════════════════════════════
# 剥注释 helper（判据必须落在**代码**上，不能被 docstring / 注释里的说明文字骗）
# ═══════════════════════════════════════════════════════════════════════════
def _strip_py_comments(src: str) -> str:
    """只剥 ``#`` 注释，**保留**普通字符串字面量。"""
    spans: list[tuple[int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((tok.start[0], tok.start[1]))
    except tokenize.TokenError:  # pragma: no cover
        return src
    lines = src.splitlines()
    for row, col in spans:
        if 1 <= row <= len(lines):
            lines[row - 1] = lines[row - 1][:col]
    return "\n".join(lines)


def _code_only(src: str) -> str:
    """剥 ``#`` 注释 **与全部 docstring**，保留普通字符串字面量。

    🔴 为什么必须剥 docstring：索引模块的 docstring **会**写着「``BS-002``」之类的
    示例与实证留痕，裸 ``_ROW_CODE_LITERAL_RE.search(src)`` 会把这些**说明文字**数成
    真实写死的码 ⇒ 零字面量判据在正确实现上打红。

    🔴 为什么**不能**顺手把普通字符串字面量也剥掉：那样「真的写死了 ``row_code = "BS-002"``」
    也查不出来，判据从假红变成假绿。区分办法 = 只把「作为语句独占一行的字符串表达式」
    （即 docstring）当注释处理。
    """
    no_comment = _strip_py_comments(src)
    try:
        tree = ast.parse(no_comment)
    except SyntaxError:  # pragma: no cover
        return no_comment
    lines = no_comment.splitlines()
    blank: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
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
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                blank.add(ln)
    return "\n".join("" if (i + 1) in blank else ln for i, ln in enumerate(lines))


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-0：剥注释 helper 与零字面量检测器的反向自检（现在应绿）
# ═══════════════════════════════════════════════════════════════════════════
def test_code_only_strips_docstrings_but_keeps_string_literals():
    """🔴 ``_code_only`` 双向自检：剥 docstring、保留普通字符串字面量。"""
    sample = '''
"""模块 docstring 举例说明 BS-002 是货币资金行。"""
MAPPING = {"note": "IS-001 营业收入"}


def f():
    """函数 docstring 也提到 IMP-008。"""
    return MAPPING
'''
    code = _code_only(sample)
    assert "BS-002" not in code, "docstring 未被剥除 —— 说明文字会被数成真实写死的码"
    assert "IMP-008" not in code, "函数 docstring 未被剥除"
    assert "IS-001" in code, (
        "普通字符串字面量被误剥 —— 那样真的写死 row_code 也查不出来（假绿）"
    )


def test_row_code_literal_detector_is_not_a_no_op():
    """🔴 零字面量检测器反向自检：raw 侧命中数必须 > clean 侧。

    若两侧命中数相等，说明 ``_code_only`` 什么都没剥（或检测正则失效），
    那么「索引零字面量」这条判据就是空转 —— 无论索引写死多少个码它都会绿。
    """
    sample = '''
"""docstring 里出现 BS-002 / BS-006 / IS-001 三个码作为说明。"""
X = 1
'''
    raw_hits = len(_ROW_CODE_LITERAL_RE.findall(sample))
    clean_hits = len(_ROW_CODE_LITERAL_RE.findall(_code_only(sample)))
    assert raw_hits == 3, f"检测正则未命中预期的 3 个码，实得 {raw_hits}"
    assert clean_hits == 0, f"剥注释后仍命中 {clean_hits} 个 —— 剥除逻辑失效"
    assert raw_hits > clean_hits, "raw 与 clean 命中数相同 ⇒ 零字面量判据是空转"


def test_row_code_literal_detector_catches_real_hardcode():
    """🔴 正向自检：真的写死在代码里（非 docstring）必须被抓到。"""
    sample = '''
"""模块说明。"""
ROW_CODES = {"D2": "BS-006"}
'''
    clean = _code_only(sample)
    assert _ROW_CODE_LITERAL_RE.search(clean), (
        "写死在代码里的 row_code 未被检测到 —— 判据是假绿"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-1：per-cycle 声明的实际取值（动态读取，不冻结字面量）
# ═══════════════════════════════════════════════════════════════════════════
def _percycle_declarations() -> dict[str, dict]:
    """从 ``four_table`` 既有 per-cycle 声明动态读出 ``{wp_code: {...}}``。

    这是交叉锁死的**独立一侧** —— 与索引的 dispatch 各走各的路径读同一批常量。
    返回项含 ``row_code``（可为 ``None``）与 ``source_symbol``（期望的溯源字符串）。
    """
    try:
        from app.services.four_table import (
            d_cycle_specs,
            e_cycle_specs,
            f_cycle_specs,
            g_cycle_specs,
            h_cycle_specs,
            i_cycle_accounts,
            i_cycle_specs,
            j_cycle_account_scope,
            k_cycle_specs,
            l_cycle_specs,
            m_cycle_specs,
            n_cycle_specs,
        )
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import four_table per-cycle 声明模块: {e!r}")

    out: dict[str, dict] = {}

    # 无准则维度的循环：spec_of 风格的注册表
    for mod_name, registry, mod in (
        ("d_cycle_specs", "D_CYCLE_SPECS", d_cycle_specs),
        ("f_cycle_specs", "F_CYCLE_SPECS", f_cycle_specs),
        ("g_cycle_specs", "G_CYCLE_SPECS", g_cycle_specs),
        ("h_cycle_specs", "H_CYCLE_SPECS", h_cycle_specs),
        ("i_cycle_specs", "I_CYCLE_SPECS", i_cycle_specs),
        ("l_cycle_specs", "L_CYCLE_SPECS", l_cycle_specs),
        ("m_cycle_specs", "M_CYCLE_SPECS", m_cycle_specs),
        ("n_cycle_specs", "N_CYCLE_SPECS", n_cycle_specs),
    ):
        for code, spec in getattr(mod, registry).items():
            out[str(code).upper()] = {
                "row_code": getattr(spec, "row_code", None),
                "module": mod_name,
                "standard_aware": False,
            }

    # E：模块级常量（四准则一致，已实证）
    out["E1"] = {
        "row_code": e_cycle_specs.E1_REPORT_ROW_CODE,
        "module": "e_cycle_specs",
        "standard_aware": False,
    }

    # I：row_code 有准则维度（既有件 resolve_row_code 已处理）
    for code in i_cycle_accounts.I_CYCLE_ROW_CODES:
        cu = str(code).upper()
        out[cu] = {
            "row_code": i_cycle_accounts.resolve_row_code(cu, ["listed_consolidated"]),
            "row_code_soe": i_cycle_accounts.resolve_row_code(cu, ["soe_consolidated"]),
            "module": "i_cycle_accounts",
            "standard_aware": True,
        }

    # J：SPEC_BY_ENTITY + pick_spec（既有件已处理准则）
    for code, table in (
        ("J1", j_cycle_account_scope.J1_SPEC_BY_ENTITY),
        ("J2", j_cycle_account_scope.J2_SPEC_BY_ENTITY),
    ):
        out[code] = {
            "row_code": j_cycle_account_scope.pick_spec(
                table, ["listed_consolidated"]
            ).row_code,
            "row_code_soe": j_cycle_account_scope.pick_spec(
                table, ["soe_consolidated"]
            ).row_code,
            "module": "j_cycle_account_scope",
            "standard_aware": True,
        }

    # K：KCycleSpec 双字段
    for code, spec in k_cycle_specs.K_CYCLE_SPECS.items():
        out[str(code).upper()] = {
            "row_code": spec.row_code_listed,
            "row_code_soe": spec.row_code_soe,
            "module": "k_cycle_specs",
            "standard_aware": True,
        }

    return out


def test_percycle_declarations_are_readable_and_well_formed():
    """类 A：11 个循环的声明可读，且 ``row_code`` 形态合法或显式为 ``None``。"""
    decls = _percycle_declarations()
    letters = {code[0] for code in decls}
    assert letters == set("DEFGHIJKLMN"), (
        f"per-cycle 声明覆盖的循环字母与预期不符：实得 {sorted(letters)}"
    )
    assert len(decls) >= 70, f"声明总数异常偏少（{len(decls)}）—— 可能某注册表 import 失败"

    bad: list[str] = []
    for code, info in sorted(decls.items()):
        rc = info["row_code"]
        if rc is None or rc == "":
            continue  # 「无报表行落点」是合法状态（G2/G3/H5/L2/L6）
        if not _ROW_CODE_LITERAL_RE.fullmatch(str(rc)):
            bad.append(f"{code}={rc!r}")
    assert not bad, f"以下声明的 row_code 形态非法（应形如 BS-006 / IS-001）：{bad}"


def test_percycle_declarations_include_none_row_code_samples():
    """类 A：确实存在 ``row_code is None`` 的循环（Property 3 的真实样本来源）。

    若这条转绿失败（一个 None 都没有），说明 Property 3 的「无落点」态在真实声明里
    找不到样本 ⇒ 索引的该分支无法用生产数据验证，须改用构造码验证并在此登记。
    """
    decls = _percycle_declarations()
    nones = sorted(c for c, i in decls.items() if not i["row_code"])
    assert nones, (
        "per-cycle 声明里没有任何 row_code 为空的项 —— "
        "Property 3「无报表行落点」失去真实样本，须改用未登记码验证"
    )


def test_percycle_standard_variance_exists():
    """类 A：至少一个循环的 ``row_code`` **按准则不同**（准则维度真实存在的证据）。

    实证 J1（``listed=BS-051`` / ``soe=BS-069``）与 J2（``BS-067`` / ``BS-093``）。
    若这条打红，说明准则维度已被上游收敛成同号 ⇒ Property 10 需改用公式差异验证
    （``BS-006`` 的四变体公式不同，那条在 Task 2 覆盖）。
    """
    decls = _percycle_declarations()
    diverging = sorted(
        code
        for code, i in decls.items()
        if i.get("standard_aware") and i.get("row_code") != i.get("row_code_soe")
    )
    assert diverging, (
        "没有任何循环的 row_code 按准则变体不同 —— 准则维度判据失去真实样本"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-2：前端归一正则字面量（供与后端 normalize_wp_code 交叉锁死）
# ═══════════════════════════════════════════════════════════════════════════
def test_frontend_subject_prefix_regex_literal_is_extractable():
    """类 A：能从 ``ProcedureTrimming.vue`` 抽出 ``subjectPrefixOf`` 的归一正则。

    两侧语言不同无法共享实现 ⇒ 用交叉锁死兜住。本条只保证「锚点抽得到」；
    真正的两侧结果逐个相等在前端守卫（Task 3）与索引守卫（下方类 B）双向断言。
    """
    assert _FRONTEND_TRIM_VUE.exists(), f"前端裁剪页不存在：{_FRONTEND_TRIM_VUE}"
    src = _FRONTEND_TRIM_VUE.read_text(encoding="utf-8")
    m = re.search(r"function\s+subjectPrefixOf[\s\S]{0,400}?\.match\((/[^/]+/)\)", src)
    assert m, "未能在 subjectPrefixOf 函数体内抽到 .match(<正则>) —— 锚点已漂移"
    assert m.group(1) == "/^([A-Z]+\\d+)/", (
        f"前端归一正则已变为 {m.group(1)} —— 后端 normalize_wp_code 须同步（交叉锁死）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-3：连库判据（现在应绿）
#
# 🔴 一次 asyncio.run 取完全部快照 + 专用 NullPool 引擎：连接池绑定首个事件循环，
#    每个测试各自 async 会让第二个起报 "Event loop is closed"；借共享池会双向污染。
# ═══════════════════════════════════════════════════════════════════════════
_LIVE_SQL = """
SELECT
  (SELECT count(DISTINCT wp_code) FROM procedure_instances
     WHERE wp_code IS NOT NULL AND btrim(wp_code) <> '')                AS pi_distinct,
  (SELECT count(DISTINCT wp_code) FROM procedure_instances
     WHERE wp_code IS NOT NULL AND btrim(wp_code) <> ''
       AND wp_code !~ '^[A-Z]+[0-9]+')                                  AS pi_not_normalizable,
  (SELECT count(DISTINCT wp_code) FROM procedure_instances
     WHERE wp_code ~ '至')                                              AS pi_range_form
"""

_LIVE_RANGE_SAMPLES_SQL = """
SELECT DISTINCT wp_code FROM procedure_instances
WHERE wp_code ~ '至' ORDER BY wp_code LIMIT 30
"""

_LIVE_ROW_CODE_SQL = """
SELECT row_code, applicable_standard, row_name, formula
FROM report_config
WHERE row_code = ANY(:codes) AND is_deleted = false
"""


def _live_snapshot(row_codes: list[str]):
    """一次取完连库判据需要的全部快照；库不可达则 skip（本组是连库判据）。"""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                counts = dict(
                    (await conn.execute(sa.text(_LIVE_SQL))).one()._mapping
                )
                ranges = [
                    r[0]
                    for r in (await conn.execute(sa.text(_LIVE_RANGE_SAMPLES_SQL))).all()
                ]
                cfg_rows = [
                    dict(r._mapping)
                    for r in (
                        await conn.execute(
                            sa.text(_LIVE_ROW_CODE_SQL), {"codes": row_codes}
                        )
                    ).all()
                ]
            return {"counts": counts, "ranges": ranges, "config": cfg_rows}
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"真实库不可达（本组为连库判据）: {e!r}")


@pytest.fixture(scope="module")
def live():
    decls = _percycle_declarations()
    codes = sorted({str(i["row_code"]) for i in decls.values() if i["row_code"]})
    codes += sorted(
        {str(i["row_code_soe"]) for i in decls.values() if i.get("row_code_soe")}
    )
    return _live_snapshot(sorted(set(codes)))


def test_live_wp_codes_are_all_prefix_normalizable(live):
    """类 A（R1.7）：真实库全部 ``wp_code`` 都能按「字母段 + 数字段」归一。"""
    c = live["counts"]
    assert c["pi_distinct"] > 0, "procedure_instances 无任何 wp_code —— 无法验证归一覆盖面"
    assert c["pi_not_normalizable"] == 0, (
        f"真实库有 {c['pi_not_normalizable']} 个 wp_code 不以「字母+数字」开头 ⇒ "
        "归一规则覆盖不全，须扩展 normalize_wp_code 并在此登记新形态"
    )
    assert c["pi_range_form"] > 0, (
        "真实库无区间型 wp_code —— R1.7 的立项事实已消失，须复核该需求是否仍有效"
    )


def test_live_range_form_samples_are_recognizable(live):
    """类 A：区间型样本形态可识别（``X{n}-a至X{n}-b``），且首段就是底稿主码。"""
    samples = live["ranges"]
    assert samples, "未取到区间型样本"
    bad = [s for s in samples if not re.match(r"^[A-Z]+\d+-\d+至[A-Z]+\d+-\d+$", s)]
    assert not bad, f"以下区间型 wp_code 形态超出已登记范式，须扩展归一规则：{bad}"


def test_live_percycle_row_codes_exist_in_report_config(live):
    """类 A（R1.5）：per-cycle 声明的每个 ``row_code`` 在 ``report_config`` 真实存在。"""
    decls = _percycle_declarations()
    declared = {str(i["row_code"]) for i in decls.values() if i["row_code"]}
    declared |= {str(i["row_code_soe"]) for i in decls.values() if i.get("row_code_soe")}
    present = {str(r["row_code"]) for r in live["config"]}
    missing = sorted(declared - present)
    assert not missing, (
        f"以下 per-cycle 声明的 row_code 在 report_config 不存在：{missing} ⇒ "
        "索引会取到一个查不到公式的号，金额恒 formula_unavailable"
    )


def test_live_report_config_standard_variants_are_four(live):
    """类 A：``report_config`` 的准则变体取值域恰为四个（R3.1 的口径基础）。"""
    stds = {str(r["applicable_standard"]) for r in live["config"]}
    assert stds == {
        "listed_consolidated",
        "listed_standalone",
        "soe_consolidated",
        "soe_standalone",
    }, f"准则变体取值域与预期不符：{sorted(stds)}"


# ═══════════════════════════════════════════════════════════════════════════
# 类 B：被测实现（Task 4 之前应全红）
# ═══════════════════════════════════════════════════════════════════════════
def _index_mod():
    """测试内 import；失败 ``fail`` 而非 skip（skip 会让缺陷静默）。"""
    try:
        from app.services.four_table import report_line_index as mod
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import four_table.report_line_index —— {_NOT_IMPLEMENTED}: {e!r}")
    return mod


def test_index_module_exports_contract():
    """类 B（R1.1）：模块导出约定接口。"""
    mod = _index_mod()
    for name in (
        "ReportLineRef",
        "resolve_report_line_ref",
        "normalize_wp_code",
        "indexed_wp_codes",
        "NON_BALANCE_DRIVEN_CYCLES",
        "REF_RESOLVED",
        "REF_NO_REPORT_LINE",
        "REF_NON_BALANCE_DRIVEN",
    ):
        assert hasattr(mod, name), f"未导出 {name} —— {_NOT_IMPLEMENTED}"


def test_index_module_has_zero_row_code_literals():
    """类 B（R1.2 / Property 1）：索引**代码**里零 ``BS-*``/``IS-*``/``IMP-*`` 字面量。

    写死一个就是双真源 —— 某循环改了报表行号索引不跟随，而两侧各自的单测都全绿
    （各用自己的常量构造样本）。docstring 与 ``#`` 注释里写码是允许的（说明与实证留痕），
    故判据落在 ``_code_only`` 之后的代码上。
    """
    assert _INDEX_PATH.exists(), f"索引模块不存在：{_INDEX_PATH} —— {_NOT_IMPLEMENTED}"
    code = _code_only(_INDEX_PATH.read_text(encoding="utf-8"))
    hits = sorted(set(_ROW_CODE_LITERAL_RE.findall(code)))
    assert not hits, (
        f"索引代码里写死了报表行编码 {hits} —— 必须 getattr 从 per-cycle 声明取值"
    )


def test_index_cross_locked_with_percycle_declarations():
    """类 B（R1.6 / Property 2）：索引取值与 per-cycle 声明**逐字相等**。

    这是本 spec 最核心的一条守卫：任一侧改动而另一侧未跟进即打红。
    """
    mod = _index_mod()
    decls = _percycle_declarations()
    mismatch: list[str] = []
    for code, info in sorted(decls.items()):
        ref = mod.resolve_report_line_ref(code, ["listed_consolidated"])
        expected = info["row_code"] or ""
        actual = getattr(ref, "row_code", None) or ""
        if actual != expected:
            mismatch.append(f"{code}: 索引={actual!r} 声明={expected!r}")
    assert not mismatch, (
        f"索引与 per-cycle 声明的 row_code 不一致（共 {len(mismatch)} 处）：{mismatch[:10]}"
    )


def test_index_cross_locked_under_soe_standard():
    """类 B（R1.6 / Property 10）：国企准则下同样与声明逐字相等。"""
    mod = _index_mod()
    decls = _percycle_declarations()
    mismatch: list[str] = []
    for code, info in sorted(decls.items()):
        expected = (
            info.get("row_code_soe") if info.get("standard_aware") else info["row_code"]
        ) or ""
        ref = mod.resolve_report_line_ref(code, ["soe_consolidated"])
        actual = getattr(ref, "row_code", None) or ""
        if actual != expected:
            mismatch.append(f"{code}: 索引={actual!r} 声明={expected!r}")
    assert not mismatch, (
        f"soe 准则下索引与声明不一致（共 {len(mismatch)} 处）：{mismatch[:10]}"
    )


def test_index_coverage_matches_percycle_registry():
    """类 B（R1.1）：``indexed_wp_codes()`` 恰好覆盖 per-cycle 全部登记码。

    多了 = 索引自己造了映射知识；少了 = 某循环漏接。
    """
    mod = _index_mod()
    indexed = {str(c).upper() for c in mod.indexed_wp_codes()}
    declared = set(_percycle_declarations())
    assert not (declared - indexed), f"索引漏接以下声明：{sorted(declared - indexed)}"
    assert not (indexed - declared), (
        f"索引多出以下 per-cycle 声明里不存在的码（自造映射知识）：{sorted(indexed - declared)}"
    )


def test_index_non_balance_driven_cycles_are_distinguishable():
    """类 B（R1.4 / Property 3）：A/B/C/S 返「不适用」而非「无落点」。

    两态混同会让「这个循环压根不看科目余额」与「这个底稿没登记报表行」不可区分 ——
    前者是设计如此，后者是待补的映射。
    """
    mod = _index_mod()
    assert set(mod.NON_BALANCE_DRIVEN_CYCLES) == {"A", "B", "C", "S"}, (
        f"不适用循环集合与 decideTrim 的 BALANCE_DRIVEN_CYCLES 补集不一致："
        f"{sorted(mod.NON_BALANCE_DRIVEN_CYCLES)}"
    )
    for code in ("A1", "B50", "C21", "S3", "A14-2", "B1-1"):
        ref = mod.resolve_report_line_ref(code)
        assert ref.status == mod.REF_NON_BALANCE_DRIVEN, (
            f"{code} 的状态为 {ref.status!r}，应为 REF_NON_BALANCE_DRIVEN"
        )
        assert not ref.row_code, f"{code} 不适用却带了 row_code={ref.row_code!r}"


def test_index_unregistered_balance_driven_code_returns_no_report_line():
    """类 B（R1.3 / Property 3）：D~N 未登记码返「无落点」+ reason 非空，不抛异常。"""
    mod = _index_mod()
    for code in ("D99", "N88", "K77"):
        ref = mod.resolve_report_line_ref(code)
        assert ref.status == mod.REF_NO_REPORT_LINE, (
            f"{code} 的状态为 {ref.status!r}，应为 REF_NO_REPORT_LINE"
        )
        assert ref.row_code == "", f"{code} 未登记却带了 row_code={ref.row_code!r}"
        assert str(ref.reason or "").strip(), f"{code} 无落点但 reason 为空 —— 成因不可追溯"


def test_index_declared_none_row_code_returns_no_report_line():
    """类 B（R1.3）：声明里 ``row_code is None`` 的底稿（G2/G3/H5/L2/L6）返「无落点」。

    不得返回空串状态或 ``REF_RESOLVED`` + 空 row_code —— 后者会让金额侧以为解析成功。
    """
    mod = _index_mod()
    decls = _percycle_declarations()
    nones = sorted(c for c, i in decls.items() if not i["row_code"])
    if not nones:
        pytest.skip("per-cycle 声明里已无 row_code 为空的项")
    for code in nones:
        ref = mod.resolve_report_line_ref(code, ["listed_consolidated"])
        assert ref.status == mod.REF_NO_REPORT_LINE, (
            f"{code} 声明 row_code 为空，索引状态却是 {ref.status!r}"
        )
        assert str(ref.reason or "").strip(), f"{code} 无落点但 reason 为空"


def test_index_resolved_refs_carry_source_symbol():
    """类 B（R1.1 / Property 2）：``resolved`` 态必带 ``source_symbol`` 且指向真实模块。

    ``source_symbol`` 既是溯源（这个号从哪来）也是守卫交叉锁死的锚。
    """
    mod = _index_mod()
    decls = _percycle_declarations()
    bad: list[str] = []
    for code, info in sorted(decls.items()):
        if not info["row_code"]:
            continue
        ref = mod.resolve_report_line_ref(code, ["listed_consolidated"])
        sym = str(getattr(ref, "source_symbol", "") or "")
        if not sym:
            bad.append(f"{code}: source_symbol 为空")
        elif info["module"] not in sym:
            bad.append(f"{code}: source_symbol={sym!r} 未指向 {info['module']}")
    assert not bad, f"以下项的溯源标识缺失或指错模块：{bad[:10]}"


def test_index_status_domain_is_exactly_three():
    """类 B（R1.3 / R1.4）：状态取值域恰为三态，且三个常量值互不相同。"""
    mod = _index_mod()
    values = {mod.REF_RESOLVED, mod.REF_NO_REPORT_LINE, mod.REF_NON_BALANCE_DRIVEN}
    assert len(values) == 3, f"三个状态常量有重复值：{values}"
    decls = _percycle_declarations()
    seen = {
        mod.resolve_report_line_ref(c, ["listed_consolidated"]).status for c in decls
    }
    seen |= {mod.resolve_report_line_ref(c).status for c in ("A1", "B50", "D99")}
    assert seen <= values, f"出现取值域外的状态：{sorted(seen - values)}"


def test_normalize_wp_code_handles_range_forms():
    """类 B（R1.7 / Property 5）：区间型与后缀型 wp_code 归一到底稿主码。"""
    mod = _index_mod()
    cases = {
        "D2-1至D2-4": "D2",
        "D2-6至D2-13": "D2",
        "E1-14至E1-15": "E1",
        "E1-1至E1-11": "E1",
        "F2-61至F2-72": "F2",
        "D4-33至D4-36": "D4",
        "H10-3": "H10",
        "K13": "K13",
        "  m1-2  ": "M1",
        "": "",
        "无编号": "",
    }
    bad = []
    for raw, expected in cases.items():
        actual = mod.normalize_wp_code(raw)
        if actual != expected:
            bad.append(f"{raw!r} → {actual!r}（期望 {expected!r}）")
    assert not bad, f"归一结果与期望不符：{bad}"


def test_normalize_wp_code_agrees_with_frontend_regex():
    """类 B（R1.7 / Property 5）：与前端 ``subjectPrefixOf`` 在同一组样本上逐个相等。

    正则字面量从前端 ``.vue`` **现场抽取**（不抄一份），故前端改正则本条即打红。
    """
    mod = _index_mod()
    src = _FRONTEND_TRIM_VUE.read_text(encoding="utf-8")
    m = re.search(r"function\s+subjectPrefixOf[\s\S]{0,400}?\.match\(/([^/]+)/\)", src)
    assert m, "未能抽到前端归一正则 —— 锚点已漂移"
    fe_re = re.compile(m.group(1))

    samples = [
        "D2-1至D2-4", "E1-14至E1-15", "F2-1至F2-14", "H10-3", "K13",
        "A14-2", "B50", "C21-1", "S3-2", "M1-2", "N5",
    ]
    bad = []
    for s in samples:
        fe = (fe_re.match(s.upper()) or [None, ""])[1] if fe_re.match(s.upper()) else ""
        be = mod.normalize_wp_code(s)
        if fe != be:
            bad.append(f"{s!r}: 前端={fe!r} 后端={be!r}")
    assert not bad, f"两侧归一结果不一致（交叉锁死打红）：{bad}"


def test_index_is_pure_and_side_effect_free():
    """类 B：索引是纯函数（同一入参多次调用结果一致，不依赖 IO）。"""
    mod = _index_mod()
    for code in ("D2", "E1", "J1", "K1", "L2", "A1", "D99"):
        a = mod.resolve_report_line_ref(code, ["listed_consolidated"])
        b = mod.resolve_report_line_ref(code, ["listed_consolidated"])
        assert (a.row_code, a.status, a.source_symbol) == (
            b.row_code,
            b.status,
            b.source_symbol,
        ), f"{code} 两次调用结果不同 —— 索引不是纯函数"


def test_index_row_codes_exist_in_report_config(live):
    """类 B（R1.5 / Property 4）：索引产出的每个 ``row_code`` 在真实库存在。"""
    mod = _index_mod()
    present = {str(r["row_code"]) for r in live["config"]}
    missing: list[str] = []
    for code in mod.indexed_wp_codes():
        for stds in (["listed_consolidated"], ["soe_consolidated"]):
            ref = mod.resolve_report_line_ref(code, stds)
            if ref.status == mod.REF_RESOLVED and ref.row_code not in present:
                missing.append(f"{code}({stds[0]})→{ref.row_code}")
    assert not missing, f"索引产出的 row_code 在 report_config 不存在：{sorted(set(missing))}"
