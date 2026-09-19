"""G7 列对齐与取数收口 —— 真实库**只读**验收。

spec: `.kiro/specs/g7-column-alignment-and-extraction-closure` Task 22（R7.5 / R11.4）

三块验收：

A. **G7 render 三条判据**（对每个有 `1511` 数据的项目）
   1. `tb_source_codes.resolved_from` —— 每个语义槽真定位到了（不是 `none` 兜底为空）
   2. `parent_check` 的父子勾稽差额 == 0
   3. `tb_leaf_categories` 的桶键 ⊆ 单一真源 `G7_INVESTMENT_BUCKETS`，且扁平兼容键
      `cost` 与类别桶 closing 之和自洽

B. **槽级 `row_code` 前后对照**（对 `DECLARED_SLOT_ROW_CODES` 登记的每条）
   声明该字段的目的是消掉「备抵自成一条报表行」导致的假冲突。故必须同时成立：
   - **假告警只减不增**：`conflicts(声明后)` ⊆ `conflicts(声明前)`
   - **定位结果逐字不变**：每槽 `codes` / `standard_codes` / `matched` / `resolved_from`
     在「声明前 vs 声明后」完全相同（`row_code` 只参与冲突检测，不参与定位）

   🔴 「声明前」不靠 git 回退取得 —— 用 `dataclasses.replace(slot, row_code=None)`
   在同一次运行里现算，两边喂同一个 session、同一个项目、同一份科目表。
   这样对照是**同条件**的，不受并发改动与库状态漂移影响。

C. **裁决未声明的 3 条**（`ADJUDICATED_NOT_DECLARED`）
   逐条核对「代码里确实没声明」，并如实标注为 `NOT-DECLARED`（不是缺陷）。

判据无法验证时一律输出 **`UNVERIFIABLE`** 并写明原因（禁用 fixture 冒充真实库）：
灰度开关关闭 / 项目无科目表 / render 抛错 / 该槽在本项目无数据，都属此类。

🔴 全程**只读**：本脚本无 `--apply`、不 commit、`finally` 里显式 rollback。
🔴 连库用**一次性专用 engine + NullPool + 同 loop dispose**，不碰
   `app.core.database` 的共享池（模块级 `asyncio.run` 借共享池后关 loop 会双向污染
   同批连库测试）。

用法::

    python backend/scripts/diagnose/verify_g7_alignment_live.py
    python backend/scripts/diagnose/verify_g7_alignment_live.py --limit 3
    python backend/scripts/diagnose/verify_g7_alignment_live.py --json out.json

退出码：0 = 无 FAIL（UNVERIFIABLE / WARN 不算失败）；2 = 有 FAIL；3 = 库不可达。
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.routers.wp_render_strategies import (  # noqa: E402
    _g7_long_term_equity_main as g7_render,
)
from app.routers.wp_render_strategies._context import RenderContext  # noqa: E402
from app.services.four_table.g7_investment_buckets import (  # noqa: E402
    CATEGORY_BUCKETS,
    G7_INVESTMENT_BUCKETS,
)
from app.services.four_table.semantic_account_resolver import (  # noqa: E402
    SemanticAccountSpec,
    ResolverContext,
    resolve_semantic_accounts,
)

# ─────────────────────────── 状态常量 ───────────────────────────

OK = "OK"
FAIL = "FAIL"
WARN = "WARN"
UNVERIFIABLE = "UNVERIFIABLE"
NOT_DECLARED = "NOT-DECLARED"

#: 单一真源的桶键集合（新增桶只改 `g7_investment_buckets.py`，此处自动跟随）
_ALL_BUCKET_KEYS = {b.bucket for b in G7_INVESTMENT_BUCKETS}


def _load_slot_registry() -> tuple[dict, dict, dict]:
    """从守卫测试里 import 登记表 —— **不在本脚本里抄第二份清单**。

    `DECLARED_SLOT_ROW_CODES` / `ADJUDICATED_NOT_DECLARED` 的真源是
    `backend/tests/four_table/test_semantic_slot_row_code.py`；脚本与守卫共用同一份，
    任一侧增删都不会出现「脚本验了 4 条而守卫管着 6 条」的分叉。

    🔴 `sys.modules` 必须先注册再 `exec_module`：该模块里有 frozen dataclass，
    `dataclasses` 在处理时会 `sys.modules.get(cls.__module__).__dict__`，
    未注册则 `AttributeError: 'NoneType' object has no attribute '__dict__'`。
    """
    import importlib.util

    path = _BACKEND / "tests" / "four_table" / "test_semantic_slot_row_code.py"
    spec = importlib.util.spec_from_file_location("_g7_slot_registry", path)
    if spec is None or spec.loader is None:  # pragma: no cover - 路径异常
        raise RuntimeError(f"无法加载登记表：{path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_g7_slot_registry"] = mod
    spec.loader.exec_module(mod)

    specs: dict[str, SemanticAccountSpec] = {
        "G4": mod.G4_SPEC,
        "G7": mod.G7_SPEC,
        "H2": mod.H2_ACCOUNT_SPEC,
        "H3": mod.H3_ACCOUNT_SPEC,
        "H7": mod.H7_ACCOUNT_SPEC,
        "D6": mod.D6_SPEC,
        "I3": mod.I3_SPEC,
        "D1": mod.D1_SPEC,
        "D2": mod.D2_SPEC,
    }
    return mod.DECLARED_SLOT_ROW_CODES, mod.ADJUDICATED_NOT_DECLARED, specs


# ─────────────────────────── 连库 ───────────────────────────


def _database_url() -> str:
    url = str(settings.DATABASE_URL)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _connect_args() -> dict:
    return {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}


def _render_ctx(db, project_id, year: int) -> RenderContext:
    """最小 RenderContext —— G7 render 只读 db / project_id / year / wp_code。

    `wp_id` 仅作占位（render 不据此写库）；`parsed_data=None` 表示「底稿尚无手工数据」，
    这正是预填路径要覆盖的形态。
    """
    wp = SimpleNamespace(
        id=None, project_id=project_id, parsed_data=None,
        wp_code="G7", name="长期股权投资",
    )
    cls = SimpleNamespace(
        sheet_name="长期股权投资审定表G7-1", wp_code="G7", class_code="G7",
        component_type="g7-long-term-equity-main", is_index=False,
    )
    return RenderContext(
        db=db,
        project_id=project_id,
        wp_id=project_id,
        wp_code="G7",
        working_paper=wp,  # type: ignore[arg-type]
        classification=cls,  # type: ignore[arg-type]
        component_type="g7-long-term-equity-main",
        sheet_html_data=None,
        sheet_schema=None,
        template_file_path=None,
        year=year,
        business_category="A",
        classifications=[cls],  # type: ignore[list-item]
    )


async def _enumerate_projects(db, limit: int | None, only: list[str]) -> list[Any]:
    """枚举有 `1511`（长期股权投资）数据的 (项目, 年度)。

    按 `tb_balance` 实际有行判定 —— 不用 `trial_balance`（那里只有一级总额，
    且多个项目金额为 0 的行也在，会把「无数据」算成「有数据」）。
    """
    sql = (
        "SELECT p.id, p.name, p.audit_year, p.template_type, "
        "       count(*) AS leaf_rows "
        "FROM projects p JOIN tb_balance b ON b.project_id = p.id "
        "WHERE p.is_deleted = false AND b.is_deleted = false "
        "  AND b.account_code LIKE '1511%' "
        + ("  AND p.id::text = ANY(:only) " if only else "")
        + "GROUP BY p.id, p.name, p.audit_year, p.template_type "
        "ORDER BY count(*) DESC, p.name"
    )
    params: dict[str, Any] = {}
    if only:
        params["only"] = only
    rows = (await db.execute(sa.text(sql), params)).fetchall()
    return list(rows[:limit] if limit else rows)


# ─────────────────────────── A. render 三条判据 ───────────────────────────


#: `parent_check` 的两种真实契约（都要支持，形态不认识时判 UNVERIFIABLE 而非静默 OK）
#:
#: - **扁平态** = G7 自建（`_g7_long_term_equity_main._build_tb_source_codes`）::
#:       {"leaf_sum": .., "parent": .., "diff": ..}       ← 只覆盖 gross 槽，字段叫 `diff`
#: - **嵌套态** = 共享件 `four_table.parent_check.build_parent_check`::
#:       {slot_key: {"leaf_sum","parent","trial_balance","diff_parent","diff_trial",
#:                   "convention","trial_net_of","consistent"}}
#:
#: 🔴 初版只按嵌套态写、并对非 dict 的 value 直接当差额用 ⇒ 把扁平态的
#:    `leaf_sum=500000.0` 当成「差额 500000」报 FAIL；而扁平态三值恰好全 0 的项目
#:    又被判成「3 组差额全 0」的 OK。**同一个缺陷同时制造假红与假绿**。
_FLAT_DIFF_KEYS = ("diff", "diff_parent")


def _check_parent_check(pchk, tag: str) -> dict:
    """判据②：父子勾稽差额为 0。"""
    base = {"block": "A", "check": "② parent_check.diff", "target": tag}
    if not isinstance(pchk, dict) or not pchk:
        return {**base, "status": UNVERIFIABLE, "detail": "render 未下发 parent_check"}

    def _num(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    nested = {k: v for k, v in pchk.items() if isinstance(v, dict)}
    if nested:
        nonzero, zero_zero = {}, []
        for key, entry in nested.items():
            diff = _num(entry.get("diff_parent", entry.get("diff")))
            leaf, parent = _num(entry.get("leaf_sum")), _num(entry.get("parent"))
            if diff is None:
                nonzero[key] = f"差额字段缺失/非数值：{sorted(entry)[:6]}"
            elif abs(diff) > 0.005:
                nonzero[key] = diff
            elif not leaf and not parent:
                zero_zero.append(key)
        if nonzero:
            return {**base, "status": FAIL, "detail": f"差额非 0：{nonzero}"}
        if len(zero_zero) == len(nested):
            return {**base, "status": UNVERIFIABLE,
                    "detail": f"{len(nested)} 组的 leaf_sum 与 parent **都是 0** ⇒ "
                              f"差额恒 0，不构成勾稽成立的证据（本项目该科目无余额）"}
        return {**base, "status": OK,
                "detail": f"{len(nested)} 组父子勾稽差额全部为 0"
                          + (f"（其中 {len(zero_zero)} 组两口径皆 0，不计入证据）"
                             if zero_zero else "")}

    # 扁平态：整个 dict 就是一次勾稽结果
    diff_key = next((k for k in _FLAT_DIFF_KEYS if k in pchk), None)
    if diff_key is None:
        return {**base, "status": UNVERIFIABLE,
                "detail": f"parent_check 形态无法识别（既非嵌套态也无 "
                          f"{_FLAT_DIFF_KEYS} 字段）：keys={sorted(pchk)}"}
    diff = _num(pchk.get(diff_key))
    leaf, parent = _num(pchk.get("leaf_sum")), _num(pchk.get("parent"))
    if diff is None:
        return {**base, "status": UNVERIFIABLE,
                "detail": f"{diff_key} 非数值：{pchk.get(diff_key)!r}"}
    if abs(diff) > 0.005:
        return {**base, "status": FAIL,
                "detail": f"{diff_key}={diff}（leaf_sum={leaf} parent={parent}）"}
    if not leaf and not parent:
        return {**base, "status": UNVERIFIABLE,
                "detail": f"leaf_sum 与 parent **都是 0** ⇒ {diff_key} 恒 0，"
                          f"不构成勾稽成立的证据（本项目 1511 叶子无余额）"}
    return {**base, "status": OK,
            "detail": f"{diff_key}=0（leaf_sum=parent={leaf}）⇒ 叶子和与父科目额勾稽成立"}


async def _check_render(db, row) -> list[dict]:
    """G7 render 三条判据。返回若干 finding。"""
    tag = f"{str(row.id)[:8]} {row.name[:20]}"
    findings: list[dict] = []

    if not settings.G7_FOUR_TABLE_EXTRACTION_ENABLED:
        return [{
            "block": "A", "check": "render 三条判据", "target": tag,
            "status": UNVERIFIABLE,
            "detail": "灰度开关 G7_FOUR_TABLE_EXTRACTION_ENABLED=False ⇒ "
                      "render 不下发 tb_leaf_categories/adjudication_prefill，判据无从验证",
        }]

    try:
        payload = await g7_render.render(_render_ctx(db, row.id, int(row.audit_year)))
    except Exception as exc:  # noqa: BLE001 —— 如实记为 UNVERIFIABLE，不吞成 OK
        await db.rollback()
        return [{
            "block": "A", "check": "render 三条判据", "target": tag,
            "status": UNVERIFIABLE, "detail": f"render 抛错：{exc!r}",
        }]

    if not isinstance(payload, dict):
        return [{
            "block": "A", "check": "render 三条判据", "target": tag,
            "status": FAIL, "detail": f"render 返回非 dict：{type(payload).__name__}",
        }]

    pc = payload.get("project_context") or {}
    src = pc.get("tb_source_codes") or {}

    # ① resolved_from：每个槽真定位到了
    slots = src.get("slots")
    if not isinstance(slots, (list, dict)) or not slots:
        findings.append({
            "block": "A", "check": "① resolved_from", "target": tag,
            "status": UNVERIFIABLE,
            "detail": f"tb_source_codes.slots 缺失或为空（keys={sorted(src)[:8]}）",
        })
    else:
        items = slots.values() if isinstance(slots, dict) else slots
        bad = []
        for s in items:
            if not isinstance(s, dict):
                continue
            frm = s.get("resolved_from")
            key = s.get("key") or s.get("slot") or "?"
            if frm in (None, "", "none"):
                bad.append(f"{key}={frm!r}")
        findings.append({
            "block": "A", "check": "① resolved_from", "target": tag,
            "status": OK if not bad else WARN,
            "detail": "全部槽有定位来源" if not bad
                      else f"{len(bad)} 个槽未定位（该科目在本项目可能确实不存在）：{bad[:4]}",
        })

    findings.append(_check_parent_check(src.get("parent_check"), tag))

    # ③ 分类桶 ⊆ 真源；扁平兼容键与类别桶自洽
    cats = payload.get("tb_leaf_categories")
    if not isinstance(cats, dict) or not cats:
        findings.append({
            "block": "A", "check": "③ 分类桶", "target": tag,
            "status": UNVERIFIABLE,
            "detail": "render 未下发 tb_leaf_categories（本项目可能无可归类叶子）",
        })
    else:
        buckets = cats.get("buckets") or {}
        unknown = sorted(set(buckets) - _ALL_BUCKET_KEYS)
        unmapped = cats.get("unmapped") or []
        cost_expected = round(
            sum(float((buckets.get(b) or {}).get("closing") or 0.0) for b in CATEGORY_BUCKETS), 2
        )
        cost_actual = cats.get("cost")
        problems = []
        if unknown:
            problems.append(f"出现真源未声明的桶键 {unknown}")
        try:
            if cost_actual is not None and abs(float(cost_actual) - cost_expected) > 0.005:
                problems.append(f"cost={cost_actual} != 类别桶合计 {cost_expected}")
        except (TypeError, ValueError):
            problems.append(f"cost 非数值：{cost_actual!r}")
        note = (f"桶 {len(buckets)}/{len(_ALL_BUCKET_KEYS)} 命中"
                f"（{sorted(buckets)}）；未归类叶子 {len(unmapped)}")
        if problems:
            status, detail = FAIL, "；".join(problems) + "｜" + note
        elif unmapped:
            status, detail = WARN, note + " ⇒ 未归类叶子未并入任何桶（宁缺勿造，需人工复核）"
        else:
            status, detail = OK, note
        findings.append({
            "block": "A", "check": "③ 分类桶", "target": tag,
            "status": status, "detail": detail,
        })

    return findings


# ─────────────────────────── B. 槽级 row_code 前后对照 ───────────────────────────


def _strip_slot_row_code(spec: SemanticAccountSpec, slot_key: str) -> SemanticAccountSpec:
    """造「声明前」对照变体：把指定槽的 `row_code` 去掉，其余逐字不动。"""
    new_slots = tuple(
        dataclasses.replace(s, row_code=None) if s.key == slot_key else s
        for s in spec.slots
    )
    return dataclasses.replace(spec, slots=new_slots)


def _locating_fingerprint(result) -> dict:
    """定位结果指纹 —— 只取**与定位有关**的字段（`row_code` 只该影响冲突检测）。"""
    return {
        key: {
            "codes": sorted(sl.codes),
            "standard_codes": sorted(sl.standard_codes),
            "matched": sorted(tuple(m) for m in sl.matched),
            "resolved_from": sl.resolved_from,
            "exact": sl.exact,
        }
        for key, sl in sorted(result.slots.items())
    }


async def _row_formulas(db, row_code: str | None) -> list[tuple[str, str | None]]:
    """取某报表行在各适用准则下的公式原文 —— 判断「声明是否对冲突检测有效果」。

    🔴 必查：`IMP-004` / `IMP-012` / `IMP-013` 三条在 `report_config` 里**两个变体
    公式都是 NULL**（2026-08-08 实证）。声明这类行是**有意为之的空兜底**（占位以便
    真源补上公式后自动生效），但它对冲突检测没有任何效果 —— 若不点明，验收输出会是
    笼统的「两侧都无冲突」，读起来像「假告警已消除」，属假绿。
    """
    if not row_code:
        return []
    rows = (await db.execute(
        sa.text(
            "SELECT applicable_standard, formula FROM report_config "
            "WHERE row_code = :c AND is_deleted = false ORDER BY applicable_standard"
        ),
        {"c": row_code},
    )).fetchall()
    return [(r.applicable_standard, r.formula) for r in rows]


async def _check_slot_row_code(db, row, spec_name, spec, slot_key, expect_code) -> list[dict]:
    tag = f"{str(row.id)[:8]} {row.name[:16]} / {spec_name}.{slot_key}"
    ctx = ResolverContext(db=db, project_id=row.id, year=int(row.audit_year))
    before_spec = _strip_slot_row_code(spec, slot_key)
    try:
        after = await resolve_semantic_accounts(ctx, spec)
        before = await resolve_semantic_accounts(ctx, before_spec)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        return [{
            "block": "B", "check": "前后对照", "target": tag,
            "status": UNVERIFIABLE, "detail": f"resolve 抛错：{exc!r}",
        }]

    if not after.chart_available:
        return [{
            "block": "B", "check": "前后对照", "target": tag,
            "status": UNVERIFIABLE,
            "detail": "本项目科目表不可用（全部槽退化为兜底码）⇒ 对照无意义",
        }]

    findings: list[dict] = []
    conf_after_all = {tuple(map(str, c)) for c in after.conflicts}
    conf_before_all = {tuple(map(str, c)) for c in before.conflicts}
    # 🔴 只比**本槽**的冲突：声明 impairment 的 row_code 不该、也不会影响
    #    `eng_mat` / `accum_dep` 等其他槽的冲突。初版拿整个集合比 ⇒ 别的槽有冲突时
    #    会输出「声明前后冲突集合相同」，读起来像「声明没起作用」，是误导。
    conf_after = {c for c in conf_after_all if c and c[0] == slot_key}
    conf_before = {c for c in conf_before_all if c and c[0] == slot_key}
    other_slot_conf = sorted(c for c in conf_after_all if not c or c[0] != slot_key)
    added = sorted(conf_after - conf_before)
    removed = sorted(conf_before - conf_after)

    if added:
        # 🔴 新增冲突 ≠ 一定是回归。`conflicts` 的存在理由正是暴露真冲突
        #    （`report_config` 已实证 6 处错码），故必须**按证据**二分：
        #
        #    - 若该槽**按科目名命中的原始码**恰好就是所声明报表行公式里的码
        #      ⇒ 声明选对了行，冲突来自 `standard_codes` 侧（`account_mapping`
        #        的 auto_fuzzy 错映射会把备抵科目映到原值标准码）⇒ **真冲突**，
        #        属该暴露的问题，登记为 WARN 并给出证据链。
        #    - 否则 ⇒ 我选错了报表行，是真回归 ⇒ FAIL。
        #
        #    实证（2026-08-12，项目 c8621493）：H3.impairment 命中
        #    `1527 投资性房地产减值准备`，IMP-010 公式 = `TB('1527')` ⇒ 逐字一致；
        #    而 `account_mapping` 把 1525/1526/1527 三个备抵全 auto_fuzzy 映到 `1521`
        #    ⇒ 槽的 standard_codes=['1521'] 与 1527 不符。声明前拿 spec 级 BS-027 的
        #    `{1521,1525}` 比，恰好含 1521 ⇒ 假阴性把错映射掩盖了整段历史。
        slot_after = after.slots.get(slot_key)
        matched_codes = {str(c) for c, _n in (slot_after.matched if slot_after else [])}
        row_codes = {str(c) for c in (getattr(after, "report_config_codes", None) or [])}
        declared_codes = {str(c) for conf in added for c in (conf[1] or "").split(",") if c}
        if matched_codes and declared_codes and (matched_codes & declared_codes):
            status = WARN
            detail = (
                f"新增冲突 {added} 属**真冲突**（声明选对了行）："
                f"该槽按名称命中 {sorted(matched_codes)}"
                f"（{[n for _c, n in (slot_after.matched if slot_after else [])]}）"
                f"与所声明报表行的公式码 {sorted(declared_codes)} 逐字一致；"
                f"冲突来自 standard_codes={sorted(slot_after.standard_codes) if slot_after else '?'}"
                f" ⇒ 需查 account_mapping 是否把备抵科目错映到原值标准码。"
                f"（声明前是拿 spec 级 {after.row_code!r} 的 {sorted(row_codes)} 比，"
                f"含错映射目标码 ⇒ 假阴性）"
            )
        else:
            status = FAIL
            detail = (
                f"声明 row_code **新增**了冲突且非真冲突：{added}；"
                f"该槽命中原始码 {sorted(matched_codes)} 与声明行公式码 "
                f"{sorted(declared_codes)} 无交集 ⇒ 疑似选错报表行"
            )
    elif removed:
        status, detail = OK, f"消掉假冲突 {len(removed)} 条：{removed}"
    elif not conf_before and not conf_after:
        declared_row = next(
            (s.row_code for s in spec.slots if s.key == slot_key), None
        )
        formulas = await _row_formulas(db, declared_row)
        with_formula = [(v, f) for v, f in formulas if (f or "").strip()]
        if formulas and not with_formula:
            status, detail = UNVERIFIABLE, (
                f"所声明报表行 {declared_row} 在 report_config 里**公式全为 NULL**"
                f"（{len(formulas)} 个适用准则变体：{[v for v, _f in formulas]}）"
                f" ⇒ 该声明对冲突检测**无实际效果**，属有意为之的空兜底占位；"
                f"不能据此说「假告警已消除」"
            )
        elif not formulas:
            status, detail = UNVERIFIABLE, (
                f"所声明报表行 {declared_row!r} 在 report_config 里**不存在** ⇒ "
                f"声明对冲突检测无效果，需复核该行号"
            )
        else:
            status, detail = UNVERIFIABLE, (
                f"本槽两侧都无冲突（所声明行 {declared_row} 有公式："
                f"{[f for _v, f in with_formula][:2]}）⇒ 该项目该槽本就没有假告警，"
                f"无法据此项目证明声明起了作用"
            )
    else:
        status, detail = WARN, f"本槽声明前后冲突相同：{sorted(conf_after)}"
    if other_slot_conf:
        detail += f"｜同 spec 其他槽仍有冲突（与本次声明无关，仅作上下文）：{other_slot_conf}"
    findings.append({
        "block": "B", "check": "假告警只减不增", "target": tag,
        "status": status, "detail": detail,
    })
    if added:
        # 无论真冲突还是回归，都把 std/原始码/公式码三者并排落到 findings 里，
        # 便于人工与后续 spec 直接引用（审计 UI 铁律：告警必须能追溯）
        slot_after = after.slots.get(slot_key)
        findings.append({
            "block": "B", "check": "新增冲突证据链", "target": tag,
            "status": WARN if status == WARN else FAIL,
            "detail": (
                f"matched={slot_after.matched if slot_after else None} "
                f"codes={slot_after.codes if slot_after else None} "
                f"standard_codes={slot_after.standard_codes if slot_after else None} "
                f"report_row={slot_after.report_row_code if slot_after else None!r} "
                f"spec_row={after.row_code!r} "
                f"spec_formula={getattr(after, 'formula', None)!r}"
            ),
        })

    fp_after, fp_before = _locating_fingerprint(after), _locating_fingerprint(before)
    if fp_after == fp_before:
        findings.append({
            "block": "B", "check": "定位结果逐字不变", "target": tag,
            "status": OK, "detail": f"{len(fp_after)} 个槽的 codes/standard_codes/"
                                    f"matched/resolved_from/exact 全部逐字相同",
        })
    else:
        diff_keys = sorted(k for k in fp_after if fp_after.get(k) != fp_before.get(k))
        findings.append({
            "block": "B", "check": "定位结果逐字不变", "target": tag,
            "status": FAIL,
            "detail": f"声明 row_code 改变了定位结果（它只该参与冲突检测）：槽 {diff_keys}；"
                      f"after={ {k: fp_after[k] for k in diff_keys[:2]} } "
                      f"before={ {k: fp_before.get(k) for k in diff_keys[:2]} }",
        })

    # 槽级 row_code 真的被下发到结果里（否则「声明了」只是源码字面量）
    slot_res = after.slots.get(slot_key)
    if slot_res is None:
        findings.append({
            "block": "B", "check": "report_row_code 下发", "target": tag,
            "status": FAIL, "detail": f"结果里没有槽 {slot_key}",
        })
    elif expect_code is None:
        findings.append({
            "block": "B", "check": "report_row_code 下发", "target": tag,
            "status": OK, "detail": f"登记为无期望码；实际 report_row_code="
                                    f"{slot_res.report_row_code!r}",
        })
    elif slot_res.report_row_code != expect_code:
        findings.append({
            "block": "B", "check": "report_row_code 下发", "target": tag,
            "status": FAIL,
            "detail": f"期望 {expect_code!r}，实际 {slot_res.report_row_code!r}",
        })
    else:
        findings.append({
            "block": "B", "check": "report_row_code 下发", "target": tag,
            "status": OK, "detail": f"report_row_code={expect_code!r} 已随结果下发",
        })
    return findings


# ─────────────────────────── C. 裁决未声明 ───────────────────────────


def _check_adjudicated(adjudicated: dict, specs: dict) -> list[dict]:
    findings: list[dict] = []
    for (spec_name, slot_key), entry in adjudicated.items():
        verdict = entry.get("verdict") if isinstance(entry, dict) else getattr(entry, "verdict", "?")
        spec = specs.get(spec_name)
        if spec is None:
            findings.append({
                "block": "C", "check": "裁决项", "target": f"{spec_name}.{slot_key}",
                "status": FAIL, "detail": "登记表引用的 spec 在代码里不存在",
            })
            continue
        slot = next((s for s in spec.slots if s.key == slot_key), None)
        if slot is None:
            findings.append({
                "block": "C", "check": "裁决项", "target": f"{spec_name}.{slot_key}",
                "status": FAIL, "detail": "登记表引用的槽在 spec 里不存在",
            })
        elif slot.row_code is not None:
            findings.append({
                "block": "C", "check": "裁决项", "target": f"{spec_name}.{slot_key}",
                "status": FAIL,
                "detail": f"裁决为「不声明」({verdict}) 但代码里已声明 row_code="
                          f"{slot.row_code!r} ⇒ 登记表与代码分叉",
            })
        else:
            findings.append({
                "block": "C", "check": "裁决项", "target": f"{spec_name}.{slot_key}",
                "status": NOT_DECLARED,
                "detail": f"裁决 {verdict}；代码里确实未声明（符合裁决）",
            })
    return findings


# ─────────────────────────── 主流程 ───────────────────────────


async def run(args) -> tuple[list[dict], dict]:
    declared, adjudicated, specs = _load_slot_registry()
    findings: list[dict] = []
    meta: dict[str, Any] = {
        "gray_flag_G7_FOUR_TABLE_EXTRACTION_ENABLED": bool(
            settings.G7_FOUR_TABLE_EXTRACTION_ENABLED
        ),
        "declared_entries": [f"{k[0]}.{k[1]}={v}" for k, v in declared.items()],
        "bucket_source_keys": sorted(_ALL_BUCKET_KEYS),
    }

    engine = create_async_engine(
        _database_url(), poolclass=NullPool, connect_args=_connect_args(), echo=False
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            try:
                projects = await _enumerate_projects(db, args.limit, args.project or [])
            except Exception as exc:  # noqa: BLE001
                raise SystemExit(f"[库不可达] {exc!r}") from exc

            meta["projects"] = [
                {"id": str(r.id), "name": r.name, "year": int(r.audit_year),
                 "template_type": r.template_type, "leaf_rows_1511": int(r.leaf_rows)}
                for r in projects
            ]
            if not projects:
                findings.append({
                    "block": "A", "check": "项目枚举", "target": "-",
                    "status": UNVERIFIABLE,
                    "detail": "真实库里没有任何项目有 1511 明细数据 ⇒ A/B 两块无从验证",
                })

            for r in projects:
                findings.extend(await _check_render(db, r))

            for (spec_name, slot_key), expect_code in declared.items():
                spec = specs.get(spec_name)
                if spec is None:
                    findings.append({
                        "block": "B", "check": "登记表", "target": f"{spec_name}.{slot_key}",
                        "status": FAIL, "detail": "登记表引用的 spec 在代码里不存在",
                    })
                    continue
                if not any(s.key == slot_key for s in spec.slots):
                    findings.append({
                        "block": "B", "check": "登记表", "target": f"{spec_name}.{slot_key}",
                        "status": FAIL, "detail": "登记表引用的槽在 spec 里不存在",
                    })
                    continue
                for r in projects:
                    findings.extend(
                        await _check_slot_row_code(db, r, spec_name, spec, slot_key, expect_code)
                    )

            findings.extend(_check_adjudicated(adjudicated, specs))
            # 🔴 只读收尾：本脚本不写任何东西，显式回滚以免留下开着的事务
            await db.rollback()
    finally:
        await engine.dispose()

    return findings, meta


def _report(findings: list[dict], meta: dict, quiet: bool) -> int:
    tally: dict[str, int] = {}
    for f in findings:
        tally[f["status"]] = tally.get(f["status"], 0) + 1

    print("=" * 96)
    print("G7 列对齐与取数收口 —— 真实库只读验收")
    print("=" * 96)
    print(f"灰度开关 G7_FOUR_TABLE_EXTRACTION_ENABLED = "
          f"{meta['gray_flag_G7_FOUR_TABLE_EXTRACTION_ENABLED']}")
    print(f"有 1511 数据的 (项目, 年度) = {len(meta.get('projects') or [])}")
    for pr in meta.get("projects") or []:
        print(f"  · {pr['id'][:8]} {pr['name'][:26]:<26} {pr['year']} "
              f"{pr['template_type'] or '-':<12} 叶子行={pr['leaf_rows_1511']}")
    print(f"槽级 row_code 登记 {len(meta['declared_entries'])} 条："
          f"{meta['declared_entries']}")
    print(f"分类桶真源 {len(meta['bucket_source_keys'])} 个：{meta['bucket_source_keys']}")
    print()

    order = [FAIL, WARN, UNVERIFIABLE, NOT_DECLARED, OK]
    for status in order:
        rows = [f for f in findings if f["status"] == status]
        if not rows:
            continue
        if quiet and status in (OK, NOT_DECLARED):
            print(f"[{status}] {len(rows)} 条（--quiet 已折叠）")
            continue
        print(f"── [{status}] {len(rows)} 条 " + "─" * 60)
        for f in rows:
            print(f"  ({f['block']}) {f['check']:<22} {f['target']:<46} {f['detail']}")
        print()

    print("=" * 96)
    print("合计：" + "  ".join(f"{k}={tally.get(k, 0)}" for k in order))
    verdict = "FAIL 🔴" if tally.get(FAIL) else "PASS ✅"
    print(f"结论：{verdict}"
          + ("（UNVERIFIABLE/WARN 不计入失败，但需逐条人工过目）"
             if (tally.get(UNVERIFIABLE) or tally.get(WARN)) else ""))
    return 2 if tally.get(FAIL) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="G7 列对齐与取数收口的真实库只读验收（无 --apply，不写库）"
    )
    parser.add_argument("--project", action="append", help="只验证指定 project_id（可重复）")
    parser.add_argument("--limit", type=int, help="只取前 N 个项目")
    parser.add_argument("--json", dest="json_out", help="把 findings 写成 JSON")
    parser.add_argument("--quiet", action="store_true", help="折叠 OK / NOT-DECLARED 明细")
    args = parser.parse_args(argv)

    findings, meta = asyncio.run(run(args))
    code = _report(findings, meta, args.quiet)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"meta": meta, "findings": findings}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"[json] {args.json_out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
