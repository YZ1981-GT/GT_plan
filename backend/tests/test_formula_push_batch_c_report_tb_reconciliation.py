"""审定表族审定合计按前端真实存储取数（全族逐科目，走真实推送引擎）。

原 C10（spec formula-push-balance-adj-batch-c 需求 C10）断言「审定合计 = 报表 TB 解析器取到的 Σ 全部科目」，
并按 ``{X}-1-rows`` rowId 清单 + 扁平 ``-unadj/-aje/-rje`` 键造数 —— 两个前提都不成立：
① 前端只有 K2 是那种存法，其余底稿全部读空，真库 G / H / I 审定合计恒为 0；
② 审定合计是底稿审定表的数，不是试算表（发布到试算表之前两者本就可以不等），H1 / I1 的 Σ 全部科目还把
   累计折旧 / 摊销、减值准备当正数相加。
spec formula-fetch-followup-defect-closure R6.3 改写为：按 ``balance_adj_extract.AUDITED_SOURCES`` 的声明
（逐底稿现读前端确认）造前端形态的数据，期望值由造数时的已知金额直接算出（不调被测求值函数），推送后逐键比对；
声明为读不到的写空，不写 0。K2 ~ K6 的扁平键与前端一致，沿用原造数方式。
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models.audit_platform_models import Adjustment, AdjustmentEntry, TrialBalance
from app.services.formula_push.bindings import get_binding, supported_wp_codes
from app.services.formula_push.bindings.balance_adj import _SPECS, BalanceAdjudicationBinding
from app.services.formula_push.bindings.balance_adj_extract import (
    AUDITED_SOURCES,
    ByMode,
    Key,
    Rows,
    Unavailable,
    formula_text,
)
from app.services.formula_push.js_compat import js_number_to_string
from app.services.formula_push.rules import load_rules, rules_for
from tests._formula_push_env import make_env

_BATCH_C_CODES = tuple(sorted(_SPECS))
_RULES = load_rules()

#: 主清单两行（一行 111 = 100 + 10 + 1，一行 200）+ 一条小计行 + 一条「合计」行（两条都不得计入）；备抵清单一行 50
_GROSS_ROW_AMOUNTS = ((100, 10, 1), (200, 0, 0))
_GROSS = 311.0
_CONTRA = 50.0
_KEY_VALUE = "1234.5"


def _audited_rules(wp_code: str):
    return tuple(
        rule
        for rule in rules_for(_RULES, wp_code=wp_code)
        if rule.stage == "derived"
        and rule.source.kind == "derivation"
        and rule.source.name == f"{wp_code.lower()}_audited_total"
    )


# ── 按声明造前端形态的数据（期望值来自造数金额，不调被测求值函数） ─────────────────


def _amounts(group: tuple[str, ...], total_parts: tuple[int, ...]) -> dict[str, int]:
    """把一行金额摊到字段组上：三字段组 (100, 10, 1)；两字段组 (100, 11)（行合计都是 111）。"""
    if len(group) == len(total_parts):
        return dict(zip(group, total_parts))
    head, rest = total_parts[0], sum(total_parts[1:])
    return {group[0]: head, **({group[1]: rest} if len(group) > 1 else {})}


def _rows_fixture(source: Rows, arrays: dict[str, list[dict]]) -> float:
    """往 ``arrays``（item_id → 行数组）里造行，返回该来源的期望合计。"""
    group = source.amount_fields[0]
    expected = 0.0
    for index, rl in enumerate(source.lists):
        section = {rl.section_field: rl.section} if rl.section is not None else {}
        bucket = arrays.setdefault(rl.item_id, [])
        marker = (rl.item_id, rl.section, rl.sign)
        if index == 0:
            if not any(r.get("_marker") == marker for r in bucket):
                for n, parts in enumerate(_GROSS_ROW_AMOUNTS):
                    bucket.append({"_marker": marker, "name": f"甲{n}", "category": f"甲{n}", **section,
                                   **_amounts(group, parts)})
                # 小计行 / 合计行不得计入
                bucket.append({"_marker": marker, "name": "子项", "isSubtotal": True, **section,
                               **_amounts(group, (9999, 0, 0))})
                bucket.append({"_marker": marker, "name": "合计", "category": "合计", "projectName": "合计",
                               **section, **_amounts(group, (8888, 0, 0))})
            expected += _GROSS
        else:
            if not any(r.get("_marker") == marker for r in bucket):
                bucket.append({"_marker": marker, "name": "乙", "category": "乙", **section,
                               **_amounts(group, (int(_CONTRA), 0, 0))})
            expected += rl.sign * _CONTRA
    return expected


def _source_fixture(source, arrays, remark, conclusion) -> float | None:
    if isinstance(source, Unavailable):
        return None
    if isinstance(source, Key):
        (conclusion if source.column == "conclusion" else remark)[source.item_id] = _KEY_VALUE
        return float(_KEY_VALUE)
    if isinstance(source, ByMode):  # 不存模式键 ⇒ 走默认分支（H3 两种模式另有专测）
        return _source_fixture(source.default, arrays, remark, conclusion)
    if isinstance(source, Rows):
        return _rows_fixture(source, arrays)
    raise TypeError(source)


def _flat_fixture(bases: list[str], remark: dict[str, str]) -> float:
    """K2 ~ K6 扁平行键（与前端一致）：前两行 111 / 200，其余行不存 ⇒ 311。"""
    for base, parts in zip(bases, _GROSS_ROW_AMOUNTS):
        for suffix, value in zip(("unadj", "aje", "rje"), parts):
            remark[f"{base}-{suffix}"] = str(value)
    return _GROSS


def _fixture(wp_code: str) -> tuple[dict[str, str], dict[str, str], dict[str, float | None]]:
    """返回 (remark 列条目, conclusion 列条目, kind → 期望审定合计)。"""
    spec = _SPECS[wp_code]
    remark: dict[str, str] = {}
    conclusion: dict[str, str] = {}
    expected: dict[str, float | None] = {}
    totals = AUDITED_SOURCES.get(wp_code)
    if totals is not None:
        arrays: dict[str, list[dict]] = defaultdict(list)
        expected["receivable"] = _source_fixture(totals.receivable, arrays, remark, conclusion)
        expected["net"] = _source_fixture(totals.net, arrays, remark, conclusion)
        for item_id, rows in arrays.items():
            remark[item_id] = json.dumps([{k: v for k, v in r.items() if k != "_marker"} for r in rows],
                                         ensure_ascii=False)
        return remark, conclusion, expected
    if spec.sections:
        for section, row_keys in spec.sections:
            expected[section] = _flat_fixture([f"{spec.sheet_code}-{section}-{rk}" for rk in row_keys], remark)
        return remark, conclusion, expected
    if spec.dynamic_rows:
        row_ids = ("row-a", "row-b")
        remark[f"{spec.sheet_code}-rows"] = json.dumps(
            [{"rowId": rid, "label": rid, "source": "manual"} for rid in row_ids], ensure_ascii=False)
        total = _flat_fixture([f"{spec.sheet_code}-{rid}" for rid in row_ids], remark)
        return remark, conclusion, {"receivable": total, "net": total}
    prefix = f"{spec.fixed_row_prefix}-" if spec.fixed_row_prefix else ""
    total = _flat_fixture([f"{spec.sheet_code}-{prefix}{rk}" for rk in spec.fixed_row_keys], remark)
    return remark, conclusion, {"receivable": total, "net": total}


async def _insert_workpaper(env, wp_code: str) -> uuid.UUID:
    index_id, wp_id = uuid.uuid4(), uuid.uuid4()
    async with env.factory() as db:
        await db.execute(
            sa.text("INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, :c)"),
            {"i": str(index_id), "p": str(env.pid), "c": wp_code},
        )
        await db.execute(
            sa.text("INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"),
            {"w": str(wp_id), "p": str(env.pid), "i": str(index_id)},
        )
        await db.commit()
    return wp_id


async def _seed_entries(env, wp_id: uuid.UUID, remark: dict[str, str], conclusion: dict[str, str]) -> None:
    async with env.factory() as db:
        for item_id in sorted(set(remark) | set(conclusion)):
            await db.execute(
                sa.text(
                    "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, conclusion, updated_at) "
                    "VALUES (:id, :p, :w, :i, :r, :c, :t)"
                ),
                {"id": str(uuid.uuid4()), "p": str(env.pid), "w": str(wp_id), "i": item_id,
                 "r": remark.get(item_id), "c": conclusion.get(item_id),
                 "t": "2026-10-01 08:00:00.000000+00:00"},
            )
        await db.commit()


async def _read_remarks(env, wp_id: uuid.UUID) -> dict[str, str | None]:
    async with env.factory() as db:
        rows = (await db.execute(
            sa.text("SELECT item_id, remark FROM checklist_responses WHERE wp_id = :w"), {"w": str(wp_id)},
        )).all()
    return {row[0]: row[1] for row in rows}


# ── 守卫 ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("wp_code", _BATCH_C_CODES)
async def test_audited_total_reads_frontend_storage(monkeypatch, wp_code: str) -> None:
    """每个审定表族科目：按声明的前端存储造数 → 推送 → 派生合计逐键等于期望；读不到的写空、旧 0 被清掉。"""
    async with make_env(
        monkeypatch,
        extra_tables=(TrialBalance.__table__, Adjustment.__table__, AdjustmentEntry.__table__),
    ) as env:
        wp_id = await _insert_workpaper(env, wp_code)
        remark, conclusion, expected = _fixture(wp_code)
        stale = {rule.target.item_id: "0" for rule in _audited_rules(wp_code)}  # 旧推送恒写的 0
        await _seed_entries(env, wp_id, {**stale, **remark}, conclusion)

        result = await env.push(codes=(wp_code,))
        assert result.status == "succeeded"

        saved = await _read_remarks(env, wp_id)
        for rule in _audited_rules(wp_code):
            kind = rule.source.params_map["kind"]
            want, got = expected[kind], saved.get(rule.target.item_id)
            if want is None:
                assert got in (None, ""), f"{wp_code} {kind}：前端没有可读来源，应留空，实得 {got!r}"
            else:
                assert got == js_number_to_string(want), f"{wp_code} {kind}：期望 {want}，实得 {got!r}"


def test_every_subject_has_contra_aware_net_or_states_why() -> None:
    """有备抵的底稿（H1 / H2 / H3 成本模式 / H4 / H5 / I1）净值来源里必须真有减项清单 —— 防回到「净值 = 原值」。"""
    def has_minus(source) -> bool:
        if isinstance(source, Rows):
            return any(rl.sign < 0 for rl in source.lists)
        if isinstance(source, ByMode):
            return has_minus(source.default)
        return False

    for code in ("H1", "H2", "H3", "H4", "H5", "I1"):
        assert has_minus(AUDITED_SOURCES[code].net), f"{code} 的净值没有减项清单"
        assert not has_minus(AUDITED_SOURCES[code].receivable), f"{code} 的原值不应含减项"


_FE_SRC = Path(__file__).resolve().parents[2] / "audit-platform" / "frontend" / "src"


def _fe_sources() -> list[str]:
    files = [p for p in _FE_SRC.rglob("*") if p.suffix in (".ts", ".vue") and "__tests__" not in p.parts
             and not p.name.endswith((".spec.ts", ".test.ts"))]
    assert len(files) > 500, f"只扫到 {len(files)} 个前端文件，路径判据失效"
    return [p.read_text(encoding="utf-8", errors="replace") for p in files]


def _fe_mentions(key: str, texts: list[str]) -> bool:
    """前端生产代码里出现该键：整键字面量，或「前缀常量 + 模板串后缀」（如 ITEM_PREFIX='H1-1' + `${…}-cost-rows`）。"""
    if any(f"{q}{key}{q}" in t for t in texts for q in ("'", '"', "`")):
        return True
    parts = key.split("-")
    for i in range(1, len(parts)):
        prefix, suffix = "-".join(parts[:i]), "-" + "-".join(parts[i:])
        if any((f"'{prefix}'" in t or f'"{prefix}"' in t) and f"}}{suffix}`" in t for t in texts):
            return True
    return False


def _declared_keys() -> set[str]:
    keys: set[str] = set()

    def walk(source) -> None:
        if isinstance(source, Key):
            keys.add(source.item_id)
        elif isinstance(source, Rows):
            keys.update(rl.item_id for rl in source.lists)
        elif isinstance(source, ByMode):
            keys.add(source.mode_key)
            for _, case in source.cases:
                walk(case)
            walk(source.default)

    for totals in AUDITED_SOURCES.values():
        walk(totals.receivable)
        walk(totals.net)
    return keys


def test_declared_frontend_keys_exist_in_frontend_code() -> None:
    """声明读的每个前端键都真在前端生产代码里出现 —— 防再读一个前端从不写的键（本次修的正是这类：恒为 0）。"""
    texts = _fe_sources()
    missing = sorted(k for k in _declared_keys() if not _fe_mentions(k, texts))
    assert not missing, f"前端生产代码里找不到这些键：{missing}"
    # 判据自检：编造的键必须判为不存在（否则上面的断言是空转）
    assert not _fe_mentions("H1-1-cost-rows-not-exist", texts)
    assert not _fe_mentions("K7-1-rows-audited-sum", texts)


def test_rule_text_matches_declared_source() -> None:
    """推送面板展示的算式说明由声明生成：改了前端来源声明却没重写规则说明 ⇒ 打红（防说明与取数口径各说各话）。"""
    for code, totals in AUDITED_SOURCES.items():
        rules = _audited_rules(code)
        assert {r.source.params_map["kind"] for r in rules} == {"receivable", "net"}, code
        for rule in rules:
            kind = rule.source.params_map["kind"]
            name = rule.source.formula_text.split("审定合计")[0]
            assert rule.source.formula_text == formula_text(name, totals, kind), rule.rule_id
            assert totals.origin in rule.description, rule.rule_id


def test_batch_c_subject_registry_and_rule_coverage() -> None:
    """参数集 = 全部已注册的审定表族 binding；每个科目恰有对应 kind 的派生规则。"""
    registered_balance_adj = {
        code
        for code in supported_wp_codes()
        if isinstance(get_binding(code), BalanceAdjudicationBinding)
    }
    assert set(_BATCH_C_CODES) == registered_balance_adj
    assert len(_BATCH_C_CODES) == 30
    for code in _BATCH_C_CODES:
        rules = _audited_rules(code)
        assert rules
        expected_kinds = {"asset", "liab"} if _SPECS[code].sections else {"receivable", "net"}
        assert {rule.source.params_map["kind"] for rule in rules} == expected_kinds
