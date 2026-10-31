"""预设库归一后全量函数名 ⊆ L1 登记名（spec formula-hub-integrity-closure 需求 3.7 · ADR-FHIC-21 · F7）。

改造前（HEAD 00525717f，2026-10-28 现算）：``prefill_formula_mapping.json`` 的 ``cells[].formula`` 含 ``TB_SUM(`` 的格 19 个
（原始文本含 ``"formula":`` 与 ``TB_SUM`` 的行 20 行，多出的第 9 行是 ``usage_guide`` 字段说明、不是公式）→
``convert_prefill_presets()`` 19 条 → ``build_preset_library(custom_entries=[])`` 按 ``(page_key, target_cell)`` 去重后 17 条
（D4「附注披露信息（国企）」的「营业收入合计本期」「营业成本合计本期」与「（上市公司）」同键，page_key 不含 sheet，首个赢）。
改造后三处都是 0：``convert_prefill_presets`` 的 expression 经 ``rename_tb_sum_calls`` 只把函数名 ``TB_SUM`` 读时改为 ``SUM_TB``；
去重键不含 expression，条目数与各来源计数不变（4250 条）。

（a）全量预设 = ``build_preset_library(custom_entries=[])``：夹具清空 DB 自定义缓存与补刷钩子并断言 ``db_custom_entries() == []``；
    旧文件 ``formula_custom_presets.json`` 按代码恒计入（``load_custom_presets()`` 不受 ``custom_entries`` 影响，现 0 条）；
    宽表 MD 预设所在的 ``附注模版/`` 被 .gitignore 忽略、主树与 worktree 都没有，现 0 条。L1 登记名取
    ``formula_engine._REGISTRY.list_all()`` 中 category ≠「自定义」的名字（``_REGISTRY`` 是模块级可变全局，别的用例注册自定义函数
    后不注销会污染 ``known_function_names()``，同 ``test_formula_runtime_zero_regression``），并交叉断言 == ``BUILTIN_FUNCTION_NAMES``。
    prefill 来源严格 ⊆；全量未登记 {来源: 函数名} == 现算冻结的精确集合（只有 check_presets 的 ``SUM``，335 处附注勾稽表达式，
    待决、本段不修也不加白名单），另查每个冻结名仍真实出现（基线不虚高）。
（b）恰两条 prefill 条目含 ``TB_AUX(``，expression 与映射文件对应格的 formula 逐字节相同（``LEGACY_ALIAS_MAP`` 会把它改成取数口径
    不同的 ``AUX``，F7）。
（c）每条 prefill 条目 expression == 原 formula 把 ``TB_SUM(`` 换成 ``SUM_TB(``（前提：真实 formula 里的 TB_SUM 都在引号外、都是左边界
    干净的 ``TB_SUM(`` 调用 ⇒ 朴素替换就是正确答案）；refs == ``_formula_ref_from_expr(原 formula)``；条目数 == JSON 可用格数。
（d）改写函数合成用例（引号、左右边界、``TB_AUX`` / ``AUX``、多处、``TB_SUM (``、大小写、None / 空串）。
（e）映射文件 sha256（LF 归一）== HEAD blob 常量；构建预设库前后磁盘原始字节相等（不写文件）。
纯文件判据，不连库。
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

import pytest

from app.services.formula_arity import BUILTIN_FUNCTION_NAMES
from app.services.formula_engine import _REGISTRY
from app.services.formula_management import preset_library as pl
from app.services.formula_management.function_support_matrix import called_function_names

MAPPING_PATH = pl.DATA_DIR / "prefill_formula_mapping.json"
#: ``git show 00525717f:backend/data/prefill_formula_mapping.json`` 的 sha256（blob 本身是 LF）。仓库 core.autocrlf=true 且
#: .gitattributes 没给本文件 ``eol=lf`` ⇒ Windows 检出的磁盘字节是 CRLF、CI 是 LF，故对 LF 归一后的字节比对。
#: 本常量只证明预设库归一没有改写数据文件；映射文件有意改动（别的 spec）时同步更新。
MAPPING_LF_SHA256 = "198e2846918023d6bfb9343852de611f69b28fe7bd6a66d7e9edd8439b365244"
PREFILL = "prefill_formula_mapping"
#: 全量预设里非 prefill 来源现存的未登记函数名（2026-10-28 现算冻结；待决）。
FROZEN_UNREGISTERED: dict[str, frozenset[str]] = {"check_presets": frozenset({"SUM"})}
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


@pytest.fixture(autouse=True)
def _no_db_custom(monkeypatch):
    monkeypatch.setattr(pl, "_DB_CUSTOM", [])
    monkeypatch.setattr(pl, "_DB_CUSTOM_REFRESHER", None)


def _registered() -> frozenset[str]:
    return frozenset(m["name"] for m in _REGISTRY.list_all() if m.get("category") != "自定义")


def _library() -> list[pl.PresetEntry]:
    assert pl.db_custom_entries() == [], "DB 自定义预设应为空"
    entries, _ = pl.build_preset_library(custom_entries=[])
    return entries


def _all_cells() -> list[tuple[str, dict]]:
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return [((m.get("wp_code") or "").strip(), cell) for m in data["mappings"] for cell in m.get("cells") or []]


def _usable_cells() -> list[tuple[str, dict]]:
    """与 ``convert_prefill_presets`` 同条件：wp_code、cell_ref 去空白后非空，formula 非空。"""
    return [(wp, c) for wp, c in _all_cells() if wp and (c.get("cell_ref") or "").strip() and c.get("formula")]


def _unregistered_by_source(entries: list[pl.PresetEntry]) -> dict[str, Counter]:
    registered = _registered()
    found: dict[str, Counter] = {}
    for e in entries:
        for name in called_function_names(e.expression):
            if name not in registered:
                found.setdefault(e.source, Counter())[name] += 1
    return found


# ── （a）函数名 ⊆ L1 登记名 ──────────────────────────────────────────────────
def test_registry_api_names_equal_builtin_names():
    assert _registered() == BUILTIN_FUNCTION_NAMES
    assert BUILTIN_FUNCTION_NAMES <= _REGISTRY.known_function_names()


def test_prefill_presets_only_call_registered_functions():
    entries = _library()
    prefill = [e for e in entries if e.source == PREFILL]
    assert prefill, "全量预设里没有 prefill 来源（判据空转）"
    stray = sorted({(e.page_key, e.target_cell, n) for e in prefill for n in called_function_names(e.expression)
                    if n not in _registered()})
    assert stray == [], f"prefill 预设调用了 L1 未登记的函数：{stray}"
    tb_sum = [(e.source, e.page_key, e.target_cell) for e in entries if "TB_SUM" in called_function_names(e.expression)]
    assert tb_sum == [], f"全量预设仍有 TB_SUM（改造前 17 条，应为 0）：{tb_sum}"


def test_full_library_unregistered_names_equal_frozen():
    found = {source: frozenset(names) for source, names in _unregistered_by_source(_library()).items()}
    assert found == FROZEN_UNREGISTERED, f"全量未登记函数名 {found} ≠ 冻结 {FROZEN_UNREGISTERED}（新增的不许悄悄放行）"


def test_frozen_unregistered_names_still_occur():
    found = _unregistered_by_source(_library())
    gone = sorted((s, n) for s, names in FROZEN_UNREGISTERED.items() for n in names if found.get(s, Counter())[n] == 0)
    assert gone == [], f"冻结名已不再出现，请从 FROZEN_UNREGISTERED 删除：{gone}"


# ── （b）两条 TB_AUX 预设不变 ────────────────────────────────────────────────
def test_two_tb_aux_presets_keep_formula_bytes():
    oracle = {(f"workpaper:{wp}", c["cell_ref"].strip()): c["formula"] for wp, c in _usable_cells()
              if "TB_AUX(" in c["formula"]}
    assert len(oracle) == 2 and sum("TB_AUX(" in (c.get("formula") or "") for _, c in _all_cells()) == 2
    groups = {"convert": pl.convert_prefill_presets(), "library": [e for e in _library() if e.source == PREFILL]}
    for label, entries in groups.items():
        hits = {e.dedup_key(): e.expression for e in entries if "TB_AUX(" in (e.expression or "")}
        assert sorted(hits) == sorted(oracle), f"{label}：应恰两条含 TB_AUX( 的 prefill 条目，实得 {hits}"
        for key, expression in hits.items():
            assert expression.encode("utf-8") == oracle[key].encode("utf-8"), f"{label} {key}: {expression!r}"


# ── （c）逐条：expression = 原 formula 只改 TB_SUM 函数名；refs 不变 ─────────
def test_prefill_expression_is_formula_with_tb_sum_renamed():
    cells = _usable_cells()
    formulas = [c["formula"] for _, c in cells]
    in_quotes = [f for f in formulas if any("TB_SUM" in q for q in _QUOTED.findall(f))]
    assert in_quotes == [], f"前提不成立：真实 formula 有位于引号内的 TB_SUM {in_quotes}"
    loose = [f for f in formulas if f.count("TB_SUM") != len(re.findall(r"(?<![A-Za-z0-9_])TB_SUM\(", f))]
    assert loose == [], f"前提不成立：有不是「左边界干净的 TB_SUM(」的 TB_SUM {loose}"
    assert any("TB_SUM(" in f for f in formulas), "真实 formula 没有 TB_SUM（改名判据空转）"
    entries = pl.convert_prefill_presets()
    assert len(entries) == len(cells)
    for (wp, cell), e in zip(cells, entries, strict=True):
        assert (e.page_key, e.target_cell) == (f"workpaper:{wp}", cell["cell_ref"].strip())
        assert e.expression == cell["formula"].replace("TB_SUM(", "SUM_TB("), (e.page_key, e.target_cell, e.expression)
        assert e.refs == pl._formula_ref_from_expr(cell["formula"]), (e.page_key, e.target_cell)


# ── （d）改写函数合成用例 ────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        pytest.param("=TB_SUM('1401~1499','期末余额')", "=SUM_TB('1401~1499','期末余额')", id="basic"),
        pytest.param("='TB_SUM(x)'", "='TB_SUM(x)'", id="single_quoted"),
        pytest.param('="TB_SUM("', '="TB_SUM("', id="double_quoted"),
        pytest.param("=TB_SUM('a~b','TB_SUM(')+\"TB_SUM(\"", "=SUM_TB('a~b','TB_SUM(')+\"TB_SUM(\"", id="mixed_quoted"),
        pytest.param("=MY_TB_SUM('a~b','x')", "=MY_TB_SUM('a~b','x')", id="identifier_prefix"),
        pytest.param("=TB_SUMX('a~b','x')", "=TB_SUMX('a~b','x')", id="identifier_suffix"),
        pytest.param("=1TB_SUM('a~b','x')", "=1TB_SUM('a~b','x')", id="digit_left"),
        pytest.param("=TB_AUX('1121','客户','期末余额')", "=TB_AUX('1121','客户','期末余额')", id="tb_aux"),
        pytest.param("=AUX('1122','客户','期末余额')", "=AUX('1122','客户','期末余额')", id="aux"),
        pytest.param("=TB_SUM('a~b','x')-TB_SUM('c~d','y')+TB('1001','z')",
                     "=SUM_TB('a~b','x')-SUM_TB('c~d','y')+TB('1001','z')", id="multiple"),
        pytest.param("=TB_SUM ('a~b','x')", "=SUM_TB ('a~b','x')", id="space_before_paren"),
        pytest.param("=tb_sum('a~b','x')", "=tb_sum('a~b','x')", id="lowercase"),
        pytest.param("=TB_SUM+1", "=TB_SUM+1", id="not_a_call"),
        pytest.param(None, None, id="none"),
        pytest.param("", "", id="empty"),
    ],
)
def test_rename_tb_sum_calls(expression, expected):
    assert pl.rename_tb_sum_calls(expression) == expected


# ── （e）映射文件字节不变 ────────────────────────────────────────────────────
def test_mapping_file_bytes_unchanged():
    before = MAPPING_PATH.read_bytes()
    assert hashlib.sha256(before.replace(b"\r\n", b"\n")).hexdigest() == MAPPING_LF_SHA256
    pl.convert_prefill_presets()
    _library()
    assert MAPPING_PATH.read_bytes() == before, "构建预设库改写了映射文件"
