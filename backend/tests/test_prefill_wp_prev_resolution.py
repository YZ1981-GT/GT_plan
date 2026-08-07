"""`WP()` / `PREV()` 死链守卫（Wave 1：先对当前状态打红）。

spec: .kiro/specs/prefill-wp-prev-resolution-repair/
      Task 1（连库实证 `cells` 零命中）
      Task 2（characterization：修复前恒返 None）
      Task 3（源码守卫：禁 `cells` 读法）
      Requirements 1.1, 3.2, 4.1, 4.2, 4.3, 4.4

背景
----

`prefill_engine._resolve_wp_formula` 与 `_resolve_prev_formula` 都从
``working_paper.parsed_data['cells']`` 取值，而该键在当前平台的**任何写入路径下都不产生**
（真实库实测零命中）⇒ 两个 resolver 恒返 ``None`` 且 fail-soft 无告警，合计 **334 条预设**
（`WP()` 191 / `PREV()` 143）从未取到过任何数值。

🔴 **本文件的 Task 3 部分在 Wave 3 交付前是「预期打红」的** —— 这是 spec 明确要求的
「守卫先对当前状态打红」：先改代码再写守卫，无法区分「守卫有效」与「守卫空转」
（覆盖率守卫第一版成为假绿源的机理）。Task 6/7 接线后它应自动转绿。

🔴 **Task 2 的 characterization 断言方向与 Task 3 相反** —— 它锁死「当前恒返 None」，
在 Task 6/7 交付后**必须反转**（改为断言已对齐锚点能取到数）。两者一起构成
「修复前后行为确实变了」的双向证据。

连库测试的两个坑（memory 已登记）
--------------------------------

1. ``app.core.database`` 的连接池绑定**首个**事件循环 → pytest-asyncio 默认每个测试新建
   loop，第二个连库测试起会抛 ``AttributeError: 'NoneType' object has no attribute 'send'``；
   若 fixture 里 ``except → pytest.skip`` 就变成**静默跳过 = 假绿**。
   ⇒ 本文件用「一次 ``asyncio.run`` 取 ``_Snapshot`` + 全部断言同步」。
2. 断言消息里夹一个 GBK 不可编码字符（``⇒`` / ``⊆`` / ``−`` / emoji）会让 pytest 把
   **整条消息**转义成 ``\\uXXXX``，极易误判成编码配置问题。
   ⇒ 消息体只用 ASCII 符号 + 中文汉字。
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
_PREFILL_ENGINE = _BACKEND / "app" / "services" / "prefill_engine.py"
#: 锚点映射真源（取值层 SQL 与待对齐上限都在这里，Property 11/13 判据来源）
_ANCHOR_MAP_PY = _BACKEND / "app" / "services" / "prefill_anchor_map.py"

#: 预设真源（Task 4 交叉锁死 probe 实参用）
#: 🔴 路径是 `backend/data/` 不是 `backend/data/ledger_adapters/`（memory 已登记）
_PREFILL_MAPPING = _BACKEND / "data" / "prefill_formula_mapping.json"


def _iter_preset_formula_calls(fn: str) -> set[tuple[str, str, str]]:
    """从预设 JSON 抽出某函数的全部 `(arg1, arg2, arg3)` 三元组。

    🔴 **实参里可能含半角括号**（`PREV('D2','附注披露信息(上市公司)','上年账面价值')`）
    ⇒ 禁用 ``\\(([^)]*)\\)`` 抽实参列表，那会在第一个 ``)`` 处截断、把 3 参读成 2 参
    并让该条静默丢失（本轮探针首版即因此少数 15 条）。
    改为**逐字符扫引号内实参**，只在引号外遇到 ``)`` 才收尾。
    """
    import json

    doc = json.loads(_PREFILL_MAPPING.read_text(encoding="utf-8"))
    out: set[tuple[str, str, str]] = set()
    needle = f"{fn}("
    for block in doc.get("mappings") or []:
        for cell in block.get("cells") or []:
            expr = str(cell.get("formula") or "")
            idx = 0
            while True:
                pos = expr.find(needle, idx)
                if pos < 0:
                    break
                # 排除 TB_SUM( 被 SUM( 命中一类前缀误配
                before = expr[pos - 1] if pos > 0 else "="
                idx = pos + len(needle)
                if before.isalnum() or before == "_":
                    continue
                args: list[str] = []
                i = idx
                while i < len(expr):
                    ch = expr[i]
                    if ch == "'":
                        j = expr.find("'", i + 1)
                        if j < 0:
                            break
                        args.append(expr[i + 1 : j])
                        i = j + 1
                        continue
                    if ch == ")":
                        break
                    i += 1
                if len(args) >= 3:
                    out.add((args[0], args[1], args[2]))
    return out

#: 被本 spec 修复的两个 resolver
_TARGET_RESOLVERS = ("_resolve_wp_formula", "_resolve_prev_formula")

#: 其余 8 个 resolver —— 零回归对照（Task 12 会做逐字比对，此处只做存在性锚点）
_UNTOUCHED_RESOLVERS = (
    "_resolve_ledger_formula",
    "_resolve_aux_formula",
    "_resolve_adj_formula",
    "_resolve_note_formula",
    "_resolve_ledger_detail_formula",
    "_resolve_count_ledger_formula",
)

#: 预设数据文件（probe 实参的真源，Task 4 从这里实时解析校验）
_PREFILL_MAPPING = _BACKEND / "data" / "prefill_formula_mapping.json"

#: characterization 直跑实参 —— **必须是 `prefill_formula_mapping.json` 里真实存在的
#: `WP()` / `PREV()` 三元组**（Task 4）。
#:
#: 🔴 交付时这 6 条实参**全部不是真实预设**（`期末未审余额` / `原值期末未审数` /
#: `减值准备期末未审数` / `明细表期末未审数` 在两个口径下都不存在）。根因是立项文档把
#: **宿主自己的 `cells[].cell_ref`**（值往哪写）与 **`WP()` 第三参**（从哪读）混成
#: 一张表。后果：Task 13 反转 characterization 时**分不清「接线没生效」与「实参不存在」**。
#: ⇒ 换成 design.md 表格里的真实三元组，并由
#: :meth:`TestProbeArgsAreRealPresets` 从 JSON 实时校验（预设变动后自动打红）。
_WP_PROBES: tuple[tuple[str, str, str], ...] = (
    ("D2", "明细表D2-2", "期末合计"),
    ("D1", "坏账准备明细表D1-4", "按票据种类小计-期末未审数"),
    ("D4", "主营业务收入明细表D4-2", "全年收入合计"),
    ("D7", "明细表D7-2", "期末合计"),
    # 已知进待对齐清单（派生列）—— Task 13 反转后它必须**仍是 None**，
    # 与上面 4 条形成「已对齐 / 未对齐」双向对照。
    ("D1", "原值明细表（按类别）D1-2", "合计-期末未审数"),
)
_PREV_PROBES: tuple[tuple[str, str, str], ...] = (
    ("D2", "审定表D2-1", "审定数"),
    ("D4", "营业收入审定表D4-1", "审定数"),
)

#: 上面 probe 里**预期永远取不到数**的那些（派生列 / 未对齐），Task 13 反转时据此分组
_WP_PROBES_EXPECTED_NONE: frozenset[tuple[str, str, str]] = frozenset(
    {("D1", "原值明细表（按类别）D1-2", "合计-期末未审数")}
)


def _iter_preset_formula_calls(fn_name: str) -> set[tuple[str, str, str]]:
    """从 `prefill_formula_mapping.json` 实时解析 ``fn_name('a','b','c')`` 三元组。

    🔴 正则必须容忍**半角括号**出现在实参里（`附注披露信息(上市公司)`）——
    按 ``\\(([^)]*)\\)`` 抽会在第一个 ``)`` 处截断，实测会把
    ``PREV('D2','附注披露信息(上市公司)','上年账面价值')`` 抽成 2 个实参
    （本轮探针首版即因此少数 15 条、错判 D 循环分布）。
    ⇒ 改为逐字符扫描 + 引号内配对。
    """
    import json

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
                idx = i + len(needle)
                args: list[str] = []
                cur = ""
                in_q = False
                j = idx
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


# ─────────────────────────── 源码抽取（Task 3 基础设施）───────────────────────────


def strip_comments(src: str) -> str:
    """剥掉 Python 注释与三引号字符串（docstring）。

    🔴 **必须先剥再判** —— 修复说明的 docstring 与注释里会**如实写出**被禁的 ``cells``
    字样（「改造前读 ``parsed_data['cells']``」），不剥就会把说明文字数成真实读取而误报。

    保留代码里的单/双引号短字符串（``"cells"`` 这种真实读取形态正是要抓的目标）。
    """
    # 先剥三引号块（docstring / 多行说明），非贪婪
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    # 再剥行注释（不跨行，避免吞掉后续代码）
    out_lines: list[str] = []
    for line in src.splitlines():
        # 朴素处理：# 之前若有奇数个引号说明在字符串内，此处代码库无该形态，保守只剥行首/代码后注释
        idx = line.find("#")
        if idx >= 0:
            before = line[:idx]
            if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                line = before
        out_lines.append(line)
    return "\n".join(out_lines)


def extract_func_body(src: str, name: str) -> str:
    """按**缩进**截取 Python 函数体（``async def`` / ``def`` 均认）。

    🔴 缩进正则写 ``[ \\t]*`` 不写 ``\\s*`` —— ``re.M`` 下 ``\\s`` **含换行**，
    ``^(\\s*)def foo`` 会从前面的空行开始匹配，``indent`` 被算成一串换行的长度，
    函数体截成空串（memory 已登记的空转形态）。
    """
    pat = re.compile(rf"^([ \t]*)(?:async[ \t]+)?def[ \t]+{re.escape(name)}[ \t]*\(", re.M)
    m = pat.search(src)
    if m is None:
        return ""
    indent = len(m.group(1))

    # 🔴 必须先用**圆括号配对**跳过参数列表再按缩进截取（memory 已登记的坑）。
    # 本仓库的 resolver 签名是跨行的：
    #
    #     async def _resolve_wp_formula(
    #         db: AsyncSession, project_id: UUID, year: int, args: list[str]
    #     ) -> Decimal | None:
    #
    # 收尾行 `) -> Decimal | None:` 缩进为 0，若直接按「缩进 <= indent 即结束」扫，
    # 会在第 2 行后立刻 break → 只截到签名两行，后续断言全在签名文本上求值
    # （表现为「函数体只有 2 行」或断言静默通过）。
    depth = 0
    sig_end = -1
    for i in range(m.end() - 1, len(src)):
        ch = src[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                # 参数列表闭合，再往后找该行的 `:`（跳过返回类型注解）
                colon = src.find(":", i)
                nl = src.find("\n", i)
                sig_end = (colon if 0 <= colon < nl else nl) if nl != -1 else len(src)
                break
    if sig_end < 0:
        return ""

    lines = src[sig_end:].splitlines()
    body: list[str] = []
    for line in lines[1:]:
        if not line.strip():
            body.append(line)
            continue
        cur = len(line) - len(line.lstrip())
        if cur <= indent:
            break
        body.append(line)
    return "\n".join(body)


# ─────────────────────────── 连库快照（Task 1 / Task 2）───────────────────────────


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
    prev_results: dict[tuple[str, str, str], object] = field(default_factory=dict)
    short_arg_results: dict[str, object] = field(default_factory=dict)
    #: Property 17：取值层 SQL 的列名是否真能在库上执行
    schema_probe_ok: bool = False
    schema_probe_error: str = ""
    #: 反向自检：故意写错列名的同形查询必须失败
    schema_probe_negative_failed: bool = False
    #: `ANCHOR_MAP` 每条真跑一次的结果（`hit=金额` / 其余六态 / `EXC:...`）
    anchor_exec_results: dict[str, str] = field(default_factory=dict)
    error: str | None = None


async def _load_snapshot() -> _Snapshot:
    """取齐全部连库判据。

    🔴 **必须用独立引擎，不能借 `app.core.database.async_session`**（2026-08-07 实测）。

    本函数在 **import 期**由 `asyncio.run()` 调用，而 `asyncio.run` 结束时会
    **关闭它自己创建的事件循环**。若期间从共享 `async_session` 借出连接，
    这些连接会留在共享池里且绑定在那个**已关闭**的 loop 上 ⇒ 同一 pytest 进程内
    后续任何连库测试拿到它就抛 `RuntimeError: Event loop is closed`
    /`AttributeError: 'NoneType' object has no attribute 'send'`。

    实测后果：本文件单独跑 70 passed，但与 `formula_runtime/integration/**` 同批跑时
    双向污染（本文件 21 个测试全 ERROR，对方 3 errors）。而**广域 CI 正是同批跑的**
    —— 即「单独绿、进 CI 红」，与本 spec 要修的「四层验证全绿而链路是死的」同族。

    正解：自建 `NullPool` 引擎（不复用连接）+ 在**同一个 loop 内** `dispose()`，
    共享池完全不参与，故对其余测试零影响。
    """
    snap = _Snapshot()
    engine = None
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
        from app.services.prefill_engine import (
            _resolve_prev_formula,
            _resolve_wp_formula,
        )

        engine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,  # 不留连接在池里，dispose 后无残留
            echo=False,
        )
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as db:
            row = (
                await db.execute(
                    sa.text(
                        """
                        SELECT count(*) AS total,
                               count(*) FILTER (WHERE parsed_data ? 'cells')     AS cells,
                               count(*) FILTER (WHERE parsed_data ? 'html_data') AS html,
                               count(*) FILTER (WHERE parsed_data ? 'wp_code')   AS wpc
                        FROM working_paper
                        WHERE is_deleted = false
                          AND parsed_data IS NOT NULL
                          AND parsed_data::text <> '{}'
                        """
                    )
                )
            ).first()
            snap.total_parsed = int(row[0] or 0)
            snap.cells_count = int(row[1] or 0)
            snap.html_count = int(row[2] or 0)
            snap.wp_code_count = int(row[3] or 0)

            # 选一个 D 循环底稿最多的项目做 characterization 直跑
            prow = (
                await db.execute(
                    sa.text(
                        """
                        SELECT wp.project_id::text, count(*) AS n
                        FROM working_paper wp
                        JOIN wp_index wi ON wi.id = wp.wp_index_id
                        WHERE wp.is_deleted = false AND wi.wp_code LIKE 'D%'
                        GROUP BY wp.project_id
                        ORDER BY n DESC
                        LIMIT 1
                        """
                    )
                )
            ).first()
            if prow is not None:
                snap.probe_project_id = prow[0]
                snap.d_wp_count = int(prow[1] or 0)
                yrow = (
                    await db.execute(
                        sa.text(
                            "SELECT COALESCE(audit_year, 2025) FROM projects "
                            "WHERE id = CAST(:pid AS uuid)"
                        ),
                        {"pid": snap.probe_project_id},
                    )
                ).first()
                snap.probe_year = int(yrow[0]) if yrow else 2025

                pid = UUID(snap.probe_project_id)
                for args in _WP_PROBES:
                    snap.wp_results[args] = await _resolve_wp_formula(
                        db, pid, snap.probe_year, list(args)
                    )
                for args in _PREV_PROBES:
                    snap.prev_results[args] = await _resolve_prev_formula(
                        db, pid, snap.probe_year, list(args)
                    )
                snap.short_arg_results["WP"] = await _resolve_wp_formula(
                    db, pid, snap.probe_year, ["D1", "审定表D1-1"]
                )
                snap.short_arg_results["PREV"] = await _resolve_prev_formula(
                    db, pid, snap.probe_year, ["D1", "审定表D1-1"]
                )

                # ── Property 17：取值层每条映射真跑一次（抓 SQL 列名/类型错） ──
                # 🔴 这里**不能**用 try/except 把异常吞掉当「无数据」——
                # 那正是本轮 P0（`checklist_responses.workpaper_id` 不存在）能潜伏的机理。
                # 异常一律记成 `EXC:...` 让断言打红。
                from app.services.prefill_anchor_map import (
                    ANCHOR_MAP,
                    read_anchor_value,
                )

                for key, spec in ANCHOR_MAP.items():
                    label = "|".join(key)
                    try:
                        res = await read_anchor_value(db, pid, key[0], spec)
                        snap.anchor_exec_results[label] = (
                            f"{res.status.value}:{res.value}"
                            if res.value is not None
                            else res.status.value
                        )
                    except Exception as exc:  # noqa: BLE001
                        await db.rollback()
                        snap.anchor_exec_results[label] = f"EXC:{type(exc).__name__}: {exc}"

                # ── Property 17 反向自检：故意写错列名的同形查询必须失败 ──
                # 缺了这条，一旦上面的执行探针因某种原因不再真发 SQL，
                # 「全部通过」会变成空转（本轮 P0 就是四层验证全绿）。
                try:
                    await db.execute(
                        sa.text(
                            "SELECT remark FROM checklist_responses "
                            "WHERE workpaper_id = CAST(:x AS uuid) LIMIT 1"
                        ),
                        {"x": str(pid)},
                    )
                except Exception:  # noqa: BLE001
                    snap.schema_probe_negative_failed = True
                    await db.rollback()

                # ── Property 17 正向锚点：正确列名必须可执行 ──
                try:
                    await db.execute(
                        sa.text(
                            "SELECT remark FROM checklist_responses "
                            "WHERE wp_id = CAST(:x AS uuid) AND item_id = :i LIMIT 1"
                        ),
                        {"x": str(pid), "i": "probe"},
                    )
                    snap.schema_probe_ok = True
                except Exception as exc:  # noqa: BLE001
                    snap.schema_probe_error = f"{type(exc).__name__}: {exc}"
                    await db.rollback()
    except Exception as exc:  # noqa: BLE001
        snap.error = f"{type(exc).__name__}: {exc}"
    finally:
        # 🔴 必须在**同一个 loop 内**释放 —— 出了 asyncio.run 这个 loop 就关了，
        # 届时再 dispose 会抛 `Event loop is closed`（本轮实测的污染形态）。
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
        pytest.fail(
            "连库快照加载失败，本文件的连库判据全部未执行（禁止静默 skip）：\n"
            f"  {_SNAP.error}"
        )
    return _SNAP


# ═════════════════════════ Task 1：cells 全库零命中实证 ═════════════════════════


class TestCellsKeyAbsent:
    """Property 6 —— `parsed_data.cells` 是两个 resolver 的唯一数据源，实测零命中。"""

    def test_scan_surface_is_not_empty(self, snap: _Snapshot) -> None:
        """反向锚点：证明扫描面非空（不是查了个空表导致 cells=0 恒成立）。"""
        assert snap.total_parsed > 0, (
            "working_paper 中未删且 parsed_data 非空的行数为 0，"
            "此时「cells 零命中」这条断言是空转的，不能作为实证。"
        )
        assert snap.html_count > 0, (
            f"parsed_data ? 'html_data' 计数为 0（total={snap.total_parsed}），"
            "正向锚点不成立：说明查询条件或列名有误，而不是 cells 真的不存在。"
        )
        assert snap.wp_code_count > 0, (
            f"parsed_data ? 'wp_code' 计数为 0（total={snap.total_parsed}），"
            "正向锚点不成立。该键是 resolver 匹配底稿的条件 1，必须确认它确实存在。"
        )

    def test_cells_key_never_produced(self, snap: _Snapshot) -> None:
        """核心实证：`cells` 键在任何写入路径下都不产生。"""
        assert snap.cells_count == 0, (
            f"parsed_data ? 'cells' 计数为 {snap.cells_count}（预期 0）。\n"
            "若该键开始出现，说明平台新增了写入路径 —— 本 spec 的根因判据需重新评估，"
            "不要直接放宽本断言。"
        )

    def test_cells_far_rarer_than_html_data(self, snap: _Snapshot) -> None:
        """辅助判据：真实落点是 html_data / checklist_responses，不是 cells。"""
        assert snap.cells_count < snap.html_count, (
            f"cells={snap.cells_count} 未少于 html_data={snap.html_count}，"
            "与「真实录入值不落在 cells」这一结论矛盾。"
        )


# ═════════════════ Task 2：characterization（修复前恒返 None）═════════════════


class TestProbeArgsAreRealPresets:
    """Task 4 —— probe 实参必须是真实预设，不能是幻想锚点。

    交付时 6 条实参全部不存在（见 `_WP_PROBES` 的注释）。本类从
    `prefill_formula_mapping.json` **实时解析**，故将来预设改动后 probe 变成幻想实参
    会自动打红，而不是等到 Task 13 反转时才发现分不清病因。
    """

    def test_mapping_file_exists_and_parses(self) -> None:
        assert _PREFILL_MAPPING.exists(), f"预设文件不存在：{_PREFILL_MAPPING}"
        wp = _iter_preset_formula_calls("WP")
        prev = _iter_preset_formula_calls("PREV")
        # 反向锚点：解析结果非空，否则下面的「⊆」断言恒成立 = 空转
        assert len(wp) >= 50, f"WP 三元组只解析出 {len(wp)} 条，正则疑似失效"
        assert len(prev) >= 50, f"PREV 三元组只解析出 {len(prev)} 条，正则疑似失效"

    def test_wp_probes_are_real_presets(self) -> None:
        real = _iter_preset_formula_calls("WP")
        bogus = [p for p in _WP_PROBES if p not in real]
        assert not bogus, (
            f"以下 WP probe 实参在 prefill_formula_mapping.json 里不存在：{bogus}\n"
            "用不存在的实参做 characterization 会让 Task 13 反转时"
            "分不清「接线没生效」与「实参本身不存在」。"
        )

    def test_prev_probes_are_real_presets(self) -> None:
        real = _iter_preset_formula_calls("PREV")
        bogus = [p for p in _PREV_PROBES if p not in real]
        assert not bogus, f"以下 PREV probe 实参不存在于预设文件：{bogus}"

    def test_paren_tolerant_parsing_selfcheck(self) -> None:
        """反向自检：实参里带半角括号的预设必须被完整解析成 3 参。

        `PREV('D2','附注披露信息(上市公司)','上年账面价值')` 这类实参用
        `\\(([^)]*)\\)` 抽会截断成 2 参 → 该条静默丢失。本轮探针首版即因此
        少数 15 条并错判 D 循环分布，故必须钉住。
        """
        prev = _iter_preset_formula_calls("PREV")
        with_paren = [t for t in prev if "(" in t[1]]
        assert with_paren, (
            "预设里找不到「sheet 名含半角括号」的 PREV 条目，"
            "本自检已空转（该形态实测存在，如 D2/D3/D7 的披露 sheet）。"
        )
        for t in with_paren:
            assert t[2], f"三元组 {t} 的第三参为空，说明解析在括号处截断了"


class TestResolverCharacterizationBeforeFix:
    """Task 13 —— **已反转**的 characterization：链路已活，且死链不会复活。

    🔴 本类原先锁死「修复前 WP() 恒返 None」，Wave 3/4 接线交付后按 spec 要求反转。
    反转不是删断言而是**换方向**，现在它构成双向证据：

    * 已对齐锚点（``ANCHOR_MAP``）在真实库**能取到数** —— 防「additive 注入即死代码」
      （接线写了但没生效时本类打红）
    * 未对齐锚点（``UNALIGNED`` 的派生列）**仍必须是 None** —— 防有人为了「让它有值」
      在后端复刻前端派生公式（那是 R3 明令禁止的双真源）
    * ``PREV()`` 恒 None —— fail-closed 不得回退本年值（R4.2）

    真实库实测（2026-08-07，项目 ``0ec33ac9`` 重药控股安徽有限公司_2025）：

    ==================================== ==========================================
    锚点                                  实测
    ==================================== ==========================================
    ``WP('D2','明细表D2-2','期末合计')``    **624025343.06**（1260/1260 行求和）
    ``WP('D1','坏账准备明细表D1-4',…)``     0（2/2 行，两行小计均为 0）
    ``WP('D4','主营业务收入明细表D4-2',…)`` 0（7/7 行 SUM_LIST）
    ``WP('D7','明细表D7-2','期末合计')``    0.0（1/1 行）
    ``WP('D1','原值明细表（按类别）D1-2',…)`` None（UNALIGNED：派生列，预期）
    ==================================== ==========================================

    ``624025343.06`` 已用独立 SQL 交叉核对（``SUM((r->>'endBalance')::numeric)``
    得同值同行数）—— 不是拿本函数的输出证明本函数。
    """

    def test_probe_project_available(self, snap: _Snapshot) -> None:
        assert snap.probe_project_id is not None, (
            "库中找不到任何含 D 循环底稿的项目，characterization 无法执行。"
        )
        assert snap.d_wp_count > 0

    def test_aligned_wp_anchors_now_resolve(self, snap: _Snapshot) -> None:
        """🔴 反转后的核心断言：已对齐锚点必须真取到数。

        判据是「至少一条非 None」而非「全部非 None」—— 探针项目里部分明细表
        确实未编制（``NO_ITEM``），那是真实业务态，要求全部有值会逼人造数据。
        但**一条都没有**就说明接线没生效，那正是本 spec 要修的缺陷。
        """
        aligned = {
            k: v
            for k, v in snap.wp_results.items()
            if k not in _WP_PROBES_EXPECTED_NONE
        }
        assert aligned, "已对齐 probe 集合为空，characterization 已空转。"
        got = {k: v for k, v in aligned.items() if v is not None}
        assert got, (
            "全部已对齐锚点都返回 None —— 链路仍是死的。\n"
            f"探针项目：{snap.probe_project_id}\n"
            f"逐条结果：{aligned}\n"
            "排查顺序：① 跑 backend/scripts/diagnose/verify_prefill_wp_prev_live.py "
            "看六态分布；② 若全 NO_ITEM 则该项目明细表未编制（换项目而非改断言）；"
            "③ 若出现 ERROR 则取值层 SQL 有缺陷（本轮 P0 即 checklist_responses "
            "的列名写成了 workpaper_id，真实列名是 wp_id，被 fail-soft 吞成静默 None）。"
        )

    def test_unaligned_wp_anchors_stay_none(self, snap: _Snapshot) -> None:
        """反向断言：待对齐清单里的锚点**必须仍是 None**（R3.1 宁缺勿造）。

        这条抓的是「为了让它有值而在后端复刻前端派生公式」——
        `D1-cat-rows` 的 `currentUnadjusted`/`currentAudited` 由前端 `recalcRow()`
        加载时重算、小计是 `computed`，都不落库。后端复刻即双真源。
        """
        leaked = {
            k: v
            for k, v in snap.wp_results.items()
            if k in _WP_PROBES_EXPECTED_NONE and v is not None
        }
        assert not leaked, (
            f"待对齐锚点取到了值：{leaked}\n"
            "这些锚点的目标列是前端派生列（不落库）。若在后端复刻其公式，"
            "前端改公式后后端不会打红 = 双真源。"
            "正解见 prefill_anchor_map.OUT_OF_SCOPE_CHANGES"
            "['frontend_persist_derived_columns']。"
        )

    def test_prev_stays_none_after_fix(self, snap: _Snapshot) -> None:
        """`PREV()` fail-closed：修复前后都恒 None，且理由不同。

        修复前是「数据源零命中」的意外恒 None；修复后是**有意** fail-closed。
        一旦有人给它接上取数，取到的只能是本年值（无 year 维度）并显示在
        「上年数」列 —— 161 条 PREV 里 118 条是「上年审定数」类，属数字级错误。
        """
        bad = {k: v for k, v in snap.prev_results.items() if v is not None}
        assert not bad, (
            f"PREV() 取到了值：{bad}\n"
            "当前数据模型无 year 维度（working_paper / wp_index 都没有 year 列），"
            "任何非 None 都只能是**本年**值。跨年度取数需数据模型变更，"
            "见 prefill_anchor_map.OUT_OF_SCOPE_CHANGES['prev_year_dimension']。"
        )

    def test_short_args_return_none(self, snap: _Snapshot) -> None:
        """Requirement 1.5 / 3.2：实参不足 3 个时返 None（修复前后都必须成立）。"""
        for name, val in snap.short_arg_results.items():
            assert val is None, (
                f"{name}() 传 2 个实参时返回了 {val!r}，应为 None。"
                "该行为在修复前后都必须保持（保护既有 fail-soft 语义）。"
            )


# ═════════════════ Task 3：源码守卫（禁 cells 读法 / 预期打红）═════════════════


class TestResolverSourceGuard:
    """Property 5 —— resolver 函数体不得再读 `parsed_data['cells']`。

    🔴 **Wave 3 交付前本类预期打红**，这是 spec 要求的「先打红」。
    """

    @staticmethod
    def _src() -> str:
        return _PREFILL_ENGINE.read_text(encoding="utf-8")

    def test_extraction_is_not_vacuous(self) -> None:
        """反向自检：函数体确实截到了，且截的是对的那一段。

        缺了这条，一旦正则失效（改名 / 缩进变化）函数体变空串，
        下面的「不得含 cells」会**恒成立** = 断言空转。
        """
        src = strip_comments(self._src())

        # `_resolve_wp_formula` 是真实取值逻辑 → 必须是多行且用到 args
        wp_body = extract_func_body(src, "_resolve_wp_formula")
        assert wp_body, "未截到 _resolve_wp_formula 的函数体，源码守卫已空转（正则失效）。"
        assert len(wp_body.splitlines()) >= 5, (
            f"_resolve_wp_formula 函数体只有 {len(wp_body.splitlines())} 行，"
            "疑似截取边界错误（如命中了参数列表里的类型注解）。"
        )
        assert "args" in wp_body, (
            "_resolve_wp_formula 的函数体里没有 args，截取到的不是目标函数。"
        )

        # 🔴 `_resolve_prev_formula` 在 Wave 3 后是 **fail-closed**（Requirement 4.2）
        # ⇒ 其正确形态恰恰是「只有一个 return None」，按「≥5 行」断言会把正确实现打红。
        # 故这里改断言「确实截到了且恰好只有 return None」——
        # 一旦有人往里加取数逻辑（比如回退查本年），行数变多即被 Property 9 抓住。
        prev_body = extract_func_body(src, "_resolve_prev_formula")
        assert prev_body, "未截到 _resolve_prev_formula 的函数体，源码守卫已空转。"
        prev_stmts = [
            ln.strip()
            for ln in prev_body.splitlines()
            if ln.strip() and ln.strip() not in ('""', "''")
        ]
        assert prev_stmts == ["return None"], (
            "_resolve_prev_formula 的函数体不再是单一 `return None`，实际语句："
            f"{prev_stmts}\n"
            "该函数必须 fail-closed（数据模型无 year 维度，取本年值属数字级错误）。"
            "若确需扩展，先落实 OUT_OF_SCOPE_CHANGES['prev_year_dimension'] 的数据模型变更。"
        )

    def test_strip_comments_selfcheck(self) -> None:
        """反向自检：`strip_comments` 确实在工作，且不会把代码一起剥掉。"""
        sample = (
            'def f():\n'
            '    """docstring 提到 cells 是说明文字"""\n'
            '    # 注释里也提到 cells\n'
            '    x = data.get("cells", {})\n'
            '    return x\n'
        )
        cleaned = strip_comments(sample)
        assert "docstring" not in cleaned, "三引号块未被剥掉，说明文字会被数成真实读取。"
        assert "注释里" not in cleaned, "行注释未被剥掉。"
        assert '"cells"' in cleaned, (
            "代码里的 \"cells\" 字符串被误剥了 —— 那正是要抓的目标形态。"
        )

    def test_resolvers_do_not_read_cells(self) -> None:
        """核心断言（Wave 3 前预期红）。"""
        src = strip_comments(self._src())
        offenders: list[str] = []
        for name in _TARGET_RESOLVERS:
            body = extract_func_body(src, name)
            if re.search(r"""['"]cells['"]""", body):
                offenders.append(name)
        assert not offenders, (
            f"以下 resolver 仍在读 parsed_data['cells']：{offenders}\n"
            "该键真实库零命中（见 TestCellsKeyAbsent），读它等于恒返 None。\n"
            "【Wave 3 交付前本断言预期打红 —— 这是 spec 要求的「守卫先对当前状态打红」，"
            "不要为了让它变绿而放宽判据。】"
        )

    def test_prev_docstring_does_not_claim_year_minus_one(self) -> None:
        """Requirement 3.1：删除「同项目 year-1」失实表述（Wave 3 前预期红）。

        当前 docstring 写「从上年底稿取值」，而查询里没有任何 year 条件，
        且 working_paper / wp_index 都没有 year 列 —— 该表述会误导后来者以为跨年度可用。
        """
        src = self._src()
        body = extract_func_body(src, "_resolve_prev_formula")
        assert body, "未截到 _resolve_prev_formula，断言空转。"

        # 🔴 判据不能是「docstring 里不许出现 year-1」——
        # 修复后的 docstring **必须**如实说明「改造前声称 year-1 而查询里没有 year 条件」，
        # 裸子串判据会把正确实现打红（memory 已登记的「裸子串被合法写法命中」同族）。
        # 正确判据 = **行为层**：函数体不得有任何 DB 查询，且必须显式说明无 year 维度。
        for forbidden in ("WorkingPaper", "db.execute", "sa.select"):
            assert forbidden not in body, (
                f"_resolve_prev_formula 出现了 {forbidden} —— 它必须 fail-closed，"
                "不得查任何底稿（查了就只能查到本年，属数字级错误）。"
            )
        assert "无 year 维度" in body or "没有 year 列" in body, (
            "_resolve_prev_formula 的 docstring 必须如实说明「数据模型无 year 维度」"
            "（Requirement 4.1），否则后来者会以为跨年度可用。"
        )
        # 反向自检：确认它确实**提到过**旧表述（作为「已纠正」的证据），
        # 而不是把整段说明删光了 —— 删光同样会让后来者重犯。
        assert "改造前" in body, (
            "_resolve_prev_formula 的 docstring 应保留「改造前如何错」的说明，"
            "否则下个会话看不到这条缺陷的历史而可能改回去。"
        )

    def test_untouched_resolvers_still_present(self) -> None:
        """零回归锚点：其余 resolver 必须仍在（防重构时被顺手删掉）。"""
        src = self._src()
        missing = [n for n in _UNTOUCHED_RESOLVERS if not extract_func_body(src, n)]
        assert not missing, f"以下 resolver 不见了：{missing}"

    def test_note_resolver_is_the_correct_paradigm(self) -> None:
        """正向锚点：`_resolve_note_formula` 是「JSON 内寻址」的既有正确范式。

        它按 `key`/`label` 匹配行 + 按列键取值且**不碰 cells** —— Task 5 的两态取值
        纯函数照它实现。这条断言把该范式钉死，防它哪天也被改成读 cells。
        """
        src = strip_comments(self._src())
        body = extract_func_body(src, "_resolve_note_formula")
        assert body, "未截到 _resolve_note_formula。"
        assert not re.search(r"""['"]cells['"]""", body), (
            "_resolve_note_formula 开始读 cells 了 —— 它本是正确范式，不应退化。"
        )
        for marker in ('"key"', '"label"', '"rows"'):
            assert marker in body, (
                f"_resolve_note_formula 里找不到 {marker}，"
                "其「按行标识匹配 + 按列键取值」的范式可能已被改写，"
                "Task 5 的实现依据需重新确认。"
            )

# ═════════════ Task 14 追加：SQL 列名 schema 契约（本轮 P0 的防线）═════════════
#
# 🔴 本轮实测抓到一个 P0：`read_anchor_value` 的第二条 SQL 写
# `WHERE workpaper_id = ...`，而 `checklist_responses` 的真实列名是 **`wp_id`**
# （无 `workpaper_id` 列）⇒ 每次取值都抛 `UndefinedColumnError`，被
# `_resolve_wp_formula` 的 `except Exception` 吞成 WARNING ⇒ 8 条已对齐锚点**全部**
# 仍返 None，而：
#
#   * 源码守卫（Property 2/4/5/11/12）全绿  —— 它们只查「不许出现 cells」「有没有 ORDER BY」
#   * 44 个纯函数单测全绿                    —— `parse_anchor_value` 零 DB 依赖
#   * characterization「恒返 None」全绿      —— 恰好与「修好了」不可区分
#
# ⇒ 「三层验证全绿 + fail-soft 吞异常」正是本 spec 要修的那个缺陷模式本身。
# 防线只能是**真实执行**：连库跑一次 `read_anchor_value`，任何异常/`ERROR` 态即打红。


class TestAnchorSqlSchemaContract:
    """Property 17（本轮新增）—— 取值层的 SQL 必须真能在真实 schema 上执行。

    判据是**行为层**（真跑 SQL）而非源码层：列名写错、表名写错、类型不匹配
    都会在这里以异常形态暴露，而源码扫描无论怎么写都抓不到「这个列名在库里不存在」。
    """

    def test_referenced_columns_exist(self, snap: _Snapshot) -> None:
        """取值层 SQL 引用的列必须在真实 schema 里存在。

        反向自检：`_probe_missing_column` 是**故意写错列名**的同形查询，
        它必须失败 —— 否则说明本测试的探测手段本身失效（如库里恰好两个列都有）。
        """
        assert snap.schema_probe_ok, (
            "取值层 SQL 引用了真实 schema 里不存在的列：\n"
            f"  {snap.schema_probe_error}\n"
            "🔴 这类错误会被 _resolve_wp_formula 的 except Exception 吞成 WARNING，"
            "源码守卫与纯函数单测都抓不到 —— 必须靠真跑 SQL 的本断言兜住。"
        )
        assert snap.schema_probe_negative_failed, (
            "反向自检失败：故意写错列名的探测查询**没有**报错，"
            "说明本测试的探测手段已失效（正向断言随之变成空转）。"
        )

    def test_read_anchor_value_executes_without_exception(self, snap: _Snapshot) -> None:
        """对 `ANCHOR_MAP` 每条真跑一次取值，不得抛异常。

        允许的结果是**六态中的任意一态**（`NO_ITEM` / `EMPTY` 等都是正常业务态），
        不允许的是「抛异常」—— 那是接线错误，会被上层 fail-soft 伪装成「本项目无此数据」。
        """
        assert snap.anchor_exec_results, (
            "一条 ANCHOR_MAP 取值都没跑到，本断言空转。"
            f"（ANCHOR_MAP 条目数应 > 0，快照错误：{snap.error}）"
        )
        crashed = {k: v for k, v in snap.anchor_exec_results.items() if v.startswith("EXC:")}
        assert not crashed, (
            "以下锚点的取值层抛异常（接线错误，不是业务态）：\n"
            + "\n".join(f"  {k} -> {v}" for k, v in sorted(crashed.items()))
        )

    def test_at_least_one_anchor_hits_in_real_db(self, snap: _Snapshot) -> None:
        """Requirement 7.1 的验收锚点：真实库里至少有一条锚点**真取到数**。

        这是「链路是否真的通了」的唯一硬判据 —— `--check` 归零 / 单测全绿 /
        六态里全是 `NO_ITEM` 都可能是链路仍死。若真实库确实一条都没编制，
        本断言会打红并要求人工确认，而不是让「全 NO_ITEM」静默冒充成功。
        """
        hits = {k: v for k, v in snap.anchor_exec_results.items() if v.startswith("hit")}
        assert hits, (
            "真实库里没有任何一条已对齐锚点取到数，六态分布：\n"
            + "\n".join(f"  {k} -> {v}" for k, v in sorted(snap.anchor_exec_results.items()))
            + "\n若确认是「底稿未编制」而非链路问题，请在 spec Notes 记录并说明"
            "验收改用哪条证据（禁构造 fixture 冒充）。"
        )


# ═══════════ Task 15 补强：变异检验暴露的四个守卫缺口 ═══════════
#
# 首轮变异检验 9 条里有 4 条 GREEN（= 守卫缺陷，不是「代码没问题」）。逐条成因：
#
#   * M4 去掉 `ORDER BY`      —— 全库无「同 wp_code 多份底稿」的项目，行为层测不出，
#                                 只能源码级断言（Property 11 的后半句一直没落地）
#   * M8 去掉 `logger.warning`—— 没有任何断言查过它（Property 12 只写在 design 里）
#   * M9 放宽 `UNALIGNED_MAX` —— 既有断言是 `len(UNALIGNED) <= UNALIGNED_MAX`，
#                                 把上限改大它当然仍绿；缺的是「上限本身不许被抬高」
#   * M7 映射到 `priorAudited`—— **这条是变异无效不是守卫缺陷**：`useD2Detail` 是
#                                 整行 stringify 形态，`priorAudited` 确实落库
#                                 ⇒ 变异改到 `useD1BadDebt`（真白名单序列化）才有效
#
# memory 已登记：变异**没打红**要先分清「守卫缺陷」与「无效变异」，别急着改实现。


class TestDeterministicOrderingAndLogging:
    """Property 11 后半句 + Property 12 —— 源码级钉死（行为层测不出）。

    为什么必须源码级：真实库里没有「同一 project 同一 wp_code 有多份 working_paper」
    的样本，去掉 `ORDER BY` 后每次仍只有一行可选 ⇒ 行为完全不变。
    但一旦将来出现多份记录，无序查询会让**同一实参两次求值得到不同金额**，
    那是审计场景不可接受的不可复算。
    """

    @staticmethod
    def _code_body(func_name: str) -> str:
        """取某函数的**代码体**：剥 docstring 与 `#` 注释，但**保留其余三引号串**。

        🔴 这里不能用本文件的 `strip_comments()` —— 它剥掉**全部**三引号块，
        而取值层的 SQL 正是写在 `sa.text(\"\"\"...\"\"\")` 里 ⇒ 剥完 SQL 变空串，
        「必须有 ORDER BY」之类断言会在**正确实现上打红**（首版即如此）。

        反过来也不能直接用原文：`read_anchor_value` 的 docstring 里如实写了
        「按 ``updated_at DESC, id ASC`` 确定性选取」，裸原文判据会让
        「SQL 里删掉 ORDER BY 但 docstring 还留着」这个变异静默通过（M4 的形态）。

        ⇒ 用 AST 精确定位 docstring 行并置空，其余原样保留。
        """
        import ast

        src = _ANCHOR_MAP_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)
        lines = src.splitlines()
        target: ast.AST | None = None
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == func_name
            ):
                target = node
                break
        if target is None:
            return ""
        blank: set[int] = set()
        doc = target.body[0] if target.body else None
        if (
            isinstance(doc, ast.Expr)
            and isinstance(doc.value, ast.Constant)
            and isinstance(doc.value.value, str)
        ):
            blank |= set(range(doc.lineno, (doc.end_lineno or doc.lineno) + 1))
        out: list[str] = []
        for ln in range(target.body[0].lineno, (target.end_lineno or 0) + 1):
            if ln in blank:
                continue
            text = lines[ln - 1]
            if text.strip().startswith("#"):
                continue
            out.append(text)
        return "\n".join(out)

    def test_extraction_is_not_vacuous(self) -> None:
        """反向自检：确实截到了 `read_anchor_value` 的函数体。

        🔴 这里**不能**用 `strip_comments()` + 正则截体 —— 取值层的 SQL 写在
        三引号字符串里，`strip_comments` 会把它当 docstring 一起剥掉，于是
        「有没有 ORDER BY」的断言永远查不到目标文本（首版即因此假红）。
        故改用 AST：只剥函数自己的 docstring，保留其余字符串字面量。
        """
        body = self._code_body("read_anchor_value")
        assert body, "未截到 read_anchor_value，本类断言已空转。"
        assert "checklist_responses" in body, (
            "截到的不是目标函数（函数体里没有 checklist_responses）。"
        )
        # 反向自检：AST 剥法必须**保留** SQL 字符串（这正是它优于 strip_comments 的点）
        assert "SELECT" in body, (
            "函数体里没有 SELECT —— SQL 字符串被误剥了，"
            "本类的 ORDER BY / 列名断言会全部空转。"
        )

    def test_workpaper_lookup_is_deterministic(self) -> None:
        """底稿定位必须带确定性 ORDER BY（Property 11）。"""
        body = self._code_body("read_anchor_value")
        assert re.search(r"ORDER\s+BY\s+wp\.updated_at\s+DESC", body), (
            "read_anchor_value 的底稿定位查询缺少 `ORDER BY wp.updated_at DESC`。\n"
            "同一 wp_code 在项目下有多份记录时，无序查询依赖数据库返回顺序 ==> "
            "同一条公式两次求值可能得到不同金额（审计场景不可复算）。\n"
            "真实库当前无多份样本故行为层测不出，只能在源码层钉死。"
        )
        assert re.search(r"ORDER\s+BY[^\n]*wp\.id\s+ASC", body), (
            "缺少 `wp.id ASC` 兜底 —— `updated_at` 相同时仍不确定。"
        )

    def test_unaligned_warning_is_present(self) -> None:
        """未对齐时必须留日志（Property 12）。

        memory 已登记：`except Exception` + fail-open 会把接线错误伪装成
        「本项目无此数据」。本轮的 P0（列名写错）正是这样藏了一整轮 ——
        当时若有 WARNING，第一次求值就会暴露。
        """
        engine = strip_comments(_PREFILL_ENGINE.read_text(encoding="utf-8"))
        body = extract_func_body(engine, "_resolve_wp_formula")
        assert body, "未截到 _resolve_wp_formula。"

        # 两处都要有：① 锚点未对齐 ② 取值抛异常
        warns = re.findall(r"_logger\.warning\s*\(", body)
        assert len(warns) >= 2, (
            f"_resolve_wp_formula 里只有 {len(warns)} 处 _logger.warning，应至少 2 处"
            "（锚点未对齐 + 取值异常）。静默返 None 会让接线缺陷伪装成「无数据」。"
        )
        assert "exc_info=True" in body, (
            "取值异常分支缺 `exc_info=True` —— 没有 traceback 的 WARNING "
            "定位不到是哪一层坏了（本轮 P0 的教训）。"
        )

    def test_exception_is_caught_not_propagated(self) -> None:
        """fail-soft 语义：异常必须被捕获（R1.8），但不得静默。"""
        engine = strip_comments(_PREFILL_ENGINE.read_text(encoding="utf-8"))
        body = extract_func_body(engine, "_resolve_wp_formula")
        assert "except Exception" in body, (
            "_resolve_wp_formula 缺 `except Exception` —— 取值异常会冒泡到 prefill "
            "主流程，可能让整张底稿预填失败（既有契约是 fail-soft）。"
        )


class TestUnalignedCapCannotBeRaised:
    """Property 13 —— 上限「只许下调」必须由守卫钉死。

    🔴 原实现只断言 `len(UNALIGNED) <= UNALIGNED_MAX`，把上限从 4 改成 99 仍全绿
    （变异 M9 GREEN）—— 那正是要禁的动作：「对不齐就往清单里加一条」会把待对齐
    清单变成逃逸阀，而 spec 的意图是它必须**逐轮变短**。
    """

    #: 交付时的实测值。**只许下调** —— 上调即意味着新增了对不齐的锚点。
    _CAP_CEILING = 4

    def test_cap_is_not_raised(self) -> None:
        from app.services.prefill_anchor_map import UNALIGNED, UNALIGNED_MAX

        assert UNALIGNED_MAX <= self._CAP_CEILING, (
            f"UNALIGNED_MAX 被抬到 {UNALIGNED_MAX}，交付时上限是 {self._CAP_CEILING}。\n"
            "🔴 上限只许下调：清单变长意味着「又有锚点对不齐」，"
            "而正解是去修映射或落实 OUT_OF_SCOPE_CHANGES 里登记的前端变更，"
            "不是把闸门开大。若确有正当理由放宽，必须同步下调本测试的 _CAP_CEILING "
            "并在 spec Notes 写明依据。"
        )
        # 反向锚点：清单确实非空（空清单会让上面断言变成对空集的空转）
        assert UNALIGNED, (
            "UNALIGNED 为空 —— 若确已全部对齐，应把 _CAP_CEILING 与 UNALIGNED_MAX "
            "一并降到 0，而不是留着一个永不触发的上限。"
        )
