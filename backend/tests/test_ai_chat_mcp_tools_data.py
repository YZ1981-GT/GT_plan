# Feature: dsh-agent-panel-integration — MCP 工具真实取数守卫（补 Task 25/26 责任真空）
"""MCP 7 个只读工具的**端到端数据流**守卫。

Requirements: 11.2, 11.3, 11.4, 11.5, 11.9, 2.4, 2.5, 2.6, 6.5, 6.6
Properties: 16（不伪降级）· 26（工具目录受控）· 28（跨用户/跨项目隔离）· 30（五角色脱敏一致）

## 这批守卫补的是什么

``routers/ai_chat_mcp.py`` 的 7 个 ``_tool_*`` 分发器上线时全是空占位
（``return {"items": []}`` / ``{"status": "placeholder"}``）。三层管道
（REST endpoint → ``tools/audit-data-mcp/server.py`` → ``DshEngine``）全部接通、
Phase C 207 个测试全绿 —— 因为**没有一条测试断言工具返回了真实数据**。

责任真空的成因：占位注释写"实际在 Task 26 接通"，而 Task 26 建的是**调用方**
（stdio server），范围不含平台侧取数。三个 gate 任务都没发现。

所以本文件的核心判据不是"函数存在"，而是**「给定真实底稿/试算表数据，工具返回非空
且字段结构正确」**：

======  =========================================================================
§1      非空断言 —— 真实 PG 数据 → ``items`` / ``rows`` 非空且结构符合声明
§2      禁占位断言 —— 运行时无 ``status="placeholder"``；源码级剥注释后无该字面量
§3      授权断言 —— 跨项目 / 越出 cycle scope 返回**拒绝**，不返回空数据伪装无结果
§4      脱敏断言 —— auditor(strict) 与 partner(none) 结果**不相等**
§5      错误码分离 —— ``semantic_unavailable`` / 不存在 / 无权限 各自 typed error
======  =========================================================================

## 为什么用真实 PostgreSQL

"返回非空"这条判据只有在真实 SQL 真实执行时才有意义：mock session 返回什么都是
测试自己塞的，改回 ``return {"items": []}`` 也照样能"非空"。复用
``dsh_agent_panel/_fixtures.py`` 的真实 PG + 事务整体回滚夹具（不污染 dev 库）。
唯一使用 mock 的地方是"embedding 不可用"（§5）—— 那是故障注入，不是数据来源。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa

from app.routers import ai_chat_mcp as mcp_router
from app.services.ai_chat.contracts import AccessDecision
from app.services.ai_chat.mcp_token import (
    MCP_READONLY_TOOLS,
    McpTokenPayload,
    McpTokenService,
)
from app.services.ai_chat.mcp_tools import (
    ERR_ACCESS_DENIED,
    ERR_INVALID_ARGUMENT,
    ERR_NOT_FOUND,
    ERR_SEMANTIC_UNAVAILABLE,
    MCP_TOOL_IMPLEMENTATIONS,
    McpToolError,
)
from tests.dsh_agent_panel._fixtures import (
    FIXTURE_AUDIT_YEAR,
    IN_SCOPE_CYCLE,
    IS_PG,
    OUT_OF_SCOPE_CYCLE,
    AccessFixture,
    run_with_fixture,
)

pytestmark = pytest.mark.skipif(
    not IS_PG, reason="MCP 取数守卫需真实 PostgreSQL（叶子聚合 / JSONB / 可见集 SQL）"
)


# ===========================================================================
# 种子数据（在夹具的同一可回滚事务内写入）
# ===========================================================================

#: 超 ``ExportMaskService.AMOUNT_THRESHOLD``（1000 万）的金额 —— 脱敏必须触发
BIG_AMOUNT = Decimal("88888888.88")

#: 科目族：父 1122 + 两个叶子 + 一个非叶子中间层 + 其孙叶子
SEED_ACCOUNTS: tuple[tuple[str, str, str, Decimal, Decimal], ...] = (
    # (code, name, closing_direction, opening, closing)
    ("1122", "应收账款", "debit", Decimal("10000000.00"), BIG_AMOUNT),
    ("1122.01", "应收账款-甲公司", "debit", Decimal("6000000.00"), Decimal("50000000.00")),
    ("1122.02", "应收账款-乙公司", "debit", Decimal("4000000.00"), Decimal("40000000.00")),
    ("1122.03", "应收账款-预收冲抵", "credit", Decimal("0.00"), Decimal("1111111.12")),
    ("2202", "应付账款", "credit", Decimal("2000000.00"), Decimal("3000000.00")),
)

SEED_SHEET_NAME = "审定表D2-1"


async def seed_tb_balance(fx: AccessFixture) -> None:
    """写入 ``tb_balance`` 种子（含父行 —— 叶子勾稽自检需要它）。"""
    from app.models.audit_platform_models import TbBalance

    for code, name, direction, opening, closing in SEED_ACCOUNTS:
        fx.session.add(
            TbBalance(
                project_id=fx.project_a.id,
                year=FIXTURE_AUDIT_YEAR,
                company_code="MAIN",
                account_code=code,
                account_name=name,
                level=len(code.split(".")),
                opening_balance=opening,
                closing_balance=closing,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("0.00"),
                closing_direction=direction,
                opening_direction=direction,
            )
        )
    await fx.session.flush()


async def seed_workpaper_content(fx: AccessFixture) -> None:
    """给 ``wp_d_file`` 写 ``parsed_data``（底稿内容真源，``working_paper`` 无 content 列）。"""
    fx.wp_d_file.parsed_data = {
        "html_data": {
            SEED_SHEET_NAME: {
                "cells": {
                    "B4": {"v": "应收账款审定表"},
                    "C7": {"v": float(BIG_AMOUNT), "f": "TB('1122','审定数')"},
                    "C8": {"v": 50000000.0},
                }
            }
        },
        "checklist_responses": [{"id": "1", "checked": True}],
    }
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(fx.wp_d_file, "parsed_data")
    await fx.session.flush()


# ===========================================================================
# token / host_decision 构造（与 router 同一形状）
# ===========================================================================

_token_service = McpTokenService()


def make_token(
    fx: AccessFixture,
    role: str = "manager",
    *,
    project_id: UUID | None = None,
    cycle_scope: frozenset[str] = frozenset({IN_SCOPE_CYCLE}),
    user_id: UUID | None = None,
) -> McpTokenPayload:
    """签发 scoped token payload（走真实 ``McpTokenService``，不手搓 dataclass）。"""
    actor_id = user_id if user_id is not None else fx.actor(role).id
    return _token_service.create_token(
        user_id=actor_id,
        project_id=project_id or fx.project_a.id,
        run_id=uuid4(),
        role=role,
        cycle_scope=cycle_scope,
        ttl_seconds=120,
    ).payload


def host_decision_for(token: McpTokenPayload) -> AccessDecision:
    """复用 router 的宿主决策构造（禁止在测试里另写一份形状）。"""
    return mcp_router.build_host_decision(token)


async def dispatch(
    fx: AccessFixture,
    tool_name: str,
    arguments: dict[str, Any],
    token: McpTokenPayload,
) -> dict[str, Any]:
    """走 router 的真实 ``_dispatch_tool``（不是直接调 service，保证接线被覆盖）。"""
    from app.services.ai_chat.access import ResourceAccessResolver

    resolver = ResourceAccessResolver(fx.session, responder=fx.responder)
    return await mcp_router._dispatch_tool(
        tool_name=tool_name,
        arguments=arguments,
        token_payload=token,
        host_decision=host_decision_for(token),
        resolver=resolver,
        db=fx.session,
    )


async def call_endpoint(
    fx: AccessFixture,
    tool_name: str,
    arguments: dict[str, Any],
    token: McpTokenPayload,
) -> mcp_router.McpToolCallResponse:
    """走**完整 endpoint 函数** ``mcp_tool_call``（含白名单/预算/审计/脱敏全链）。

    只绕过 FastAPI 的依赖注入（token 与 db 直接传入），业务链路一条不少 ——
    脱敏那一步（router 第 ⑥ 段）必须被真实执行，否则 §4 断言毫无意义。
    """
    req = mcp_router.McpToolCallRequest(
        tool_name=tool_name, arguments=arguments, tool_call_id=uuid4().hex
    )
    return await mcp_router.mcp_tool_call(req, token_payload=token, db=fx.session)


# ===========================================================================
# §1 非空断言 —— 真实数据必须真的出来
# ===========================================================================


class TestRealDataNonEmpty:
    """给定真实底稿/试算表数据，工具返回非空且字段结构与声明一致。

    这是防"回到空占位"的核心判据（Validates: Requirements 11.2, 11.3）。
    """

    def test_wp_list_returns_real_workpapers(self):
        """``wp_list`` 返回真实底稿条目（非空 + 字段齐全 + wp_code 来自 wp_index）。

        MUTATION ANCHOR MCP-1: ``_tool_wp_list`` 改回 ``return {"items": []}`` → 打红。
        """

        async def scenario(fx: AccessFixture, _sql):
            token = make_token(fx, "manager")
            out = await dispatch(fx, "wp_list", {"limit": 50}, token)

            assert out["items"], (
                "wp_list 返回空 —— 项目下存在底稿却取不到，取数未接通"
            )
            codes = {it["wp_code"] for it in out["items"]}
            assert fx.wp_d.wp_code in codes, (
                f"在 scope 内的底稿 {fx.wp_d.wp_code} 未出现：{sorted(codes)}"
            )
            # 字段结构与 MCP server 声明一致
            required = {
                "wp_id", "wp_code", "wp_name", "cycle",
                "status", "review_status", "updated_at",
            }
            for item in out["items"]:
                assert required <= set(item), (
                    f"wp_list 条目缺字段 {sorted(required - set(item))}"
                )
                assert item["wp_id"], "wp_id 不得为空"
            assert out["total"] == len(out["items"])

        run_with_fixture(scenario)

    def test_wp_read_returns_real_parsed_data(self):
        """``wp_read`` 返回真实 ``parsed_data`` 内容（不是空 dict / placeholder）。

        MUTATION ANCHOR MCP-2: ``_tool_wp_read`` 返回 ``{"content": {}}`` → 打红。
        """

        async def scenario(fx: AccessFixture, _sql):
            await seed_workpaper_content(fx)
            token = make_token(fx, "manager")

            summary = await dispatch(
                fx, "wp_read", {"wp_id": str(fx.wp_d_file.id)}, token
            )
            assert summary["wp_code"] == fx.wp_d.wp_code, (
                "wp_code 必须来自 wp_index JOIN（working_paper 表无此列）"
            )
            assert SEED_SHEET_NAME in summary["sheets"], (
                f"sheet 清单未含种子 sheet：{summary['sheets']}"
            )
            assert summary["content"], "不指定 sheet 时也应返回结构概要，不得为空"
            assert summary["content"]["sheet_count"] == 1

            detail = await dispatch(
                fx,
                "wp_read",
                {"wp_id": str(fx.wp_d_file.id), "sheet_name": SEED_SHEET_NAME},
                token,
            )
            cells = detail["content"]["cells"]["cells"]
            assert cells, "指定 sheet 后单元格为空 —— parsed_data 未真正读出"
            assert cells["B4"]["v"] == "应收账款审定表"
            assert cells["C7"]["f"] == "TB('1122','审定数')", (
                "公式必须原样透传（溯源能力依赖它）"
            )

        run_with_fixture(scenario)

    def test_tb_query_leaf_mode_aggregates_only_leaves(self):
        """``tb_query`` 叶子模式：只含叶子行、父行被排除、合计按方向定符号。

        种子科目族 ``1122``：父额 88,888,888.88；三个叶子
        ``.01=50,000,000`` + ``.02=40,000,000``（借） 与 ``.03=1,111,111.12``（贷）。
        方向定符号 ⇒ 50,000,000 + 40,000,000 − 1,111,111.12 = 88,888,888.88 == 父额；
        原样求和 ⇒ 91,111,111.12 ≠ 父额。所以「按 closing_direction 带符号」这条
        铁律在本用例里是**可判定的**，而不是口头声明。

        MUTATION ANCHOR MCP-3: ``_tool_tb_query`` 返回 ``{"rows": []}`` → 打红。
        """

        async def scenario(fx: AccessFixture, _sql):
            await seed_tb_balance(fx)
            token = make_token(fx, "manager")
            out = await dispatch(fx, "tb_query", {"account_code": "1122"}, token)

            assert out["mode"] == "leaf_aggregate"
            assert out["rows"], "tb_query 返回空 rows —— 试算表取数未接通"

            codes = {r["account_code"] for r in out["rows"]}
            assert codes == {"1122.01", "1122.02", "1122.03"}, (
                f"只应返回叶子科目，实际 {sorted(codes)}（父行 1122 必须被排除，"
                "否则父子双算）"
            )
            for row in out["rows"]:
                assert row["is_leaf"] is True
                assert {"opening", "closing", "debit", "credit"} <= set(row)

            totals = out["totals"]
            assert totals, "叶子聚合必须给出 totals（含约定与勾稽证据）"
            assert totals["closing"] == pytest.approx(float(BIG_AMOUNT), abs=0.01), (
                "期末合计必须按 closing_direction 带符号求和（应等于父科目额）；"
                f"实际 {totals['closing']}"
            )
            assert totals["convention"]["closing"] == "directional", (
                "本种子是「无符号绝对值 + 方向列」形态，期末必须选 directional 约定"
            )
            assert totals["matched"] is True, (
                f"叶子和与父额未勾稽：diff={totals['diff']}"
            )

        run_with_fixture(scenario)

    def test_tb_query_top_level_mode_returns_rows(self):
        """``tb_query`` 不传 account_code 时返回一级科目行（含方向列）。"""

        async def scenario(fx: AccessFixture, _sql):
            await seed_tb_balance(fx)
            token = make_token(fx, "manager")
            out = await dispatch(fx, "tb_query", {}, token)

            assert out["mode"] == "top_level"
            assert out["rows"], "top_level 模式返回空 —— get_active_filter 取数未接通"
            codes = {r["account_code"] for r in out["rows"]}
            assert codes == {"1122", "2202"}, (
                f"一级模式只应返回不含点号的一级科目，实际 {sorted(codes)}"
            )
            for row in out["rows"]:
                assert row["closing_direction"] in ("debit", "credit"), (
                    "方向列必须下发（缺它则备抵/负债科目符号无法判定）"
                )

        run_with_fixture(scenario)

    def test_note_read_returns_rows_from_table_data(self):
        """``note_read`` 返回附注行（真源 = ``table_data.rows[].label/values``）。

        MUTATION ANCHOR MCP-4: ``_tool_note_read`` 返回 ``{"content": {}}`` → 打红。
        """

        async def scenario(fx: AccessFixture, _sql):
            token = make_token(fx, "manager")
            out = await dispatch(fx, "note_read", {"note_id": str(fx.note_a.id)}, token)

            assert out["items"], "note_read 返回空 —— 附注取数未接通"
            note = out["items"][0]
            assert note["section_title"] == fx.note_a.section_title
            assert note["text_content"], "附注正文不得为空"
            assert note["rows"], (
                "附注行为空 —— rows[].label/values 是真源，不能只回 text_content"
            )
            assert note["rows"][0]["label"] == "银行存款"
            assert note["rows"][0]["values"] == ["1000.00", "900.00"]

        run_with_fixture(scenario)

    def test_review_prompt_returns_structured_fields(self):
        """``review_prompt`` 返回结构化复核提示（至少 base 级），且不含正文。"""

        async def scenario(fx: AccessFixture, _sql):
            token = make_token(fx, "manager")
            out = await dispatch(
                fx, "review_prompt", {"wp_id": str(fx.wp_d_file.id)}, token
            )

            assert out["wp_code"] == fx.wp_d.wp_code
            assert out["source_level"] in ("sheet", "subject", "base"), (
                f"source_level 非法：{out['source_level']}"
            )
            assert isinstance(out["checklist"], list)
            assert isinstance(out["risk_areas"], list)
            assert out["tips"] or out["checklist"], (
                "三级降级至少应给出 base 模板的 tips/checklist"
            )
            # Req 9.2：不下发提示词正文
            assert "content" not in out and "prompt_content" not in out, (
                "review_prompt 不得返回提示词正文（Req 9.2）"
            )

        run_with_fixture(scenario)


# ===========================================================================
# §2 禁占位断言 —— 运行时 + 源码级（含反向自检）
# ===========================================================================

_ROUTER_PATH = Path(mcp_router.__file__).resolve()
_TOOL_FUNC_RE = re.compile(r"^async def (_tool_\w+)\(", re.MULTILINE)


def _docstring_spans(source: str) -> set[tuple[int, int]]:
    """所有 docstring 的 ``(lineno, col_offset)`` 起点集合。

    只认**语句位置的首个裸字符串**（Module / ClassDef / FunctionDef /
    AsyncFunctionDef 的第一条语句），不误伤普通字符串字面量。
    """
    import ast

    spans: set[tuple[int, int]] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover
        return spans
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
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
            spans.add((first.value.lineno, first.value.col_offset))
    return spans


def strip_comments_and_docstrings(source: str) -> str:
    """只剥**注释与 docstring**，保留其余字符串字面量。

    🔴 两个方向都要防：

    1. 不剥 → 生产代码/守卫自身的注释里如实提到 ``placeholder``（解释历史事故），
       ``"placeholder" in source`` 会永久假红；
    2. 把**所有**字符串都剥掉 → ``return {"status": "placeholder"}`` 里的字面量
       也消失，守卫再也抓不到真正的占位实现（本函数第一版就是这么写的，
       被反向自检 ``test_placeholder_detector_is_not_vacuous`` 当场打红）。

    所以用 ``tokenize``（不是正则 —— 三引号/转义/嵌套引号必出错）丢弃 COMMENT，
    再用 ``ast`` 定位 docstring 起点精确丢弃这几个 STRING token。
    """
    import io
    import tokenize

    doc_starts = _docstring_spans(source)
    out: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == tokenize.STRING and tok.start in doc_starts:
                out.append('""')
                continue
            out.append(tok.string)
    except tokenize.TokenError:  # pragma: no cover — 生产源码不应有未闭合 token
        return source
    return " ".join(out)


def extract_function_bodies(source: str, names: list[str]) -> dict[str, str]:
    """按 AST 精确截取函数体源码（不用固定字符窗口，不靠花括号猜边界）。"""
    import ast

    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    wanted = set(names)
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node.name not in wanted:
            continue
        start = node.lineno - 1
        end = node.end_lineno or node.lineno
        out[node.name] = "".join(lines[start:end])
    return out


class TestNoPlaceholderRemains:
    """空占位彻底消失：运行时无 ``status="placeholder"``，源码内无该字面量。

    **Validates: Requirements 11.2, 11.3**
    """

    def test_dispatcher_set_equals_readonly_tools(self):
        """7 个工具全部有真实实现，且集合与 ``MCP_READONLY_TOOLS`` 等势（Property 26）。

        MUTATION ANCHOR MCP-5: 删掉任一实现 → 打红。
        """
        assert set(MCP_TOOL_IMPLEMENTATIONS) == set(MCP_READONLY_TOOLS), (
            "工具实现集合与只读白名单不等势："
            f"多={sorted(set(MCP_TOOL_IMPLEMENTATIONS) - set(MCP_READONLY_TOOLS))} "
            f"缺={sorted(set(MCP_READONLY_TOOLS) - set(MCP_TOOL_IMPLEMENTATIONS))}"
        )
        for name, impl in MCP_TOOL_IMPLEMENTATIONS.items():
            assert asyncio.iscoroutinefunction(impl), f"{name} 实现不是协程函数"

    def test_tool_dispatchers_contain_no_placeholder_literal(self):
        """源码级：``ai_chat_mcp.py`` 的 ``_tool_*`` 函数体内无 ``placeholder`` 字面量。

        先 ``strip_comments_and_docstrings`` 再查 —— 注释里如实记录历史事故是允许的。

        MUTATION ANCHOR MCP-6: 任一 ``_tool_*`` 里塞回 placeholder 返回 → 打红。
        """
        source = _ROUTER_PATH.read_text(encoding="utf-8")
        names = _TOOL_FUNC_RE.findall(source)
        # 自检：扫描范围不能空（否则"零违规"只是没扫到东西）
        assert len(names) >= 7, (
            f"未找到全部 7 个 _tool_* 分发器，只找到 {names}"
        )

        bodies = extract_function_bodies(source, names)
        assert set(bodies) == set(names), (
            f"AST 截取缺失：{sorted(set(names) - set(bodies))}"
        )

        offenders: list[str] = []
        for name, body in bodies.items():
            code_only = strip_comments_and_docstrings(body)
            if "placeholder" in code_only.lower():
                offenders.append(name)
        assert not offenders, (
            f"以下分发器仍含 placeholder 占位实现：{offenders}"
        )

    def test_placeholder_detector_is_not_vacuous(self):
        """反向自检：判据能抓到故意插入的 placeholder，也不会误判注释里的提及。

        没有这条，上一条测试可能只是因为"判据什么都认不出来"而绿。
        """
        planted = (
            'async def _tool_fake(*, arguments):\n'
            '    return {"status": "placeholder"}\n'
        )
        bodies = extract_function_bodies(planted, ["_tool_fake"])
        code_only = strip_comments_and_docstrings(bodies["_tool_fake"])
        assert "placeholder" in code_only.lower(), (
            "判据漏检：故意插入的 placeholder 返回没被抓到"
        )

        commented = (
            'async def _tool_ok(*, arguments):\n'
            '    # 历史上这里是 placeholder 占位实现，已在补洞时替换\n'
            '    """曾返回 placeholder。"""\n'
            '    return {"items": [1]}\n'
        )
        bodies2 = extract_function_bodies(commented, ["_tool_ok"])
        code_only2 = strip_comments_and_docstrings(bodies2["_tool_ok"])
        assert "placeholder" not in code_only2.lower(), (
            "判据误判：注释/docstring 里的散文提及被当成违规"
        )

    def test_runtime_results_carry_no_placeholder_status(self):
        """运行时：所有工具的成功返回都不含 ``status="placeholder"`` 或空壳 content。"""

        async def scenario(fx: AccessFixture, _sql):
            await seed_tb_balance(fx)
            await seed_workpaper_content(fx)
            token = make_token(fx, "manager")

            probes: list[tuple[str, dict[str, Any]]] = [
                ("wp_list", {}),
                ("wp_read", {"wp_id": str(fx.wp_d_file.id)}),
                ("tb_query", {"account_code": "1122"}),
                ("note_read", {"note_id": str(fx.note_a.id)}),
                ("review_prompt", {"wp_id": str(fx.wp_d_file.id)}),
            ]
            for tool_name, args in probes:
                out = await dispatch(fx, tool_name, args, token)
                assert out.get("status") != "placeholder", (
                    f"{tool_name} 仍返回 placeholder 状态"
                )
                assert out != {}, f"{tool_name} 返回空 dict"
                if "content" in out:
                    assert out["content"] != {}, f"{tool_name} 的 content 是空壳"

        run_with_fixture(scenario)


# ===========================================================================
# §3 授权断言 —— 拒绝就是拒绝，不许用空结果伪装
# ===========================================================================


class TestToolAuthorization:
    """每个工具内部再过 ``ResourceAccessResolver``；越权返回拒绝而非空数据。

    **Validates: Requirements 11.5, 2.4, 2.5, 2.6** · Property 28
    """

    def test_cross_project_token_cannot_read_workpaper(self):
        """另一 project 的 token 读本 project 的 wp_id → 拒绝（Property 28）。"""

        async def scenario(fx: AccessFixture, _sql):
            await seed_workpaper_content(fx)
            # outsider 只属于 project_b；token 也绑 project_b
            token = make_token(
                fx, "auditor",
                project_id=fx.project_b.id,
                user_id=fx.outsider.id,
            )
            with pytest.raises(McpToolError) as exc:
                await dispatch(
                    fx, "wp_read", {"wp_id": str(fx.wp_d_file.id)}, token
                )
            assert exc.value.code == ERR_ACCESS_DENIED, (
                f"跨项目读取应返回 access_denied，实际 {exc.value.code}"
            )

        run_with_fixture(scenario)

    def test_out_of_scope_cycle_workpaper_is_denied(self):
        """越出 ``scope_cycles`` 的底稿 → 拒绝（同项目，故只有授权判定能拦住它）。

        MUTATION ANCHOR MCP-7: ``_tool_wp_read`` 里放宽 ``if not decision.allowed``
        → 打红（该底稿项目相同，跨项目断言拦不住它）。
        """

        async def scenario(fx: AccessFixture, _sql):
            token = make_token(
                fx, "manager", cycle_scope=frozenset({IN_SCOPE_CYCLE, OUT_OF_SCOPE_CYCLE})
            )
            with pytest.raises(McpToolError) as exc:
                await dispatch(
                    fx, "wp_read", {"wp_id": str(fx.wp_e_file.id)}, token
                )
            assert exc.value.code == ERR_ACCESS_DENIED, (
                f"越出平台 scope_cycles 的底稿应拒绝，实际 {exc.value.code}"
            )

        run_with_fixture(scenario)

    def test_wp_read_denied_when_cycle_outside_token_cycle_scope(self):
        """token ``cycle_scope`` 之外的底稿即使平台允许也拒绝（Req 2.6 共用上界）。

        wp_d 在平台 ``scope_cycles="D"`` 内 ⇒ 门是放行的；token 收窄到 ``{E}`` 后
        **只有** ``_in_token_cycle_scope`` 这一层能拦住它。所以本用例是"token 循环
        裁剪"的隔离判据（wp_list 那条同时受 SQL 下推保护，抓不到这层）。

        MUTATION ANCHOR MCP-8: ``_in_token_cycle_scope`` 恒 True → 打红。
        """

        async def scenario(fx: AccessFixture, _sql):
            await seed_workpaper_content(fx)
            token = make_token(
                fx, "manager", cycle_scope=frozenset({OUT_OF_SCOPE_CYCLE})
            )
            with pytest.raises(McpToolError) as exc:
                await dispatch(
                    fx, "wp_read", {"wp_id": str(fx.wp_d_file.id)}, token
                )
            assert exc.value.code == ERR_ACCESS_DENIED, (
                f"token cycle_scope 之外的底稿应拒绝，实际 {exc.value.code}"
            )

        run_with_fixture(scenario)

    def test_wp_list_excludes_workpapers_outside_token_cycle_scope(self):
        """token ``cycle_scope`` 之外的底稿不出现在 ``wp_list`` 里。

        用 ``cycle_scope={E}`` 反向验证：平台 scope 允许 D，只有 **token 的**
        循环收窄能把 D 底稿挡掉 —— 这样"删掉 token scope 裁剪"必然打红。

        MUTATION ANCHOR MCP-8: 去掉 ``_in_token_cycle_scope`` / SQL 层 scope 下推 → 打红。
        """

        async def scenario(fx: AccessFixture, _sql):
            wide = await dispatch(
                fx, "wp_list", {}, make_token(fx, "manager", cycle_scope=frozenset())
            )
            wide_codes = {it["wp_code"] for it in wide["items"]}
            assert fx.wp_d.wp_code in wide_codes, (
                "前置条件不成立：不收窄时 D 底稿本应可见"
            )

            narrowed = await dispatch(
                fx, "wp_list", {},
                make_token(fx, "manager", cycle_scope=frozenset({OUT_OF_SCOPE_CYCLE})),
            )
            codes = {it["wp_code"] for it in narrowed["items"]}
            assert fx.wp_d.wp_code not in codes, (
                f"token cycle_scope={{{OUT_OF_SCOPE_CYCLE}}} 时 D 循环底稿仍出现："
                f"{sorted(codes)}"
            )

        run_with_fixture(scenario)

    def test_note_read_cross_project_note_is_denied(self):
        """跨项目附注 ID → 拒绝，不返回空 items 伪装无结果。"""

        async def scenario(fx: AccessFixture, _sql):
            token = make_token(fx, "manager")  # 绑 project_a
            with pytest.raises(McpToolError) as exc:
                await dispatch(fx, "note_read", {"note_id": str(fx.note_b.id)}, token)
            assert exc.value.code == ERR_ACCESS_DENIED

        run_with_fixture(scenario)

    def test_tb_query_denied_for_non_member(self):
        """非项目成员查试算表 → 拒绝（项目级授权真的执行了）。"""

        async def scenario(fx: AccessFixture, _sql):
            await seed_tb_balance(fx)
            token = make_token(
                fx, "auditor", project_id=fx.project_a.id, user_id=fx.outsider.id
            )
            with pytest.raises(McpToolError) as exc:
                await dispatch(fx, "tb_query", {"account_code": "1122"}, token)
            assert exc.value.code == ERR_ACCESS_DENIED

        run_with_fixture(scenario)


# ===========================================================================
# §4 脱敏断言 —— 两角色结果必须不相等
# ===========================================================================


class TestRoleMasking:
    """同一份含大额金额的数据，strict 与 none 两角色结果**不相等**。

    **Validates: Requirements 11.9** · Property 30

    🔴 为什么这条容易假绿：``ExportMaskService.MASK_RULES`` 只登记联系方式 /
    银行账号 / 身份证号，对"只含金额的试算表结构"是空操作。若 router 只调
    ``apply_mask``，auditor(strict) 与 partner(none) 会拿到**逐字节相同**的结果，
    而"脱敏已生效"的说法看起来仍成立。
    """

    def test_strict_and_none_role_results_differ(self):
        """auditor(strict) 与 partner(none) 走同一 endpoint，结果不得相等。

        MUTATION ANCHOR MCP-9: ``mask_tool_result`` 跳过金额脱敏 → 两者相等 → 打红。
        """

        async def scenario(fx: AccessFixture, _sql):
            await seed_tb_balance(fx)

            strict = await call_endpoint(
                fx, "tb_query", {"account_code": "1122"},
                make_token(fx, "auditor"),
            )
            none = await call_endpoint(
                fx, "tb_query", {"account_code": "1122"},
                make_token(fx, "partner"),
            )
            assert strict.status == "success", strict.error_message
            assert none.status == "success", none.error_message

            assert strict.result != none.result, (
                "strict 与 none 两角色的工具返回逐字节相同 ⇒ 脱敏未生效"
            )

            # partner：原始大额可见
            none_closing = {
                r["account_code"]: r["closing"] for r in none.result["rows"]
            }
            assert none_closing["1122.01"] == pytest.approx(50000000.0), (
                "partner(none) 不应被脱敏"
            )

            # auditor：嵌套 list 里的金额字段也被脱敏
            strict_closing = {
                r["account_code"]: r["closing"] for r in strict.result["rows"]
            }
            assert strict_closing["1122.01"] == "***", (
                f"auditor(strict) 的嵌套行金额未脱敏：{strict_closing}"
            )
            # totals 是嵌套 dict —— 同样必须覆盖
            assert strict.result["totals"]["closing"] == "***", (
                f"totals 嵌套 dict 内的金额未脱敏：{strict.result['totals']}"
            )

        run_with_fixture(scenario)

    def test_manager_gets_range_description_not_raw_amount(self):
        """manager(partial) 拿到区间描述，既不是原值也不是 ``***``（五角色映射一致）。"""

        async def scenario(fx: AccessFixture, _sql):
            await seed_tb_balance(fx)
            resp = await call_endpoint(
                fx, "tb_query", {"account_code": "1122"}, make_token(fx, "manager")
            )
            assert resp.status == "success", resp.error_message
            closing = {r["account_code"]: r["closing"] for r in resp.result["rows"]}
            value = closing["1122.01"]
            assert isinstance(value, str) and "万" in value, (
                f"manager 应得到区间描述，实际 {value!r}"
            )
            assert value != "***", "manager 不应与 auditor 同级脱敏"

        run_with_fixture(scenario)

    def test_sub_threshold_amounts_keep_numeric_type(self):
        """未触发阈值的金额保持数值类型（脱敏不得无差别把数字转成字符串）。"""

        async def scenario(fx: AccessFixture, _sql):
            await seed_tb_balance(fx)
            resp = await call_endpoint(
                fx, "tb_query", {"account_code": "2202"}, make_token(fx, "auditor")
            )
            assert resp.status == "success", resp.error_message
            rows = resp.result["rows"]
            assert rows, "2202 无子科目时应回落为父科目自身"
            for row in rows:
                assert isinstance(row["closing"], (int, float)), (
                    f"低于阈值的金额被无差别字符串化：{row['closing']!r}"
                )

        run_with_fixture(scenario)


# ===========================================================================
# §5 错误码分离 —— semantic_unavailable / not_found / invalid_argument
# ===========================================================================


class TestTypedErrorSeparation:
    """错误态与空态可区分；三类错误各自 typed error。

    **Validates: Requirements 6.5, 6.6, 12.4** · Property 16
    """

    def test_kb_search_embedding_down_returns_semantic_unavailable(self):
        """embedding 不可用 → ``semantic_unavailable``，**不是**空 results。

        MUTATION ANCHOR MCP-10: ``semantic_search_strict`` 改回带 BM25/ILIKE 兜底
        → 返回空 results 而非 typed error → 打红。
        """

        async def scenario(fx: AccessFixture, _sql):
            token = make_token(fx, "manager")
            with patch(
                "app.services.ai_service.AIService.embedding",
                new=AsyncMock(side_effect=RuntimeError("embedding endpoint refused")),
            ):
                with pytest.raises(McpToolError) as exc:
                    await dispatch(fx, "kb_search", {"query": "应收账款坏账准备"}, token)
            assert exc.value.code == ERR_SEMANTIC_UNAVAILABLE, (
                f"embedding down 应返回 semantic_unavailable，实际 {exc.value.code}"
            )

            # endpoint 层同样以 error_code 暴露，且 result 不塞假数据
            with patch(
                "app.services.ai_service.AIService.embedding",
                new=AsyncMock(side_effect=RuntimeError("embedding endpoint refused")),
            ):
                resp = await call_endpoint(
                    fx, "kb_search", {"query": "应收账款坏账准备"}, token
                )
            assert resp.status == "error"
            assert resp.error_code == ERR_SEMANTIC_UNAVAILABLE
            assert resp.result == {}, "错误态不得携带伪装结果"

        run_with_fixture(scenario)

    def test_kb_search_empty_hit_is_success_not_error(self):
        """检索成功但零命中 → ``success`` + 空 results（空态 ≠ 错误态）。

        🔴 这里注入的是"向量召回返回空列表"，而不是"embedding 可用"：本 dev 库的
        ``knowledge_index`` **没有** ``embedding_vec`` 列（V119 的 pgvector 列未落地），
        ``_vector_search`` 的 pgvector 分支必失败并把整个事务置为 aborted，其内建的
        内存暴力兜底也就跟着失败 —— 于是在真实库上 ``kb_search`` 永远只能得到
        ``semantic_unavailable``。那正是本 spec 想要的诚实行为（好过静默 BM25 降级），
        但它让"零命中"这个**正常态**无法在真库上复现，故只注入命中列表这一步。
        判据本身（strict 不吞空、工具把空列表如实映射为 success）仍走真实代码。
        """

        async def scenario(fx: AccessFixture, _sql):
            from app.services.knowledge_index_service import KnowledgeIndexService

            token = make_token(fx, "manager")
            with patch.object(
                KnowledgeIndexService,
                "_vector_search",
                new=AsyncMock(return_value=[]),
            ):
                out = await dispatch(
                    fx, "kb_search", {"query": "本项目不存在的关键词"}, token
                )
            assert out["results"] == [], (
                f"未命中时应返回空 results，实际 {out['results'][:2]}"
            )
            assert out["query"] == "本项目不存在的关键词"
            assert out["total"] == 0
            assert "error_code" not in out

        run_with_fixture(scenario)

    def test_missing_resource_is_not_found_not_empty(self):
        """不存在的 wp_id → ``tool_resource_not_found``，不返回空 content。"""

        async def scenario(fx: AccessFixture, _sql):
            token = make_token(fx, "manager")
            with pytest.raises(McpToolError) as exc:
                await dispatch(fx, "wp_read", {"wp_id": str(uuid4())}, token)
            # 授权先行：不存在的资源在 gate 处即被判不可访问（不可枚举语义）
            assert exc.value.code in (ERR_NOT_FOUND, ERR_ACCESS_DENIED)
            assert exc.value.code != ERR_INVALID_ARGUMENT

        run_with_fixture(scenario)

    def test_invalid_arguments_are_rejected_distinctly(self):
        """缺必填 / 非法 UUID → ``tool_invalid_argument``（与"无权限"分码）。"""

        async def scenario(fx: AccessFixture, _sql):
            token = make_token(fx, "manager")
            cases: list[tuple[str, dict[str, Any]]] = [
                ("wp_read", {}),
                ("wp_read", {"wp_id": "not-a-uuid"}),
                ("kb_search", {"query": ""}),
                ("addr_lookup", {}),
                ("review_prompt", {}),
                ("note_read", {"note_id": "not-a-uuid"}),
            ]
            for tool_name, args in cases:
                with pytest.raises(McpToolError) as exc:
                    await dispatch(fx, tool_name, args, token)
                assert exc.value.code == ERR_INVALID_ARGUMENT, (
                    f"{tool_name}{args} 应判 invalid_argument，实际 {exc.value.code}"
                )

        run_with_fixture(scenario)

    def test_endpoint_maps_tool_error_code_verbatim(self):
        """endpoint 把工具 typed error 原样映射到 ``error_code``（不塌缩成通用码）。"""

        async def scenario(fx: AccessFixture, _sql):
            token = make_token(fx, "manager")
            resp = await call_endpoint(fx, "wp_read", {"wp_id": "not-a-uuid"}, token)
            assert resp.status == "error"
            assert resp.error_code == ERR_INVALID_ARGUMENT, (
                f"错误码被塌缩：{resp.error_code}"
            )
            assert resp.error_code != "tool_execution_failed"

        run_with_fixture(scenario)


# ===========================================================================
# §6 只读约束
# ===========================================================================


class TestReadOnlyGuarantee:
    """工具实现不含任何写操作（Req 11.2：全部 readonly）。"""

    def test_mcp_tools_module_has_no_write_statements(self):
        """``mcp_tools.py`` 代码里没有 insert/update/delete/commit（先剥注释）。"""
        from app.services.ai_chat import mcp_tools

        source = Path(mcp_tools.__file__).resolve().read_text(encoding="utf-8")
        code_only = strip_comments_and_docstrings(source)
        forbidden = ["sa.insert", "sa.update", "sa.delete", ".commit(", ".add(", ".flush("]
        offenders = [token for token in forbidden if token in code_only]
        assert not offenders, (
            f"MCP 取数实现出现写操作：{offenders}（工具必须 readonly）"
        )
