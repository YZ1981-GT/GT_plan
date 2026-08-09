"""差异数据完整性守卫 — note_soe_listed_diff.json 与其消费口径.

spec: soe-listed-note-conversion-correctness

覆盖 **Task 1 + Task 3**（Requirements 1.1 / 1.2 / 1.3 / 1.4 / 1.5 = Property 1~4）：

Task 1 交付（Property 1 / 3）：

* ``TestIsMockFalse``            — 落盘不得再自标 mock
* ``TestStoredMatchesLive``      — 落盘由 ``compute_diff_from_templates`` 派生，逐条相等
* ``TestFormatDiffLocatingKey``  — 钉死「消费方按侧取 sid」这一裁决
* ``TestGeneratorDelegates``     — 生成脚本必须委托 service，禁第二份实现

Task 3 追加（Property 2 / 4 + 两族不变式）：

* ``TestStaleFallsBackToLive``   — Property 2：落盘 stale 时 WARNING + 以实时为准
                                   （覆盖 ``is_mock=true`` 与「条目不一致」两条告警路径，
                                   外加 fail-open 降级路径与「一致时不误报」反向自检）
* ``TestBucketIdentityIsPayloadComplete``
                                 — 条目标识必须**载荷完备**：改 ``format_diff`` 任一
                                   载荷字段（``soe_format`` / ``listed_format`` /
                                   ``field_mapping``）必判不一致
* ``TestAdaptTableDataSemantics`` — Property 4：``field_mapping`` 空 ⇒ 输出逐字等于输入
                                   且 ``reason=no_field_mapping``；非空 ⇒ 结构确实改变。
                                   并钉死四条不变式：
                                     ① ``changed == (输出 != 输入)``（禁自我声明）
                                     ② ``column_remap`` 同时改 ``_columns_meta[].id``
                                        + 行内四个 dict 桶 + ``_cell_provenance`` 键
                                     ③ 列 id 撞车必须跳过而不是产生重复列
                                     ④ ``row_filter`` 剔行后 ``_cell_provenance``
                                        行下标必须重排
* ``TestConsumerCountsOnlyRealAdaptations``
                                 — 消费方 ``format_adapted_count`` 不得把空操作
                                   计为已适配（AST 结构断言 + 反向自检）

------------------------------------------------------------------------------
Property 2 为什么不直接改真实落盘文件
------------------------------------------------------------------------------

``load_diff_data()`` 在调用时读模块全局 ``_DIFF_JSON_PATH``，故 stale 场景一律
**monkeypatch 到 tmp 文件**：既走完全相同的生产代码路径，又不触碰
``backend/data/note_soe_listed_diff.json``（该文件是 5 个 spec 共享的数据真源，
并发会话高频读写）。``TestRealDiffJsonUntouched`` 以「模块导入时 md5 ↔ 运行结束时
md5」的**前后对照**方式核验它未被本文件改动 —— 不冻结 md5 常量，否则模板合法
变更后重生成会让守卫变成假红发生器。

真实文件的字节级改动只发生在**变异检验脚本**里（`.bak` 落磁盘 + ``try/finally``
无条件写回 + md5 核验），不由测试承担。

------------------------------------------------------------------------------
Requirement 1.4 的二选一：本项目选定「消费方改读两侧 sid」
------------------------------------------------------------------------------

依据三条（2026-08-07 实测）：

1. ``format_diff_sections`` 条目**从来没有** ``section_id`` 键 —— 落盘与实时的
   键集均为 ``field_mapping / listed_format / listed_section_id /
   section_title / soe_format / soe_section_id``。而 ``convert_disclosure_notes_v2``
   的 step 6 读的正是 ``fd.get("section_id")`` ⇒ 恒 None ⇒ 整步空转、
   ``format_adapted_count`` 恒 0。
2. 「往数据里补 ``section_id``」要求把一个**运行时才知道的侧向选择**（取 soe 侧
   还是 listed 侧）编码进静态数据，既有歧义又与两侧 sid 构成双真源。
3. 同模块的 ``classify_section_mapping`` 早已按侧取键
   （``id_field = "soe_section_id" if source_type == "soe"``）⇒ 选项 A 与既有
   范式一致，不在同一份数据上引入第二套约定。
"""
from __future__ import annotations

import ast
import copy
import hashlib
import io
import json
import logging
import pathlib
import textwrap
import tokenize

import pytest

from app.services import note_template_diff as diff_mod
from app.services.note_template_diff import (
    ADAPT_REASON_APPLIED,
    ADAPT_REASON_NO_EFFECT,
    ADAPT_REASON_NO_FIELD_MAPPING,
    ADAPT_REASON_UNSUPPORTED_ONLY,
    DECLARED_UNIMPLEMENTED_FIELD_MAPPING_KEYS,
    DIFF_BUCKETS,
    SUPPORTED_FIELD_MAPPING_KEYS,
    adapt_table_data,
    adapt_table_data_with_report,
    compare_diff_payloads,
    compute_diff_from_templates,
    load_diff_data,
    reset_diff_cache,
)


# ---------------------------------------------------------------------------
# 定位仓库/backend 根：双哨兵文件向上查找，禁写死回退级数
# ---------------------------------------------------------------------------

def _find_backend_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for cand in [here.parent, *here.parents]:
        if (cand / "data" / "note_template_soe.json").is_file() and (
            cand / "app" / "services" / "note_template_diff.py"
        ).is_file():
            return cand
    raise AssertionError("未能定位 backend/ 根（缺哨兵文件）")


BACKEND_ROOT = _find_backend_root()
DATA_DIR = BACKEND_ROOT / "data"
DIFF_JSON = DATA_DIR / "note_soe_listed_diff.json"
CONVERSION_SERVICE = BACKEND_ROOT / "app" / "services" / "note_conversion_service.py"
DIFF_SERVICE = BACKEND_ROOT / "app" / "services" / "note_template_diff.py"
GENERATOR = BACKEND_ROOT / "scripts" / "gen" / "generate_note_soe_listed_diff.py"

#: 模块导入时真实落盘文件的 md5 —— 供「前后对照」核验本文件未改动它。
#: 有意**不写死常量**：模板合法变更后重生成会让 md5 改变，冻结即假红。
_DIFF_JSON_MD5_AT_IMPORT = hashlib.md5(DIFF_JSON.read_bytes()).hexdigest()

#: 差异服务的 logger 名（caplog 过滤用）
DIFF_LOGGER = "app.services.note_template_diff"

#: format_diff 条目的合法键集（实测，落盘与实时一致）
EXPECTED_FORMAT_DIFF_KEYS = frozenset({
    "section_title",
    "soe_section_id",
    "listed_section_id",
    "soe_format",
    "listed_format",
    "field_mapping",
})


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_stored() -> dict:
    assert DIFF_JSON.is_file(), f"落盘差异数据缺失: {DIFF_JSON}"
    return json.loads(DIFF_JSON.read_text(encoding="utf-8"))


def _compute_live() -> dict:
    soe = json.loads((DATA_DIR / "note_template_soe.json").read_text(encoding="utf-8"))
    listed = json.loads((DATA_DIR / "note_template_listed.json").read_text(encoding="utf-8"))
    return compute_diff_from_templates(soe.get("sections", []), listed.get("sections", []))


def _strip_comments(source: str) -> str:
    """剥掉 ``#`` 注释（token 级，字符串字面量内的 ``#`` 不受影响）。

    源码级断言必须先剥注释 —— 本 spec 的生产代码在注释里**原样写了**被禁的
    ``fd.get("section_id")`` 作为踩坑说明，不剥注释会让断言恒红。
    """
    lines = source.splitlines(keepends=True)
    spans: list[tuple[int, int, int]] = []  # (1-based row, start col, end col)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((tok.start[0], tok.start[1], tok.end[1]))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # 片段可能缩进/括号不完整 —— 退化为行级剥离（保守，可能误伤字符串内的 #）
        return "".join(line.split("#", 1)[0] + "\n" for line in source.splitlines())

    # 从后往前置空，避免列偏移
    for row, col_start, col_end in sorted(spans, reverse=True):
        idx = row - 1
        line = lines[idx]
        lines[idx] = line[:col_start] + " " * (col_end - col_start) + line[col_end:]
    return "".join(lines)


def _func_source(path: pathlib.Path, name: str) -> str:
    """按 AST 取指定函数/方法的源码片段（含嵌套在类里的）。

    不用「声明后第一个 ``{``/缩进」这类启发式：多行签名与内联类型注解都会让
    那类切法截错块（平台已登记的坑）。
    """
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            start = (node.decorator_list[0].lineno if node.decorator_list else node.lineno) - 1
            end = node.end_lineno or node.lineno
            # 按整行切并 dedent —— 保持各行缩进一致，tokenize 才能正常工作
            return textwrap.dedent("".join(lines[start:end]))
    raise AssertionError(f"{path.name} 中找不到函数 {name}")


# ---------------------------------------------------------------------------
# Task 3 helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_diff_cache():
    """``load_diff_data`` 带模块级缓存 —— 每例前后清一次，避免跨例/跨文件污染。"""
    reset_diff_cache()
    yield
    reset_diff_cache()


def _write_stored(tmp_path: pathlib.Path, payload: dict) -> pathlib.Path:
    path = tmp_path / "note_soe_listed_diff.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and r.name == DIFF_LOGGER
    ]


def _rich_table_data() -> dict:
    """一份**四个行内 dict 桶 + 表级溯源都齐备**的 table_data。

    Invariant ② 的断言必须建立在「桶确实存在」之上，否则是空转 ——
    ``test_fixture_populates_every_remap_target`` 显式钉死这一点。

    ``_cell_provenance`` 的值取可区分标记（``P0``/``P1``/``P2``），Invariant ④
    才能验「行下标重排后值跟着走对了」而不只是「键数量对上了」。
    """
    return {
        "headers": ["项目", "本期"],
        "_columns_meta": [
            {"id": "col_label", "name": "项目"},
            {"id": "col_movement", "name": "本期"},
        ],
        "rows": [
            {
                "row_type": "total",
                "values": {"col_label": "合计", "col_movement": "300"},
                "_cell_modes": {"col_movement": "formula"},
                "_cell_meta": {"col_movement": {"src": "sum"}},
                "_legacy_cells": {"col_movement": "299"},
            },
            {
                "row_type": "data",
                "values": {"col_label": "货币资金", "col_movement": "100"},
                "_cell_modes": {"col_movement": "manual"},
                "_cell_meta": {"col_movement": {"src": "wp", "wp_code": "E1"}},
                "_legacy_cells": {"col_movement": "98"},
            },
            {
                "row_type": "data",
                "values": {"col_label": "应收账款", "col_movement": "200"},
                "_cell_modes": {"col_movement": "manual"},
                "_cell_meta": {"col_movement": {"src": "wp", "wp_code": "D2"}},
                "_legacy_cells": {"col_movement": "197"},
            },
        ],
        "_cell_provenance": {
            "0:col_movement": "P0",
            "1:col_movement": "P1",
            "2:col_movement": "P2",
        },
    }


#: Invariant ② 要覆盖的行内桶（与生产常量交叉锁死，见对应测试）
ROW_BUCKETS = ("values", "_cell_modes", "_cell_meta", "_legacy_cells")


#: 生产代码里 ``format_adapted`` 自增语句的赋值目标（源码形态，双引号）
_FORMAT_ADAPTED_TARGET_SRC = 'result["format_adapted"]'

#: 上者经 ``ast.unparse`` 规范化后的形态。
#:
#: 🔴 **必须由 unparse 派生、不得手写字面量** —— ``ast.unparse`` 会把字符串下标
#: 统一改写成**单引号**（``result["format_adapted"]`` → ``result['format_adapted']``），
#: 直接拿源码形态去比恒不相等 ⇒ 判据静默返回 False、守卫在正确实现上打红。
#: 同族已登记的坑：「守卫判据必须是形态而非字符」。
_FORMAT_ADAPTED_TARGET = ast.unparse(
    ast.parse(_FORMAT_ADAPTED_TARGET_SRC, mode="eval").body
)


def _format_adapt_increments(tree: ast.AST) -> list[ast.AugAssign]:
    """收集全部 ``result["format_adapted"] += 1`` 形态的自增节点。"""
    out: list[ast.AugAssign] = []
    for sub in ast.walk(tree):
        if (
            isinstance(sub, ast.AugAssign)
            and isinstance(sub.op, ast.Add)
            and ast.unparse(sub.target) == _FORMAT_ADAPTED_TARGET
        ):
            out.append(sub)
    return out


def _format_adapt_guard_ok(source: str) -> bool:
    """判据：**每一处** ``result["format_adapted"] += 1`` 都必须位于 ``test`` 为
    ``report.changed`` 的 ``if`` 体内。

    ------------------------------------------------------------------
    为什么比「守卫先于计数」更强
    ------------------------------------------------------------------

    原判据是「``adapted == note.table_data`` 的 ``continue`` 守卫出现在自增之前」
    ——「先于」是**行号偏序**，挡不住「守卫在别的分支里、自增其实没被它包住」，也
    挡不住第二个未受守卫的自增点。新判据把两件事一起钉死：

    * **计数被守卫包住**（不是仅仅「守卫在前面」）；
    * **不得存在第二个未受守卫的自增点**（``len(inside) == len(incs)``）。

    仍然是**条件表达式形态**判据（``ast.unparse(node.test) == "report.changed"``），
    故 ``if False:`` / ``if True:`` 这类变异会让形态不匹配而打红，不会静默逃逸
    （平台已登记的「只断言标识符出现」弱判据坑）。

    用 AST 而非文本匹配的两个理由不变：① 注释天然不进 AST（该函数注释里原样写着
    被禁形态的字样）；② 要判的是结构而非字符。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    incs = _format_adapt_increments(tree)
    if not incs:
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if ast.unparse(node.test) != "report.changed":
            continue
        inside = _format_adapt_increments(node)
        if len(inside) == len(incs):
            return True
    return False


#: 反向自检用替身：有自增但**无** ``report.changed`` 守卫（= 改造前的假成功反馈形态）
_UNCONDITIONAL_COUNT_FIXTURE = textwrap.dedent(
    """
    def probe(plan, notes, tgt_side):
        result = {"format_adapted": 0}
        for src_sid, note in notes.items():
            fd = plan["format_diff"].get(src_sid)
            if fd:
                target_format = (
                    fd.get("listed_format") if tgt_side == "listed" else fd.get("soe_format")
                ) or {}
                field_mapping = fd.get("field_mapping") or {}
                adapted, report = adapt_table_data_with_report(
                    note.table_data, target_format, field_mapping
                )
                note.table_data = adapted
                result["format_adapted"] += 1
        return result
    """
)

#: 反向自检用替身：先自增再判 ``report.changed``（计数未被守卫包住 ⇒ 必须判 False）
_GUARD_AFTER_COUNT_FIXTURE = textwrap.dedent(
    """
    def probe(plan, notes, tgt_side):
        result = {"format_adapted": 0}
        for src_sid, note in notes.items():
            fd = plan["format_diff"].get(src_sid)
            if fd:
                adapted, report = adapt_table_data_with_report(note.table_data, {}, {})
                result["format_adapted"] += 1
                if report.changed:
                    note.table_data = adapted
        return result
    """
)

#: 反向自检用替身：一个自增在守卫内、另一个在守卫外（第二自增点必须被抓到）
_SECOND_UNGUARDED_INCREMENT_FIXTURE = textwrap.dedent(
    """
    def probe(plan, notes, tgt_side):
        result = {"format_adapted": 0}
        for src_sid, note in notes.items():
            fd = plan["format_diff"].get(src_sid)
            if fd:
                adapted, report = adapt_table_data_with_report(note.table_data, {}, {})
                if report.changed:
                    note.table_data = adapted
                    result["format_adapted"] += 1
            else:
                result["format_adapted"] += 1
        return result
    """
)


# ---------------------------------------------------------------------------
# Requirement 1.1 — 去 mock
# ---------------------------------------------------------------------------

class TestIsMockFalse:
    def test_stored_is_not_mock(self):
        stored = _load_stored()
        assert stored.get("is_mock") is False, (
            "note_soe_listed_diff.json 仍标 is_mock —— 重跑 "
            "scripts/gen/generate_note_soe_listed_diff.py"
        )

    def test_live_is_not_mock(self):
        assert _compute_live().get("is_mock") is False

    def test_generator_does_not_hardcode_is_mock_true(self):
        """生成脚本不得自己写 ``is_mock`` 真值（那正是落盘长期自标 mock 的成因）。"""
        body = _strip_comments(_func_source(GENERATOR, "generate_diff"))
        assert '"is_mock": True' not in body
        assert "'is_mock': True" not in body

    def test_reverse_selfcheck_predicate_catches_mock(self):
        """反向自检：同一判据施加于 is_mock=true 的替身必须不通过。"""
        fake = {"is_mock": True}
        assert fake.get("is_mock") is not False


# ---------------------------------------------------------------------------
# Requirement 1.1 — 落盘由实时派生（Task 3 会扩成完整 Property 1）
# ---------------------------------------------------------------------------

class TestStoredMatchesLive:
    def test_bucket_entries_equal(self):
        cmp = compare_diff_payloads(_load_stored(), _compute_live())
        if not cmp["consistent"]:
            detail = "; ".join(
                f"{b}: stored={d['stored_count']} live={d['live_count']}"
                f" only_stored={len(d['only_stored'])} only_live={len(d['only_live'])}"
                for b, d in cmp["buckets"].items()
                if d["only_stored"] or d["only_live"]
            )
            pytest.fail(f"落盘与实时计算不一致，需重跑生成脚本。{detail}")

    def test_all_buckets_present_and_non_empty(self):
        """反向自检：桶都存在且非空，否则上一条断言可能在空集上空转。"""
        stored = _load_stored()
        for bucket in DIFF_BUCKETS:
            entries = stored.get(bucket)
            assert isinstance(entries, list), f"{bucket} 不是 list"
            assert entries, f"{bucket} 为空，判据形同空转"


# ---------------------------------------------------------------------------
# Requirement 1.4 — 定位键裁决：消费方按侧取 sid
# ---------------------------------------------------------------------------

class TestFormatDiffLocatingKey:
    def test_entries_carry_both_side_sids(self):
        for entry in _load_stored()["format_diff_sections"]:
            assert entry.get("soe_section_id"), f"缺 soe_section_id: {entry}"
            assert entry.get("listed_section_id"), f"缺 listed_section_id: {entry}"

    def test_entries_have_no_ambiguous_section_id_key(self):
        """禁止往条目里补 ``section_id``（选项 B 已被否决，见模块 docstring）。"""
        offenders = [
            e.get("section_title")
            for e in _load_stored()["format_diff_sections"]
            if "section_id" in e
        ]
        assert not offenders, (
            "format_diff 条目出现歧义键 section_id（该侧向选择是运行时决定的，"
            f"不得编码进静态数据）: {offenders}"
        )

    def test_entry_key_set_is_frozen(self):
        for entry in _load_stored()["format_diff_sections"]:
            assert set(entry.keys()) == EXPECTED_FORMAT_DIFF_KEYS, (
                f"format_diff 条目键集漂移: {sorted(entry.keys())}"
            )

    def test_consumer_selects_sid_by_side(self):
        """生产代码必须按侧取 sid，且不得读 ``fd["section_id"]``。

        ------------------------------------------------------------------
        标的为什么是 ``_build_section_mapping_plan`` 而不是消费循环
        ------------------------------------------------------------------

        「按侧取 sid」与「按侧取格式」在生产代码里是**两件分离的事**（2026-08-07
        AST 实测）：

        * 取 **sid** 在 :meth:`_build_section_mapping_plan`，形态是
          ``_conversion_side()`` 派生 + **f-string** 拼字段名
          （``src_field = f"{src_side}_section_id"``）—— 不是条件表达式；
        * ``_map_disclosure_notes`` 里的 ``tgt_side == "listed"`` **只用于选格式**
          （``listed_format`` / ``soe_format``）。

        故断言不得把两者合并成一条「``"soe_section_id" if ... else ...``」的条件
        表达式判据 —— 那个形态在生产代码里不存在（历史 v2 实现已于 Task 10 删除）。
        """
        plan_body = _strip_comments(
            _func_source(CONVERSION_SERVICE, "_build_section_mapping_plan")
        )
        map_body = _strip_comments(_func_source(CONVERSION_SERVICE, "_map_disclosure_notes"))

        # 正向：按侧派生 + f-string 拼字段名（两侧都要）
        assert "_conversion_side(current_type)" in plan_body, (
            "_build_section_mapping_plan 未由 current_type 派生源侧"
        )
        assert "_conversion_side(target_type)" in plan_body, (
            "_build_section_mapping_plan 未由 target_type 派生目标侧"
        )
        assert 'f"{src_side}_section_id"' in plan_body, (
            "未见按源侧 f-string 拼 sid 字段名（src_field）"
        )
        assert 'f"{tgt_side}_section_id"' in plan_body, (
            "未见按目标侧 f-string 拼 sid 字段名（tgt_field）"
        )
        # 正向：拼出来的字段名真的被用于从 diff 条目取值
        assert "entry.get(src_field)" in plan_body, "src_field 未被用于取源侧 sid"
        assert "entry.get(tgt_field)" in plan_body, "tgt_field 未被用于取目标侧 sid"
        # format_diff 索引同样按源侧 sid 建键（消费方据此 O(1) 命中）
        assert "format_diff[entry[src_field]] = entry" in plan_body, (
            "format_diff 索引未按源侧 sid 建键"
        )

        # 反向：两处都不得回退到不存在的 fd["section_id"]
        for name, body in (
            ("_build_section_mapping_plan", plan_body),
            ("_map_disclosure_notes", map_body),
        ):
            assert 'fd.get("section_id")' not in body, (
                f"{name} 按 fd.get('section_id') 定位 —— 该键不存在，"
                "会让 format_adapted 恒 0"
            )
            assert 'entry.get("section_id")' not in body or name != "_map_disclosure_notes", (
                f"{name} 按 entry.get('section_id') 定位 format_diff 条目"
            )

        # 消费方按侧选**格式**（与选 sid 分离，不得合并判据）
        assert 'tgt_side == "listed"' in map_body, (
            "_map_disclosure_notes 未按目标侧选择 listed_format / soe_format"
        )

    def test_strip_comments_selfcheck(self):
        """反向自检：剥注释确实在承重。

        ------------------------------------------------------------------
        锚点为什么换成 ``legacy compat``
        ------------------------------------------------------------------

        原锚点 ``fd.get("section_id")`` 在生产代码 raw 里已是 **0 次**（该踩坑说明
        随历史 v2 实现一并删除），拿它做自检等于空转。实测唯一「raw 有 / body 无」
        的等价锚点是 ``legacy compat``：

        * ``_map_disclosure_notes`` **docstring** 里有 1 处（字符串字面量，
          :func:`_strip_comments` 有意不剥）；
        * 新建空章节处的 ``#`` **注释**里有 1 处（必须被剥掉）。

        故 ``raw.count > body.count`` 恒成立，且一旦 ``_strip_comments`` 退化成
        「原样返回」本条立刻打红。
        """
        raw = _func_source(CONVERSION_SERVICE, "_map_disclosure_notes")
        body = _strip_comments(raw)
        needle = "legacy compat"
        assert raw.count(needle) >= 2, (
            f"生产代码里 {needle!r} 的出现次数不足（raw={raw.count(needle)}）—— "
            "该自检依赖「docstring 里 1 处 + # 注释里 1 处」，请另择等价锚点"
        )
        assert raw.count(needle) > body.count(needle), (
            f"_strip_comments 未剥掉 # 注释里的 {needle!r}（raw={raw.count(needle)} "
            f"body={body.count(needle)}）—— 上面几条源码级断言可能只是在原文上空转"
        )
        assert body.count(needle) >= 1, (
            "docstring 里的说明文字被一起剥掉了 —— _strip_comments 不应剥字符串字面量"
        )

    def test_side_lookup_locates_real_entries(self):
        """正向：按侧取键能在真实条目上定位到非空 sid；旧读法恒 None。"""
        entries = _load_stored()["format_diff_sections"]
        for current_type, field in (("soe", "soe_section_id"), ("listed", "listed_section_id")):
            resolved = [e.get(field) for e in entries]
            assert all(resolved), f"current_type={current_type} 下存在定位不到的条目"
        assert all(e.get("section_id") is None for e in entries), (
            "旧读法 fd.get('section_id') 应恒 None（这正是改造前空转的机理）"
        )


# ---------------------------------------------------------------------------
# 生成脚本必须委托 service（禁第二份差异实现）
# ---------------------------------------------------------------------------

class TestGeneratorDelegates:
    def test_generator_imports_service(self):
        src = _strip_comments(GENERATOR.read_text(encoding="utf-8"))
        assert "from app.services.note_template_diff import" in src
        assert "compute_diff_from_templates" in src

    def test_generate_diff_calls_service(self):
        body = _strip_comments(_func_source(GENERATOR, "generate_diff"))
        assert "compute_diff_from_templates(" in body, "generate_diff 未委托 service"

    def test_generator_has_no_duplicate_diff_implementation(self):
        """禁止脚本自带 title 索引 / format 差异判定（改前的第二真源形态）。"""
        src = _strip_comments(GENERATOR.read_text(encoding="utf-8"))
        for banned in ("_build_title_index", "has_format_diff", "content_type"):
            assert banned not in src, (
                f"生成脚本重新实现了差异逻辑（命中 {banned!r}）—— 应委托 "
                "note_template_diff.compute_diff_from_templates"
            )

    def test_generator_data_dir_resolves_to_backend_data(self):
        """脚本移入 scripts/gen/ 后曾指向不存在的 backend/scripts/data。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("_gen_diff_probe", GENERATOR)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.DATA_DIR == DATA_DIR, f"DATA_DIR 解析错: {mod.DATA_DIR}"
        assert mod.SOE_PATH.is_file()
        assert mod.LISTED_PATH.is_file()
        assert mod.OUTPUT_PATH == DIFF_JSON


# ---------------------------------------------------------------------------
# Property 2 / Requirement 1.3 — 落盘 stale 时记 WARNING 且以实时为准
# ---------------------------------------------------------------------------

class TestStaleFallsBackToLive:
    """两条告警路径 + fail-open 降级 + 「一致时不误报」反向自检。

    全部走 monkeypatch 到 tmp 文件，真实落盘文件零改动（见模块 docstring）。
    """

    def test_patch_actually_takes_effect(self, tmp_path, monkeypatch, caplog):
        """反向自检（防空转）：monkeypatch 必须真的改变了 ``load_diff_data`` 的读取源。

        若哪天 ``load_diff_data`` 不再读模块全局 ``_DIFF_JSON_PATH``，本条会先红，
        提醒下面几条 stale 断言已经不再行使真实分支。
        """
        stored = _compute_live()
        stored["common_sections"] = []  # 与实时必然不一致
        path = _write_stored(tmp_path, stored)
        monkeypatch.setattr(diff_mod, "_DIFF_JSON_PATH", path)
        caplog.set_level(logging.WARNING, logger=DIFF_LOGGER)

        load_diff_data()

        msgs = _warnings(caplog)
        assert any(path.name in m for m in msgs), (
            f"未见针对被 patch 文件的告警，patch 可能未生效: {msgs}"
        )

    def test_is_mock_true_triggers_warning_and_live_result(self, tmp_path, monkeypatch, caplog):
        """告警路径 1：落盘自标 ``is_mock`` → WARNING，返回值仍是实时结果。"""
        live = _compute_live()
        stored = copy.deepcopy(live)
        stored["is_mock"] = True
        monkeypatch.setattr(diff_mod, "_DIFF_JSON_PATH", _write_stored(tmp_path, stored))
        caplog.set_level(logging.WARNING, logger=DIFF_LOGGER)

        result = load_diff_data()

        assert result.get("is_mock") is False, "返回值仍带 is_mock ⇒ 用了落盘那份"
        assert any("is_mock" in m for m in _warnings(caplog)), (
            f"落盘标 is_mock 未产生 WARNING: {_warnings(caplog)}"
        )
        for bucket in DIFF_BUCKETS:
            assert result[bucket] == live[bucket]

    def test_entry_mismatch_triggers_warning_and_live_result(self, tmp_path, monkeypatch, caplog):
        """告警路径 2：条目集合不一致 → WARNING（含差异摘要），返回实时结果。"""
        live = _compute_live()
        stored = copy.deepcopy(live)
        stored["common_sections"] = stored["common_sections"][:5]
        monkeypatch.setattr(diff_mod, "_DIFF_JSON_PATH", _write_stored(tmp_path, stored))
        caplog.set_level(logging.WARNING, logger=DIFF_LOGGER)

        result = load_diff_data()

        assert result["common_sections"] == live["common_sections"], (
            "返回的 common_sections 不是实时结果 ⇒ 仍以落盘为准"
        )
        assert len(result["common_sections"]) > 5
        msgs = _warnings(caplog)
        assert any("不一致" in m for m in msgs), f"未见不一致告警: {msgs}"
        assert any("common_sections" in m for m in msgs), (
            f"告警未带差异摘要（应点名具体桶）: {msgs}"
        )

    def test_payload_field_change_also_triggers_warning(self, tmp_path, monkeypatch, caplog):
        """载荷 stale（而非条目增删）同样必须告警 —— 这是 Task 2 强化标识的目的。

        ``adapt_table_data`` 拿 ``*_format`` 当目标格式、拿 ``field_mapping`` 当
        指令，载荷 stale 等于「按旧模板结构去适配新模板」。
        """
        live = _compute_live()
        stored = copy.deepcopy(live)
        assert stored["format_diff_sections"], "format_diff 为空，本例形同空转"
        stored["format_diff_sections"][0]["listed_format"] = {
            "content_type": "table",
            "table_count": 999,
        }
        monkeypatch.setattr(diff_mod, "_DIFF_JSON_PATH", _write_stored(tmp_path, stored))
        caplog.set_level(logging.WARNING, logger=DIFF_LOGGER)

        result = load_diff_data()

        assert result["format_diff_sections"] == live["format_diff_sections"]
        assert any("不一致" in m for m in _warnings(caplog)), (
            f"载荷字段 stale 未被检出: {_warnings(caplog)}"
        )

    def test_consistent_stored_emits_no_mismatch_warning(self, tmp_path, monkeypatch, caplog):
        """反向自检：落盘与实时一致时**不得**报不一致（否则上面三条是常亮噪声）。"""
        live = _compute_live()
        monkeypatch.setattr(
            diff_mod, "_DIFF_JSON_PATH", _write_stored(tmp_path, copy.deepcopy(live))
        )
        caplog.set_level(logging.WARNING, logger=DIFF_LOGGER)

        result = load_diff_data()

        assert result["common_sections"] == live["common_sections"]
        assert not [m for m in _warnings(caplog) if "不一致" in m or "is_mock" in m], (
            f"一致场景仍告警: {_warnings(caplog)}"
        )

    def test_missing_stored_file_is_not_an_error(self, tmp_path, monkeypatch, caplog):
        """落盘缺失不影响返回值（模板才是真源）。"""
        monkeypatch.setattr(diff_mod, "_DIFF_JSON_PATH", tmp_path / "absent.json")
        caplog.set_level(logging.WARNING, logger=DIFF_LOGGER)

        result = load_diff_data()

        live = _compute_live()
        assert result["common_sections"] == live["common_sections"]

    def test_corrupt_stored_file_falls_back_to_live(self, tmp_path, monkeypatch, caplog):
        """落盘损坏 → WARNING + 实时结果（不得抛给调用方）。"""
        bad = tmp_path / "note_soe_listed_diff.json"
        bad.write_text("{ not json", encoding="utf-8")
        monkeypatch.setattr(diff_mod, "_DIFF_JSON_PATH", bad)
        caplog.set_level(logging.WARNING, logger=DIFF_LOGGER)

        result = load_diff_data()

        assert result["common_sections"] == _compute_live()["common_sections"]
        assert any("读取失败" in m for m in _warnings(caplog))

    def test_stored_used_only_when_live_unavailable(self, tmp_path, monkeypatch, caplog):
        """fail-open：模板不可用时才降级用落盘，且必须 WARNING 说明可能 stale。"""
        stored = {
            "version": "9.9.9",
            "is_mock": False,
            "common_sections": [{"section_title": "T", "soe_section_id": "s", "listed_section_id": "l"}],
            "soe_only_sections": [],
            "listed_only_sections": [],
            "format_diff_sections": [],
        }
        monkeypatch.setattr(diff_mod, "_DIFF_JSON_PATH", _write_stored(tmp_path, stored))
        monkeypatch.setattr(diff_mod, "_SOE_TEMPLATE_PATH", tmp_path / "absent_soe.json")
        monkeypatch.setattr(diff_mod, "_LISTED_TEMPLATE_PATH", tmp_path / "absent_listed.json")
        caplog.set_level(logging.WARNING, logger=DIFF_LOGGER)

        result = load_diff_data()

        assert result["version"] == "9.9.9", "模板不可用时应降级使用落盘"
        assert any("降级" in m for m in _warnings(caplog))


class TestRealDiffJsonUntouched:
    def test_md5_unchanged_within_this_module(self):
        """前后对照：本文件的任何测试都不得改动真实落盘文件。

        有意不冻结 md5 常量 —— 模板合法变更后重生成会让它变，冻结即假红发生器。
        """
        current = hashlib.md5(DIFF_JSON.read_bytes()).hexdigest()
        assert current == _DIFF_JSON_MD5_AT_IMPORT, (
            "note_soe_listed_diff.json 在本模块运行期间被改动了 —— "
            "stale 场景必须 monkeypatch 到 tmp 文件，禁改真实数据真源"
        )


# ---------------------------------------------------------------------------
# 条目标识必须载荷完备（Requirement 1.2 的比对基准）
# ---------------------------------------------------------------------------

class TestBucketIdentityIsPayloadComplete:
    """把标识退回「只比 sid + 标题」时，下列断言必须打红。"""

    @pytest.mark.parametrize("field", ["soe_format", "listed_format", "field_mapping"])
    def test_format_diff_payload_change_detected(self, field):
        live = _compute_live()
        assert live["format_diff_sections"], "format_diff 为空，判据形同空转"
        mutated = copy.deepcopy(live)
        mutated["format_diff_sections"][0][field] = {"__probe__": True}
        cmp = compare_diff_payloads(live, mutated)
        assert cmp["consistent"] is False, (
            f"改 format_diff.{field} 未被检出 —— 条目标识不是载荷完备的"
        )
        assert cmp["buckets"]["format_diff_sections"]["only_stored"], (
            f"差异未归到 format_diff_sections 桶: {cmp['buckets']}"
        )

    def test_added_section_id_key_detected(self):
        """往条目补 ``section_id``（已否决的选项 B）也必须被判成不一致。"""
        live = _compute_live()
        mutated = copy.deepcopy(live)
        mutated["format_diff_sections"][0]["section_id"] = "probe"
        assert compare_diff_payloads(live, mutated)["consistent"] is False

    @pytest.mark.parametrize(
        "bucket,field",
        [
            ("common_sections", "listed_section_id"),
            ("soe_only_sections", "title"),
            ("listed_only_sections", "section_id"),
        ],
    )
    def test_other_buckets_change_detected(self, bucket, field):
        live = _compute_live()
        assert live[bucket], f"{bucket} 为空，判据形同空转"
        mutated = copy.deepcopy(live)
        mutated[bucket][0][field] = "__probe__"
        assert compare_diff_payloads(live, mutated)["consistent"] is False

    def test_identical_payload_is_consistent(self):
        """反向自检：同一份载荷必须判一致（否则上面几条是常亮噪声）。"""
        live = _compute_live()
        assert compare_diff_payloads(copy.deepcopy(live), live)["consistent"] is True

    def test_metadata_only_change_is_not_a_bucket_mismatch(self):
        """``is_mock`` / ``version`` 不进条目比对（它们由 load_diff_data 单独告警）。"""
        live = _compute_live()
        mutated = copy.deepcopy(live)
        mutated["is_mock"] = True
        mutated["version"] = "0.0.1"
        assert compare_diff_payloads(live, mutated)["consistent"] is True


# ---------------------------------------------------------------------------
# Property 4 / Requirement 1.5 — adapt_table_data 语义 + 四条不变式
# ---------------------------------------------------------------------------

class TestAdaptTableDataSemantics:
    # --- fixture 自检（防空转）---------------------------------------------

    def test_fixture_populates_every_remap_target(self):
        """Invariant ② 的断言建立在「桶确实存在」之上，先钉死 fixture 本身。"""
        td = _rich_table_data()
        assert [c["id"] for c in td["_columns_meta"]] == ["col_label", "col_movement"]
        assert [r["row_type"] for r in td["rows"]] == ["total", "data", "data"], (
            "fixture 必须首行为 total —— Invariant ④ 靠它验「剔行后下标重排」"
        )
        for bucket in ROW_BUCKETS:
            assert any("col_movement" in row.get(bucket, {}) for row in td["rows"]), (
                f"fixture 的 {bucket} 未按 col_movement 建键"
            )
        assert any(k.endswith(":col_movement") for k in td["_cell_provenance"])

    def test_row_bucket_list_matches_production_constant(self):
        """与生产常量交叉锁死：生产新增一个按列 id 建键的桶，本守卫必须跟着覆盖。"""
        assert set(ROW_BUCKETS) == set(diff_mod._ROW_COLUMN_KEYED_BUCKETS)

    # --- 空 field_mapping ⇒ 恒等 -------------------------------------------

    @pytest.mark.parametrize("mapping", [None, {}, [], "x", 0])
    def test_empty_or_invalid_mapping_is_identity(self, mapping):
        td = _rich_table_data()
        out, report = adapt_table_data_with_report(td, {"content_type": "table"}, mapping)
        assert out == td, "field_mapping 为空/非法时输出必须逐字等于输入"
        assert report.changed is False
        assert report.reason == ADAPT_REASON_NO_FIELD_MAPPING

    def test_input_is_never_mutated(self):
        td = _rich_table_data()
        snapshot = copy.deepcopy(td)
        adapt_table_data_with_report(td, {}, {"column_remap": {"col_movement": "col_period"}})
        assert td == snapshot, "入参被就地修改了 —— 必须返回深拷贝"

    def test_non_dict_table_data_returns_empty(self):
        out, report = adapt_table_data_with_report(None, {}, {"column_remap": {"a": "b"}})
        assert out == {}
        assert report.changed is False

    def test_shell_matches_with_report_output(self):
        td = _rich_table_data()
        for mapping in (
            None,
            {},
            {"column_remap": {"col_movement": "col_period"}},
            {"row_filter": {"exclude_row_types": ["total"]}},
            {"value_transform": {"col_movement": "x100"}},
        ):
            shell = adapt_table_data(_rich_table_data(), {}, mapping)
            with_report, _ = adapt_table_data_with_report(_rich_table_data(), {}, mapping)
            assert shell == with_report, f"薄壳与 with_report 输出不一致: {mapping}"
        assert td == _rich_table_data()

    # --- 非空 field_mapping ⇒ 结构确实改变 --------------------------------

    def test_non_empty_mapping_really_changes_structure(self):
        td = _rich_table_data()
        out, report = adapt_table_data_with_report(
            td, {}, {"column_remap": {"col_movement": "col_period"}}
        )
        assert out != td, "非空 field_mapping 命中时结构必须真的改变"
        assert report.changed is True
        assert report.reason == ADAPT_REASON_APPLIED
        assert "column_remap" in report.applied

    # --- Invariant ①：changed == (输出 != 输入) ---------------------------

    @pytest.mark.parametrize(
        "case,mapping",
        [
            ("null", None),
            ("empty", {}),
            ("remap_hit", {"column_remap": {"col_movement": "col_period"}}),
            ("remap_miss", {"column_remap": {"col_absent": "col_x"}}),
            ("remap_noop_same", {"column_remap": {"col_movement": "col_movement"}}),
            ("remap_collision", {"column_remap": {"col_movement": "col_label"}}),
            ("unsupported_only", {"value_transform": {"col_movement": "x2"}}),
            ("unknown_key", {"__nope__": 1}),
            ("filter_hit", {"row_filter": {"exclude_row_types": ["total"]}}),
            ("filter_miss", {"row_filter": {"exclude_row_types": ["nosuch"]}}),
            ("filter_empty", {"row_filter": {}}),
            (
                "remap_and_filter",
                {
                    "column_remap": {"col_movement": "col_period"},
                    "row_filter": {"exclude_row_types": ["total"]},
                },
            ),
        ],
    )
    def test_changed_equals_output_differs_from_input(self, case, mapping):
        """``changed`` 必须是**事实判据**，不得改成「我以为改了」的自我声明。

        典型错误形态：``changed = bool(field_mapping)``（``unsupported_only`` 案例
        必红）或 ``changed = bool(applied)``。
        """
        td = _rich_table_data()
        out, report = adapt_table_data_with_report(td, {}, mapping)
        assert report.changed == (out != td), f"case={case}: changed 与事实不符"

    def test_reason_codes_are_distinct(self):
        codes = {
            ADAPT_REASON_APPLIED,
            ADAPT_REASON_NO_EFFECT,
            ADAPT_REASON_NO_FIELD_MAPPING,
            ADAPT_REASON_UNSUPPORTED_ONLY,
        }
        assert len(codes) == 4, "四个原因码必须互不相同（否则调用方无法区分成因）"

    def test_unsupported_only_reason(self):
        td = _rich_table_data()
        out, report = adapt_table_data_with_report(
            td, {}, {"value_transform": {"col_movement": "x2"}}
        )
        assert out == td
        assert report.changed is False
        assert report.reason == ADAPT_REASON_UNSUPPORTED_ONLY
        assert "value_transform" in report.unsupported
        assert any("value_transform" in n for n in report.notes), (
            "已声明未实现的指令必须留诊断，不得静默忽略"
        )
        assert "value_transform" in DECLARED_UNIMPLEMENTED_FIELD_MAPPING_KEYS

    def test_recognized_but_no_effect_reason(self):
        td = _rich_table_data()
        _out, report = adapt_table_data_with_report(
            td, {}, {"column_remap": {"col_absent": "col_x"}}
        )
        assert report.reason == ADAPT_REASON_NO_EFFECT, (
            "已识别指令但没命中，应为 no_effect（与 unsupported_only 可区分）"
        )
        assert set(SUPPORTED_FIELD_MAPPING_KEYS) == {"column_remap", "row_filter"}

    # --- Invariant ②：column_remap 必须改全五处 --------------------------

    def test_column_remap_moves_meta_rows_and_provenance(self):
        td = _rich_table_data()
        out, report = adapt_table_data_with_report(
            td, {}, {"column_remap": {"col_movement": "col_period"}}
        )
        assert report.changed is True

        assert [c["id"] for c in out["_columns_meta"]] == ["col_label", "col_period"], (
            "_columns_meta[].id 未改写"
        )
        for bucket in ROW_BUCKETS:
            for idx, row in enumerate(out["rows"]):
                if bucket not in row:
                    continue
                assert "col_movement" not in row[bucket], (
                    f"rows[{idx}].{bucket} 仍留在旧列 id 上 —— 值/人工标记/溯源会失联"
                )
                assert "col_period" in row[bucket], f"rows[{idx}].{bucket} 未改到新列 id"
        assert set(out["_cell_provenance"]) == {
            "0:col_period",
            "1:col_period",
            "2:col_period",
        }, f"_cell_provenance 键未跟随列 id: {sorted(out['_cell_provenance'])}"

    def test_column_remap_preserves_manual_marks_and_values(self):
        """人工编辑必须保留（平台红线）：``manual`` 标记与值只换键、不丢内容。"""
        out, _ = adapt_table_data_with_report(
            _rich_table_data(), {}, {"column_remap": {"col_movement": "col_period"}}
        )
        assert out["rows"][1]["_cell_modes"]["col_period"] == "manual"
        assert out["rows"][2]["_cell_modes"]["col_period"] == "manual"
        assert out["rows"][1]["values"]["col_period"] == "100"
        assert out["rows"][1]["_cell_meta"]["col_period"] == {"src": "wp", "wp_code": "E1"}
        assert out["rows"][1]["_legacy_cells"]["col_period"] == "98"
        assert out["_cell_provenance"]["1:col_period"] == "P1"

    def test_column_remap_works_without_columns_meta(self):
        """``_columns_meta`` 缺失时仍须改行内列键（改造前直接 return 不改）。"""
        td = _rich_table_data()
        td.pop("_columns_meta")
        out, report = adapt_table_data_with_report(
            td, {}, {"column_remap": {"col_movement": "col_period"}}
        )
        assert report.changed is True
        assert "col_period" in out["rows"][1]["values"]
        assert any("_columns_meta" in n for n in report.notes)

    def test_column_index_keyed_cell_modes_untouched(self):
        """列**索引**形态的 ``_cell_modes``（键 ``"0"``/``"1"``）不该被 remap 命中。"""
        td = _rich_table_data()
        td["rows"][1]["_cell_modes"] = {"0": "auto", "1": "manual"}
        out, _ = adapt_table_data_with_report(
            td, {}, {"column_remap": {"col_movement": "col_period"}}
        )
        assert out["rows"][1]["_cell_modes"] == {"0": "auto", "1": "manual"}

    # --- Invariant ③：列 id 撞车必须跳过 ---------------------------------

    def test_column_id_collision_is_skipped(self):
        td = _rich_table_data()
        out, report = adapt_table_data_with_report(
            td, {}, {"column_remap": {"col_movement": "col_label"}}
        )
        assert report.changed is False, "撞车时不得改写（会产生重复列 id）"
        assert out == td
        assert any("撞车" in n for n in report.notes), f"撞车未留诊断: {report.notes}"

    def test_two_sources_to_same_target_keeps_ids_unique(self):
        td = _rich_table_data()
        out, report = adapt_table_data_with_report(
            td, {}, {"column_remap": {"col_label": "col_x", "col_movement": "col_x"}}
        )
        ids = [c["id"] for c in out["_columns_meta"]]
        assert len(ids) == len(set(ids)), f"产生了重复列 id: {ids}"
        assert any("撞车" in n for n in report.notes)

    def test_column_ids_stay_unique_on_normal_remap(self):
        out, _ = adapt_table_data_with_report(
            _rich_table_data(), {}, {"column_remap": {"col_movement": "col_period"}}
        )
        ids = [c["id"] for c in out["_columns_meta"]]
        assert len(ids) == len(set(ids)) == 2

    # --- Invariant ④：row_filter 剔行后溯源行下标必须重排 ----------------

    def test_row_filter_reindexes_cell_provenance(self):
        td = _rich_table_data()
        out, report = adapt_table_data_with_report(
            td, {}, {"row_filter": {"exclude_row_types": ["total"]}}
        )
        assert report.changed is True
        assert [r["row_type"] for r in out["rows"]] == ["data", "data"]
        assert out["_cell_provenance"] == {
            "0:col_movement": "P1",
            "1:col_movement": "P2",
        }, (
            "剔行后 _cell_provenance 的行下标未重排 —— 溯源会静默指向错行"
            f"（实际 {out['_cell_provenance']}）"
        )
        assert any("_cell_provenance" in n for n in report.notes)

    def test_row_filter_miss_is_noop(self):
        td = _rich_table_data()
        out, report = adapt_table_data_with_report(
            td, {}, {"row_filter": {"exclude_row_types": ["nosuch"]}}
        )
        assert out == td
        assert report.changed is False
        assert report.reason == ADAPT_REASON_NO_EFFECT

    def test_row_filter_unknown_subkey_is_reported(self):
        _out, report = adapt_table_data_with_report(
            _rich_table_data(), {}, {"row_filter": {"keep_only": ["data"]}}
        )
        assert any("keep_only" in n for n in report.notes)

    def test_remap_and_filter_combined(self):
        out, report = adapt_table_data_with_report(
            _rich_table_data(),
            {},
            {
                "column_remap": {"col_movement": "col_period"},
                "row_filter": {"exclude_row_types": ["total"]},
            },
        )
        assert report.changed is True
        assert set(report.applied) == {"column_remap", "row_filter"}
        assert out["_cell_provenance"] == {"0:col_period": "P1", "1:col_period": "P2"}


# ---------------------------------------------------------------------------
# 消费方计数：format_adapted_count 不得把空操作计为已适配
# ---------------------------------------------------------------------------

class TestConsumerCountsOnlyRealAdaptations:
    """标的 = :meth:`_map_disclosure_notes`（``convert_disclosure_notes_v2`` 已于
    spec Task 10 删除，生产侧唯一的 ``format_adapted`` 计数点在这里）。"""

    def test_increment_is_wrapped_by_changed_guard(self):
        src = _func_source(CONVERSION_SERVICE, "_map_disclosure_notes")
        assert _format_adapt_guard_ok(src), (
            '_map_disclosure_notes 里存在未被 ``if report.changed:`` 包住的 '
            'result["format_adapted"] += 1 —— 空操作会被上报成「已适配」'
            "（39/39 全 null 的 field_mapping 会让计数虚高）"
        )

    def test_unparse_normalizes_quotes_in_target(self):
        """自检：``_FORMAT_ADAPTED_TARGET`` 必须是 unparse 派生值，不得手写源码形态。

        ``ast.unparse`` 把字符串下标统一改写成单引号，手写双引号字面量去比会让
        :func:`_format_adapt_increments` 恒收集不到任何节点 ⇒ 判据静默返回 False
        ⇒ 守卫在**正确实现**上打红（本轮实测踩中）。
        """
        assert _FORMAT_ADAPTED_TARGET == "result['format_adapted']"
        assert _FORMAT_ADAPTED_TARGET != _FORMAT_ADAPTED_TARGET_SRC, (
            "unparse 后与源码形态相同 ⇒ 本自检失去意义，请确认仍在做规范化派生"
        )

    def test_predicate_finds_the_real_increment(self):
        """自检（防空转）：判据必须在真实生产源码里**确实找到** 1 个自增点。

        只断言 ``_format_adapt_guard_ok(...) is True`` 不足以区分「找到并验证通过」
        与「一个都没找到」——后者在 helper 写错时会走 ``if not incs: return False``，
        表现为打红；但若将来 helper 改成「没找到就放行」就会静默变成假绿。
        """
        src = _func_source(CONVERSION_SERVICE, "_map_disclosure_notes")
        incs = _format_adapt_increments(ast.parse(src))
        assert len(incs) == 1, (
            f"生产代码里 result['format_adapted'] 的自增点应恰好 1 处，实测 {len(incs)}"
        )

    def test_predicate_rejects_unconditional_increment(self):
        """反向自检：有自增但无 ``report.changed`` 守卫（改造前形态）必须判 False。"""
        assert _format_adapt_guard_ok(_UNCONDITIONAL_COUNT_FIXTURE) is False

    def test_predicate_rejects_guard_after_increment(self):
        """反向自检：先自增再判守卫（计数未被包住）必须判 False。"""
        assert _format_adapt_guard_ok(_GUARD_AFTER_COUNT_FIXTURE) is False

    def test_predicate_rejects_second_unguarded_increment(self):
        """反向自检：一个自增在守卫内、另一个在 ``else`` 里，必须判 False。

        这是新判据比原「守卫先于计数」强的地方 —— 行号偏序抓不到第二自增点。
        """
        assert _format_adapt_guard_ok(_SECOND_UNGUARDED_INCREMENT_FIXTURE) is False

    def test_adapt_call_is_inside_the_loop(self):
        """锚点存在性：确认判据作用在真实的格式适配代码块上，非空转。

        锚点按 2026-08-07 AST 实测取生产代码真实形态：``for fd in format_diffs:``
        与裸 ``adapt_table_data(`` 在 ``_map_disclosure_notes`` 里**均为 0 次**
        （适配是按 ``src_sid`` 从 plan 里取条目、调 ``*_with_report`` 版本）。
        """
        body = _strip_comments(_func_source(CONVERSION_SERVICE, "_map_disclosure_notes"))
        assert 'plan["format_diff"].get(src_sid)' in body, (
            "未见从映射计划按源侧 sid 取 format_diff 条目"
        )
        assert "adapt_table_data_with_report(" in body, (
            "未调 adapt_table_data_with_report —— 薄壳版不返回 report，"
            "拿不到事实判据就只能退回自我声明计数"
        )

    def test_increment_appears_exactly_once_after_stripping_comments(self):
        body = _strip_comments(_func_source(CONVERSION_SERVICE, "_map_disclosure_notes"))
        assert body.count('result["format_adapted"] += 1') == 1, (
            "format_adapted 的自增点不唯一 —— 多入口会绕开 report.changed 守卫"
        )

    def test_strip_comments_selfcheck_for_count_region(self):
        """反向自检：剥注释在承重（raw 命中数 > body 命中数）。

        原锚点「无条件 ``+= 1``」在生产 raw 里已被换行拆开 ⇒ 命中 0 = 空转。
        实测唯一「raw 多于 body」的锚点是 ``legacy compat``（raw 2 / body 1）：
        docstring 里 1 处是字符串字面量（:func:`_strip_comments` 有意不剥），
        新建空章节处的 ``#`` 注释里 1 处必须被剥掉。
        """
        raw = _func_source(CONVERSION_SERVICE, "_map_disclosure_notes")
        needle = "legacy compat"
        raw_hits = raw.count(needle)
        body_hits = _strip_comments(raw).count(needle)
        assert raw_hits > 0, (
            f"生产代码里已无 {needle!r} —— 本自检失去锚点，请另选「raw 有 / body 无」的字样"
        )
        assert body_hits < raw_hits, (
            f"_strip_comments 未剥掉任何 {needle!r} 注释（raw={raw_hits} body={body_hits}）"
            " —— 剥注释可能已失效，上面几条源码级断言会在含注释的文本上求值"
        )

    def test_noop_writeback_is_guarded_and_logged(self):
        """空操作**不写回**：``note.table_data = adapted`` 必须在 ``report.changed`` 体内。

        生产代码没有「``format_noop_sids`` 收集空操作章节」这一概念（AST 实测 0 次）
        ⇒ 不按它写断言（会引入生产代码里不存在的概念）。改为更强的正向不变式：
        空操作时**连写回都不发生**（比「计数不加一」更严 —— 写回会让 ``table_data``
        被同值覆盖并触发无谓的 flush/脏标记）。
        """
        src = _func_source(CONVERSION_SERVICE, "_map_disclosure_notes")
        tree = ast.parse(src)

        def _writebacks(node: ast.AST) -> list[ast.Assign]:
            out: list[ast.Assign] = []
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Assign)
                    and len(sub.targets) == 1
                    and ast.unparse(sub.targets[0]) == "note.table_data"
                    and ast.unparse(sub.value) == "adapted"
                ):
                    out.append(sub)
            return out

        all_wb = _writebacks(tree)
        assert all_wb, (
            "未见 ``note.table_data = adapted`` 写回 —— 锚点失效，本断言形同空转"
        )
        guarded = [
            wb
            for node in ast.walk(tree)
            if isinstance(node, ast.If) and ast.unparse(node.test) == "report.changed"
            for wb in _writebacks(node)
        ]
        assert len(guarded) == len(all_wb), (
            f"有 {len(all_wb) - len(guarded)} 处 ``note.table_data = adapted`` 未被 "
            "``if report.changed:`` 包住 —— 空操作会被同值写回"
        )

        body = _strip_comments(src)
        assert "logger.warning" in body, (
            "该方法未保留 WARNING 出口 —— 逐章节失败会被静默吞掉（假成功反馈会重现）"
        )
