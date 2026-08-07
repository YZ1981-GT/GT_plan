"""`prefill_anchor_map` 单一真源守卫（Wave 2/4：映射一致性 + 持久化列交叉锁死）。

spec: .kiro/specs/prefill-wp-prev-resolution-repair/
      Task 7（持久化列交叉锁死，本 spec 最有价值的一条）
      Task 11（待对齐清单 + 范围外登记）
      Property 3/4/5/6/7/8/13/14/15/16

本文件的核心是 **Property 4**：断言 `ANCHOR_MAP` 每条的 `column` 都在**前端序列化
函数真正写入的字段集**里。这把「后端复刻前端派生公式」这一双真源风险变成编译期可检测 ——
`useD1DetailCategory.serializeRows()` 只写 10 个录入列，`currentUnadjusted` 由
`recalcRow()` 加载时重算、「小计」是 `computed` ⇒ 映射到它们后端永远拿不到值，
而单测用替身数据可以「全绿」地掩盖这一点。
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.prefill_anchor_map import (
    ANCHOR_MAP,
    OUT_OF_SCOPE_CHANGES,
    OUT_OF_SCOPE_CYCLES,
    OUT_OF_SCOPE_NON_WORKPAPER_TARGETS,
    UNALIGNED,
    UNALIGNED_MAX,
    WP_IMPLEMENTATION_PATHS,
    AnchorAggregate,
    AnchorReadStatus,
    AnchorSpec,
    parse_anchor_value,
    resolve_anchor,
)

_REPO = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]
_PRESET_JSON = _BACKEND / "data" / "prefill_formula_mapping.json"

#: 本 spec 负责的循环
_IN_SCOPE_CYCLE = "D"


# ─────────────────────────── 预设 JSON 实时解析（Property 3/5）───────────────────────────


def _parse_wp_triples() -> dict[str, set[tuple[str, str, str]]]:
    """从 `prefill_formula_mapping.json` 实时解析 `WP()` 三元组，按**目标** wp_code 分组。

    🔴 不写死清单 —— 预设变动时守卫自动打红（Property 3 的核心要求）。

    🔴 正则必须容忍**半角括号**：实测 `WP('E1','银行存款及其他货币资金明细表(人民币及外币)E1-3',…)`
    的 sheet 名里含半角 `)`，用 `\\(([^)]*)\\)` 抽实参会在 sheet 名中间截断
    （本轮首版探针即因此把 5 条 WP 误判成「实参不足 3 个」）。
    故按**单引号配对**抽三个实参，不依赖外层括号。
    """
    doc = json.loads(_PRESET_JSON.read_text(encoding="utf-8"))
    out: dict[str, set[tuple[str, str, str]]] = {}
    arg_re = re.compile(r"=\s*WP\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'")
    for block in doc.get("mappings") or []:
        for cell in block.get("cells") or []:
            m = arg_re.match(str(cell.get("formula") or "").strip())
            if m is None:
                continue
            triple = (m.group(1), m.group(2), m.group(3))
            out.setdefault(triple[0][:1].upper(), set()).add(triple)
    return out


_WP_TRIPLES_BY_CYCLE = _parse_wp_triples()
_D_TRIPLES = _WP_TRIPLES_BY_CYCLE.get(_IN_SCOPE_CYCLE, set())


class TestPresetParsingIsNotVacuous:
    """反向自检：解析器确实抽到了东西（正则失效 → 集合为空 → 下游断言恒成立）。"""

    def test_preset_json_exists(self) -> None:
        assert _PRESET_JSON.exists(), (
            f"预设 JSON 不存在：{_PRESET_JSON}\n"
            "🔴 该文件在 `backend/data/` 不在 `backend/data/ledger_adapters/`"
            "（memory 已登记的路径坑）；路径错会让本文件全部断言空转。"
        )

    def test_d_cycle_triples_non_empty(self) -> None:
        assert _D_TRIPLES, (
            "从预设 JSON 解析出的 D 循环 WP() 三元组为空 —— 解析正则已失效，"
            "Property 3 的完备性断言会恒成立（空转）。"
        )

    def test_paren_tolerant_regex_selfcheck(self) -> None:
        """反向自检：半角括号 sheet 名必须能被解析（首版探针的真实缺陷）。"""
        arg_re = re.compile(r"=\s*WP\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'")
        sample = "=WP('E1','银行存款及其他货币资金明细表(人民币及外币)E1-3','期末余额合计')"
        m = arg_re.match(sample)
        assert m is not None, "半角括号 sheet 名解析失败"
        assert m.group(2) == "银行存款及其他货币资金明细表(人民币及外币)E1-3", (
            f"sheet 名被截断：{m.group(2)!r} —— 说明正则退化成按外层括号抽实参。"
        )
        assert m.group(3) == "期末余额合计"

    def test_all_cycles_present(self) -> None:
        """辅助锚点：解析结果应覆盖多个循环（证明扫描面是全库不是单块）。"""
        assert len(_WP_TRIPLES_BY_CYCLE) >= 5, (
            f"只解析出 {len(_WP_TRIPLES_BY_CYCLE)} 个循环的 WP()，"
            "预期 ≥5（实测 D/E/F/G/H/J/K/M/N）。"
        )


# ═══════════════════════ Property 3：映射表与待对齐清单互斥且完备 ═══════════════════════


class TestMapCompleteness:
    def test_disjoint(self) -> None:
        overlap = set(ANCHOR_MAP) & set(UNALIGNED)
        assert not overlap, (
            f"以下三参组同时出现在 ANCHOR_MAP 与 UNALIGNED：{sorted(overlap)}\n"
            "两表必须互斥 —— 否则「已对齐」与「待对齐」的判定取决于查表顺序。"
        )

    def test_union_covers_all_d_cycle_triples(self) -> None:
        """每条 D 循环预设要么有映射，要么显式登记待对齐，不留灰区。"""
        covered = set(ANCHOR_MAP) | set(UNALIGNED)
        missing = _D_TRIPLES - covered
        assert not missing, (
            f"以下 D 循环 WP() 三元组既未映射也未登记待对齐（灰区）：\n"
            + "\n".join(f"  {t}" for t in sorted(missing))
            + "\n每条都必须有明确归属，否则 resolver 静默返 None 而无人知晓。"
        )

    def test_no_phantom_entries(self) -> None:
        """反向：两表里不得有预设中不存在的三元组（防写幻想锚点）。"""
        covered = set(ANCHOR_MAP) | set(UNALIGNED)
        phantom = covered - _D_TRIPLES
        assert not phantom, (
            f"以下三参组在真实预设里不存在（幻想锚点）：\n"
            + "\n".join(f"  {t}" for t in sorted(phantom))
            + "\n预设改动后应同步移除，否则映射表逐渐与现实脱节。"
        )


# ═══════════════════════ Property 4：🔴 持久化列交叉锁死 ═══════════════════════


def _extract_persisted_fields(ts_path: Path) -> set[str]:
    """从前端 composable 源码抽「持久化函数真正写入的字段名集合」。

    两种形态（实测都存在）：

    1. **显式白名单** —— `serializeRows()` / `serializeNoteTypeRows()` 里
       `rows.map(r => ({ rowId: r.rowId, ... }))`，只写录入列
       （`useD1DetailCategory` / `useD1BadDebt` 是这种）
    2. **整行 stringify** —— `JSON.stringify(rows.value)` 或
       `JSON.stringify(storedData.value)`，全字段落库
       （`useD6Detail` / `useD7Detail` / `useD4*` 是这种）

    形态 2 下「持久化字段集」= 该行接口声明的字段集，故回退到抽 `interface XxxRow`。
    """
    src = ts_path.read_text(encoding="utf-8")

    # ── 形态 1：找显式白名单序列化函数 ──
    for fn in ("serializeNoteTypeRows", "serializeRows"):
        m = re.search(rf"function\s+{fn}\s*\(", src)
        if m is None:
            continue
        body = _brace_body(src, m.end() - 1)
        if not body:
            continue
        # 整行 stringify（形态 2 伪装成 serializeRows）→ 落到形态 2 处理
        if re.search(r"JSON\.stringify\(\s*(?:cleaned)?[Rr]ows\s*\)", body):
            break
        keyed = set(re.findall(r"^\s*(\w+)\s*:", body, re.M))
        # 排除 ChecklistItem 的三个包装键
        keyed -= {"item_id", "conclusion", "remark"}
        if keyed:
            return keyed

    # ── 形态 2：整行落库 → 字段集 = 接口声明 ──
    fields: set[str] = set()
    for im in re.finditer(r"(?:export\s+)?interface\s+(\w*Row)\s*\{", src):
        body = _brace_body(src, im.end() - 1)
        fields |= set(re.findall(r"^\s*(\w+)\s*[?]?\s*:", body, re.M))
    return fields


def _brace_body(src: str, open_idx: int) -> str:
    """从 `src[open_idx] == '{'` 起做花括号配对，返回体内文本。

    🔴 固定字符窗口在本仓库反复出问题（memory 已登记多例）→ 一律配对。
    """
    if open_idx < 0 or open_idx >= len(src) or src[open_idx] != "{":
        # 允许传入 `(` 的位置：先找它之后的第一个 `{`
        nxt = src.find("{", open_idx)
        if nxt < 0:
            return ""
        open_idx = nxt
    depth = 0
    for i in range(open_idx, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_idx + 1 : i]
    return ""


class TestPersistedColumnCrossLock:
    """Property 4 —— 映射的列键必须在前端序列化字段集内（防双真源）。"""

    def test_serializer_files_exist(self) -> None:
        for key, spec in ANCHOR_MAP.items():
            p = _REPO / spec.serializer_module
            assert p.exists(), (
                f"{key} 声明的 serializer_module 不存在：{spec.serializer_module}\n"
                "该路径是 Property 4 的判据来源，写错会让交叉锁死空转。"
            )

    def test_extraction_is_not_vacuous(self) -> None:
        """反向自检：抽出的字段集非空（正则失效时集合为空会让下面断言恒成立）。"""
        for key, spec in ANCHOR_MAP.items():
            fields = _extract_persisted_fields(_REPO / spec.serializer_module)
            assert fields, (
                f"{key} 的 serializer 抽出 0 个持久化字段 —— 抽取器已失效，"
                f"Property 4 对该条空转。文件：{spec.serializer_module}"
            )
            assert len(fields) >= 5, (
                f"{key} 只抽出 {len(fields)} 个字段（{sorted(fields)}），疑似抽取边界错误。"
            )

    def test_mapped_columns_are_persisted(self) -> None:
        """核心断言：每条映射的 column 必须真的落库。"""
        offenders: list[str] = []
        for key, spec in ANCHOR_MAP.items():
            fields = _extract_persisted_fields(_REPO / spec.serializer_module)
            if spec.column and spec.column not in fields:
                offenders.append(
                    f"  {key}\n"
                    f"    column={spec.column!r} 不在持久化字段集内\n"
                    f"    serializer={spec.serializer_module}\n"
                    f"    实测字段集={sorted(fields)}"
                )
        assert not offenders, (
            "以下映射指向了**不落库**的列（后端永远取不到值）：\n"
            + "\n".join(offenders)
            + "\n\n🔴 派生列（前端加载时重算 / computed 小计）不得映射 —— "
            "在后端复刻其公式就是双真源。正解见 "
            "OUT_OF_SCOPE_CHANGES['frontend_persist_derived_columns']，"
            "该条目应进 UNALIGNED 而非 ANCHOR_MAP。"
        )

    def test_derived_column_would_be_caught(self) -> None:
        """反向自检 ①：拿已实证的派生列构造替身，断言守卫能抓出来。

        `D1-cat-rows` 的 `currentUnadjusted` 由 `useD1DetailCategory.recalcRow()`
        加载时重算，`serializeRows()` 的 10 个键里没有它 —— 这是本 spec 的判据原点。
        """
        ts = (
            "audit-platform/frontend/src/components/workpaper/composables/"
            "useD1DetailCategory.ts"
        )
        fields = _extract_persisted_fields(_REPO / ts)
        assert fields, "useD1DetailCategory 字段集抽取失败，反向自检空转。"
        assert "currentUnadjusted" not in fields, (
            "useD1DetailCategory.serializeRows() 现在写入 currentUnadjusted 了 —— "
            "若前端确已改为持久化派生列，本 spec 的 UNALIGNED 条目 "
            "('D1','原值明细表（按类别）D1-2','合计-期末未审数') 应移入 ANCHOR_MAP；"
            "否则说明字段集抽取器把派生列误算进去了。"
        )
        # 同时确认录入列确实抽到了（证明不是整体抽空）
        for entered in ("priorUnadjusted", "currentIncrease", "currentDecrease"):
            assert entered in fields, (
                f"录入列 {entered} 未被抽到，抽取器判据不可信：{sorted(fields)}"
            )


# ═══════════════════════ Property 5/6：键形态与实证 ═══════════════════════


class TestKeyShapeAndEvidence:
    def test_keys_are_triples(self) -> None:
        for table_name, table in (("ANCHOR_MAP", ANCHOR_MAP), ("UNALIGNED", UNALIGNED)):
            for key in table:
                assert isinstance(key, tuple) and len(key) == 3, (
                    f"{table_name} 的键 {key!r} 不是三元组。\n"
                    "🔴 键必须含 sheet —— 实测 34 对 (wp_code, cell_ref) 跨 sheet 复用，"
                    "二元组键会让多张明细表塌成一条映射。"
                )

    def test_cross_sheet_reuse_really_exists(self) -> None:
        """Property 5 反向自检：证明二元组键确实会塌。"""
        by_pair: dict[tuple[str, str], set[str]] = {}
        for triples in _WP_TRIPLES_BY_CYCLE.values():
            for wp, sheet, ref in triples:
                by_pair.setdefault((wp, ref), set()).add(sheet)
        collisions = {k: v for k, v in by_pair.items() if len(v) > 1}
        assert collisions, (
            "真实预设里找不到任何「同 (wp_code, cell_ref) 跨多 sheet」的组 —— "
            "则「键必须三元组」这条约束失去实证依据，需复核设计前提。"
        )
        # D 循环内至少一组（本 spec 作用域内的直接证据）
        d_collisions = {k: v for k, v in collisions.items() if k[0].startswith("D")}
        assert d_collisions, (
            f"D 循环内无跨 sheet 复用（全库有 {len(collisions)} 组）—— "
            "本 spec 作用域内的三元组必要性需另找依据。"
        )

    def test_evidence_quality(self) -> None:
        markers = ("item_id", "serializeRows", "serializeNoteTypeRows", "persistRows",
                   "composable", "源模板", "实测", "接口")
        bad: list[str] = []
        for key, spec in ANCHOR_MAP.items():
            if len(spec.evidence) < 20:
                bad.append(f"  {key}: evidence 仅 {len(spec.evidence)} 字")
            elif not any(m in spec.evidence for m in markers):
                bad.append(f"  {key}: evidence 无实证标记 {markers}")
        assert not bad, (
            "以下映射的 evidence 不合格（防映射表变成「猜出来的」）：\n" + "\n".join(bad)
        )

    def test_row_key_consistency(self) -> None:
        for key, spec in ANCHOR_MAP.items():
            if spec.aggregate is AnchorAggregate.ROW:
                assert spec.row_key, f"{key}: aggregate=ROW 但 row_key 为空"
            else:
                assert spec.row_key is None, (
                    f"{key}: aggregate={spec.aggregate.value} 却声明了 "
                    f"row_key={spec.row_key!r}（不合法形态）"
                )


# ═══════════════════════ Property 7/8：六态与聚合语义 ═══════════════════════


def _spec(**kw) -> AnchorSpec:
    base = dict(
        item_id="X-rows",
        column="amount",
        aggregate=AnchorAggregate.SUM,
        evidence="替身 spec：item_id X-rows 用于单测，不进真实映射表（实测形态镜像）",
        serializer_module="audit-platform/frontend/src/components/workpaper/composables/useD7Detail.ts",
    )
    base.update(kw)
    return AnchorSpec(**base)  # type: ignore[arg-type]


class TestParseAnchorValue:
    """Property 7/8 —— 六态可分辨 + 聚合语义正确。"""

    def test_scalar_hit(self) -> None:
        """标量态必须显式声明 ``aggregate=SCALAR``。

        🔴 本例原写 ``aggregate=SUM`` + ``column=""`` —— 那是三枚举草案的遗留写法。
        实现新增 `SCALAR` 后，``SUM`` 分支会先 ``json.loads('1234.56')`` 得 float，
        非 list ⇒ 返 ``EMPTY``。**不得**为了让本例过而让 ``SUM`` 去容忍标量：
        「行数组里求和」与「整个 item 就是一个数」是两种存储形态，
        合并会让「配置写错列名」静默退化成「取到整格标量」。
        """
        res = parse_anchor_value(
            "1234.56", _spec(column="", aggregate=AnchorAggregate.SCALAR)
        )
        assert res.status is AnchorReadStatus.HIT
        assert res.value == Decimal("1234.56")

    def test_scalar_form_must_be_declared_not_inferred(self) -> None:
        """反向自检：标量 raw 配 ``SUM`` 必须得 EMPTY，不得被当标量兜底。

        这条钉死「形态由声明决定、不由值猜」——
        否则映射表写错 ``aggregate`` 时不会打红。
        """
        res = parse_anchor_value("1234.56", _spec(column="amount"))
        assert res.status is AnchorReadStatus.EMPTY, (
            f"SUM 形态遇到标量 raw 得到 {res.status.value}，应为 EMPTY —— "
            "聚合形态必须由 AnchorSpec 声明，容忍标量会掩盖映射表的 aggregate 写错。"
        )
        assert res.value is None

    def test_none_is_empty_at_parse_layer(self) -> None:
        """``raw is None`` 在**纯函数层**是 EMPTY，``NO_ITEM`` 只由取值层判定。

        🔴 本例原断言 ``NO_ITEM``，但 `parse_anchor_value` 零 DB 依赖、
        无从得知「item_id 未落库」与「落库了但值是 NULL」的区别 ——
        那个区分在 :func:`read_anchor_value` 里（查不到行 → ``NO_ITEM``）。
        让纯函数返 ``NO_ITEM`` 会让六态归属含糊：同一个 ``None`` 在两层含义不同。
        """
        res = parse_anchor_value(None, _spec())
        assert res.status is AnchorReadStatus.EMPTY
        assert res.value is None

    def test_empty_string_is_empty_not_hit(self) -> None:
        """反向自检：空串必须得 EMPTY 而非 HIT / NO_ITEM。"""
        res = parse_anchor_value("", _spec())
        assert res.status is AnchorReadStatus.EMPTY, (
            f"空串得到 {res.status.value}，应为 EMPTY —— "
            "「未编制」与「填了空」是两种审计事实，合并会让缺陷潜伏。"
        )
        assert res.value is None

    def test_non_numeric_scalar_is_empty(self) -> None:
        res = parse_anchor_value("待填", _spec(column="", aggregate=AnchorAggregate.SUM))
        assert res.status is AnchorReadStatus.EMPTY
        assert res.value is None

    def test_sum_across_rows(self) -> None:
        raw = json.dumps([{"amount": 100}, {"amount": "200.5"}, {"amount": 0}])
        res = parse_anchor_value(raw, _spec())
        assert res.status is AnchorReadStatus.HIT
        assert res.value == Decimal("300.5")
        assert "3" in res.detail, f"detail 未含参与行数：{res.detail!r}"

    def test_sum_skips_non_numeric_not_treats_as_zero(self) -> None:
        """非数值行跳过而不当 0 —— 两者在「全非数值」时结果不同（EMPTY vs 0）。"""
        raw = json.dumps([{"amount": "abc"}, {"amount": 50}])
        res = parse_anchor_value(raw, _spec())
        assert res.status is AnchorReadStatus.HIT
        assert res.value == Decimal("50")

    def test_all_non_numeric_is_empty_not_zero(self) -> None:
        raw = json.dumps([{"amount": "abc"}, {"amount": None}])
        res = parse_anchor_value(raw, _spec())
        assert res.status is AnchorReadStatus.EMPTY, (
            f"全非数值得到 {res.status.value}/{res.value} —— 应为 EMPTY。"
            "返 0 会让「填了但全是脏数据」显示成「余额为 0」。"
        )

    def test_empty_array_is_empty(self) -> None:
        res = parse_anchor_value("[]", _spec())
        assert res.status is AnchorReadStatus.EMPTY

    def test_missing_column_is_no_column(self) -> None:
        """反向自检：列键不存在于任何行 → NO_COLUMN（禁回退别的列）。"""
        raw = json.dumps([{"other": 100}, {"other": 200}])
        res = parse_anchor_value(raw, _spec())
        assert res.status is AnchorReadStatus.NO_COLUMN, (
            f"缺列得到 {res.status.value}，应为 NO_COLUMN —— "
            "回退取别的列会静默取错数。"
        )
        assert res.value is None

    def test_sum_list_inner_then_outer(self) -> None:
        raw = json.dumps([{"months": [1, 2, 3]}, {"months": [10, 20]}])
        res = parse_anchor_value(raw, _spec(column="months", aggregate=AnchorAggregate.SUM_LIST))
        assert res.status is AnchorReadStatus.HIT
        assert res.value == Decimal("36")

    def test_sum_list_rejects_scalar_column(self) -> None:
        """SUM_LIST 的列若不是数组 → 不得静默当标量求和。"""
        raw = json.dumps([{"months": 100}])
        res = parse_anchor_value(raw, _spec(column="months", aggregate=AnchorAggregate.SUM_LIST))
        assert res.status is not AnchorReadStatus.HIT or res.value != Decimal("100"), (
            "SUM_LIST 对标量列静默求和了 —— 应视为形态不符（EMPTY/NO_COLUMN），"
            "否则前端把数组改成标量时后端不会报错。"
        )

    def test_row_mode_hits_by_row_id(self) -> None:
        raw = json.dumps([
            {"rowId": "fixed-bank", "amount": 111},
            {"rowId": "fixed-commercial", "amount": 222},
        ])
        res = parse_anchor_value(
            raw, _spec(aggregate=AnchorAggregate.ROW, row_key="fixed-commercial")
        )
        assert res.status is AnchorReadStatus.HIT
        assert res.value == Decimal("222")

    def test_row_mode_does_not_fall_back_to_first_row(self) -> None:
        """反向自检 ②：`row_key` 未命中**绝不**返第一行（静默取错行的防线）。"""
        raw = json.dumps([
            {"rowId": "fixed-bank", "amount": 111},
            {"rowId": "fixed-commercial", "amount": 222},
        ])
        res = parse_anchor_value(
            raw, _spec(aggregate=AnchorAggregate.ROW, row_key="不存在的行")
        )
        assert res.value is None, (
            f"row_key 未命中却返回了 {res.value} —— 疑似回退取第一行（111）。"
        )
        assert res.status in (AnchorReadStatus.NO_COLUMN, AnchorReadStatus.EMPTY)

    def test_row_mode_matches_alternate_id_fields(self) -> None:
        """行标识字段实测有 rowId/id/label/category/noteType/name 多种。"""
        for field in ("id", "label", "category", "noteType", "name"):
            raw = json.dumps([{field: "target", "amount": 777}])
            res = parse_anchor_value(
                raw, _spec(aggregate=AnchorAggregate.ROW, row_key="target")
            )
            assert res.status is AnchorReadStatus.HIT, f"行标识字段 {field} 未被识别"
            assert res.value == Decimal("777")

    def test_malformed_json_is_empty(self) -> None:
        res = parse_anchor_value("{not json", _spec())
        assert res.status is AnchorReadStatus.EMPTY
        assert res.value is None

    def test_hit_iff_value_not_none(self) -> None:
        """Property 7 的核心不变式：HIT ⟺ value is not None。"""
        cases = [
            ("1", _spec(column="", aggregate=AnchorAggregate.SUM)),
            ("", _spec()),
            (None, _spec()),
            ("[]", _spec()),
            (json.dumps([{"other": 1}]), _spec()),
            (json.dumps([{"amount": 5}]), _spec()),
        ]
        for raw, spec in cases:
            res = parse_anchor_value(raw, spec)
            assert (res.status is AnchorReadStatus.HIT) == (res.value is not None), (
                f"raw={raw!r} 得 status={res.status.value} value={res.value!r} —— "
                "违反 HIT ⟺ value is not None。"
            )


class TestResolveAnchor:
    def test_resolves_known_triple(self) -> None:
        spec = resolve_anchor("D2", "明细表D2-2", "期末合计")
        assert spec is not None
        assert spec.item_id == "D2-detail-rows"

    def test_returns_none_for_unaligned(self) -> None:
        """待对齐清单里的三参组必须返 None（不得偷偷映射）。"""
        for key in UNALIGNED:
            assert resolve_anchor(*key) is None, (
                f"{key} 在 UNALIGNED 清单里，resolve_anchor 却返回了 spec。"
            )

    def test_returns_none_for_unknown(self) -> None:
        assert resolve_anchor("ZZ", "不存在的表", "不存在的锚点") is None

    def test_sheet_participates_in_lookup(self) -> None:
        """同 (wp_code, cell_ref) 换 sheet 必须解析到不同 spec（或 None）。"""
        a = resolve_anchor("D6", "明细表D6-2", "期末合计")
        b = resolve_anchor("D6", "合同资产减值准备明细表D6-3", "期末合计")
        assert a is not None and b is not None
        assert a.item_id != b.item_id, (
            f"D6 的两个 sheet 解析到同一 item_id={a.item_id} —— "
            "sheet 未参与查表，二元组键的塌陷已发生。"
        )


# ═══════════════════════ Property 13/14/15/16：清单与范围外登记 ═══════════════════════


class TestUnalignedLedger:
    def test_within_cap(self) -> None:
        assert len(UNALIGNED) <= UNALIGNED_MAX, (
            f"待对齐清单 {len(UNALIGNED)} 条 > 上限 {UNALIGNED_MAX}。\n"
            "🔴 上限只许下调 —— 「对不齐就往清单里加一条」会把清单当逃逸阀。"
        )

    def test_reason_quality(self) -> None:
        markers = ("派生列", "item_id", "实测", "二级链", "小计", "serializeRows")
        bad = [
            f"  {k}: {len(v)} 字"
            for k, v in UNALIGNED.items()
            if len(v) < 20 or not any(m in v for m in markers)
        ]
        assert not bad, "以下待对齐条目的理由不合格（防占位理由）：\n" + "\n".join(bad)

    def test_derived_reasons_point_to_the_fix(self) -> None:
        """Property 16：凡「派生列」原因的条目必须引用正解登记键。"""
        fix_key = "frontend_persist_derived_columns"
        bad = [
            f"  {k}"
            for k, v in UNALIGNED.items()
            if "派生列" in v and fix_key not in v
        ]
        assert not bad, (
            f"以下「派生列」待对齐条目未引用 OUT_OF_SCOPE_CHANGES['{fix_key}']：\n"
            + "\n".join(bad)
            + "\n把「为什么对不齐」与「正解在哪」绑死，防清单变成无出口的黑洞。"
        )


class TestOutOfScopeLedger:
    def test_all_non_d_cycles_registered(self) -> None:
        """范围外登记必须**从预设实时派生**，不得写死字母表。

        🔴 原判据是 `expected = set("EFGHIJKLMN")` —— 写死清单有两个后果：

        1. 预设新增别的循环时**不会打红**（清单不会自己长出来）；
        2. **表达不了非循环字母的 target** —— 实测 `WP('PL','利润表','净利润')`
           与 `'上期净利润'` 两条，`PL` 是**利润表（报表）不是底稿**，
           首字母 `P` 落在字母表外，于是这两条既不在 `ANCHOR_MAP`、
           也不在 `UNALIGNED`、也不被任何范围外登记覆盖 = **无人认领的灰区**，
           而本 spec 的 Property 3 只校验 D 循环并集，抓不到它。

        正确判据 = 「预设里出现的每一个非 D 目标，都必须被某张登记表覆盖」。
        """
        # 🔴 判据对象是**完整 wp_code**（`PL` / `F2`）而非首字母 —— 首字母粒度
        # 表达不了「`PL` 不是底稿」这件事（`P` 看起来像个循环字母，实则是报表前缀）。
        wp = _parse_wp_triples()
        all_targets = {t[0] for triples in wp.values() for t in triples}
        non_d_targets = {
            code for code in all_targets if not code.startswith(_IN_SCOPE_CYCLE)
        }
        # 反向锚点：派生结果非空，否则下面的断言恒成立 = 空转
        assert len(non_d_targets) >= 5, (
            f"从预设派生出的非 D 目标只有 {sorted(non_d_targets)}，"
            "解析疑似失效（实测应有 E1/F2/G1/.../PL 二十个以上）。"
        )

        # 一个 target 算「已认领」有两条路径：
        #   ① 完整 wp_code 登记在「非底稿目标」表里（`PL`）
        #   ② 其**循环字母**登记在「范围外循环」表里（`F2` → `F`）
        def _claimed(code: str) -> bool:
            return code in OUT_OF_SCOPE_NON_WORKPAPER_TARGETS or (
                code[:1] in OUT_OF_SCOPE_CYCLES
            )

        unclaimed = sorted(t for t in non_d_targets if not _claimed(t))
        assert not unclaimed, (
            f"以下非 D 目标在预设里存在但无任何范围外登记：{unclaimed}\n"
            "两张登记表的分工：\n"
            "  OUT_OF_SCOPE_CYCLES               —— 目标是**底稿**，各 per-cycle spec 按本机制补映射\n"
            "  OUT_OF_SCOPE_NON_WORKPAPER_TARGETS —— 目标**不是底稿**（如 PL 利润表），\n"
            "                                       本 spec 的取值层结构上取不到，需另一条 resolver\n"
            "🔴 不要把非底稿目标塞进 OUT_OF_SCOPE_CYCLES —— 那会暗示「补个映射就行」，"
            "而真实情况是取值层要换数据源。"
        )

    def test_non_workpaper_targets_are_really_not_workpapers(self) -> None:
        """反向自检：登记为「非底稿」的 target 确实不是循环编号。

        缺了这条，有人可以把真实循环（如 `F2`）塞进
        `OUT_OF_SCOPE_NON_WORKPAPER_TARGETS` 来绕过「按本机制补映射」的义务。
        """
        import re as _re

        for target in OUT_OF_SCOPE_NON_WORKPAPER_TARGETS:
            assert not _re.fullmatch(r"[A-Z]\d+", target), (
                f"{target!r} 形如循环底稿编号（字母+数字），不该登记为「非底稿目标」。\n"
                "真实底稿必须走 OUT_OF_SCOPE_CYCLES 并由 per-cycle spec 补映射。"
            )
            assert len(OUT_OF_SCOPE_NON_WORKPAPER_TARGETS[target]) >= 20, (
                f"{target} 的登记理由少于 20 字"
            )

    def test_non_workpaper_targets_not_in_anchor_map(self) -> None:
        """非底稿目标不得进 `ANCHOR_MAP` —— 取值层对它们结构上取不到数。"""
        leaked = sorted(
            {k[0] for k in ANCHOR_MAP if k[0] in OUT_OF_SCOPE_NON_WORKPAPER_TARGETS}
        )
        assert not leaked, (
            f"ANCHOR_MAP 含非底稿目标 {leaked} —— `read_anchor_value` 经 "
            "`wp_index` JOIN 定位底稿，对报表类 target 必返 NO_WORKPAPER，"
            "映射进去只会产生「永远取不到数却看起来已对齐」的假象。"
        )

    def test_reasons_have_substance(self) -> None:
        bad = [f"  {k}: {len(v)} 字" for k, v in OUT_OF_SCOPE_CYCLES.items() if len(v) < 20]
        assert not bad, "以下范围外登记理由过短：\n" + "\n".join(bad)

    def test_anchor_map_has_no_foreign_cycle(self) -> None:
        """防越界对齐后无人维护。"""
        foreign = sorted({k[0] for k in ANCHOR_MAP if not k[0].startswith(_IN_SCOPE_CYCLE)})
        assert not foreign, (
            f"ANCHOR_MAP 含非 D 循环 wp_code：{foreign}\n"
            "其余循环由各 per-cycle spec 按本机制补，本 spec 不越界。"
        )

    def test_change_ledger_keys(self) -> None:
        for key in ("prev_year_dimension", "frontend_persist_derived_columns"):
            assert key in OUT_OF_SCOPE_CHANGES, (
                f"OUT_OF_SCOPE_CHANGES 缺 {key!r} —— "
                "范围外的数据模型/前端变更必须显式登记，否则下个会话不知道正解在哪。"
            )
            assert len(OUT_OF_SCOPE_CHANGES[key]) >= 20

    def test_two_wp_paths_registered(self) -> None:
        """Property 15：两条 WP 实现路径的差异已登记，防后来者"统一"。"""
        assert len(WP_IMPLEMENTATION_PATHS) >= 2, (
            "WP_IMPLEMENTATION_PATHS 应登记 prefill_engine 与 formula_engine 两条路径。"
        )
        blob = json.dumps(WP_IMPLEMENTATION_PATHS, ensure_ascii=False)
        for marker in ("prefill_engine", "formula_engine", "checklist_responses"):
            assert marker in blob, f"两路径登记里缺 {marker}"
