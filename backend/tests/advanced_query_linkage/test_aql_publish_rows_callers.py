"""``tb_audited_writer.publish_rows`` 生产调用方棘轮（advanced-query-linkage-closure 任务 15；R4.3；变异 #9）。

试算表审定数只经发布门（``tb_audited_writer``）写入是平台铁律。``publish_rows`` 是发布门的批量入口，它的生产调用方
冻结为下面登记的 5 个他域模块；高级查询包与 custom_query / query_builder 路由出现任何引用即红（任务 13 删掉
``snapshot_writer_modules.write_tb_cell`` 那一处之后，高级查询包是零调用）。

判定用 AST（不做文本 ``in`` 匹配）：一个模块「引用了 ``publish_rows``」= 出现以下任一形态——
``from …tb_audited_writer import publish_rows``（含别名）、任意对象上的 ``.publish_rows`` 属性访问、名为
``publish_rows`` 的调用，或字符串常量 ``"publish_rows"``（``getattr`` / ``importlib`` 等动态取用）。定义它的
``tb_audited_writer`` 本身不算调用方。登记集多一个或少一个都红，新增调用方须在此登记并写明理由。
"""
from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
DEFINER = "services/tb_audited_writer.py"
NAME = "publish_rows"

#: 合法的他域调用方（2026-10-27 现查；远端同此集合，合入后在任务 0 第 6 条重跑）
REGISTERED: frozenset[str] = frozenset({
    "services/event_handlers_cycle_linkage.py",   # 审定表联动：底稿保存后按循环推审定数
    "routers/m9_other_comprehensive_income.py",   # M9 其他综合收益发布
    "routers/n2_taxes_payable.py",                # N2 应交税费发布
    "services/s_transaction_tb_writeback_service.py",  # S 循环交易类回写
    "services/s_estimate_tb_writeback_service.py",     # S 循环估计类回写
})

#: 高级查询的生产代码（包 + 三个 router）
ADVANCED_QUERY_PREFIXES: tuple[str, ...] = (
    "services/custom_query/", "routers/custom_query.py", "routers/custom_query_writeback.py",
    "routers/query_builder.py",
)


def references_publish_rows(source: str) -> bool:
    """模块源码里是否出现对 ``publish_rows`` 的引用（导入 / 属性 / 调用 / 字符串常量）。"""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and any(alias.name == NAME for alias in node.names):
            return True
        if isinstance(node, ast.Attribute) and node.attr == NAME:
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == NAME:
            return True
        if isinstance(node, ast.Constant) and node.value == NAME:
            return True
    return False


def production_callers() -> set[str]:
    found: set[str] = set()
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        if rel == DEFINER:
            continue
        if references_publish_rows(path.read_text(encoding="utf-8-sig")):
            found.add(rel)
    return found


def test_publish_rows_callers_are_exactly_the_registered_set() -> None:
    found = production_callers()
    extra, missing = sorted(found - REGISTERED), sorted(REGISTERED - found)
    assert not extra and not missing, (
        "publish_rows 的生产调用方与登记集不一致（审定数只经发布门写入，新增调用方须在本文件登记并写明理由；"
        f"登记了却不再调用的须删掉登记）：多出 {extra}，缺少 {missing}"
    )


def test_advanced_query_code_never_references_publish_rows() -> None:
    offenders = sorted(rel for rel in production_callers() if rel.startswith(ADVANCED_QUERY_PREFIXES))
    assert not offenders, f"高级查询不得写试算表审定数（ADR-AQL-02），以下模块引用了 publish_rows：{offenders}"


def test_scanner_recognises_every_reference_form() -> None:
    """扫描器自检（双向）：四种引用形态都认得，名字相近的不误认。"""
    positive = {
        "from_import_alias": "from app.services.tb_audited_writer import publish_rows as _p\n",
        "attribute": "from app.services import tb_audited_writer\nasync def f(db):\n"
                     "    await tb_audited_writer.publish_rows(db)\n",
        "bare_call": "async def f(db):\n    await publish_rows(db)\n",
        "dynamic": "import importlib\ndef f():\n    return getattr(importlib.import_module('m'), 'publish_rows')\n",
    }
    for label, source in positive.items():
        assert references_publish_rows(source), f"漏认引用形态：{label}"
    negative = (
        "def publish_rows_preview():\n    return 'publish_rows_v2'\n",
        "from app.services.tb_audited_writer import publish_one\n",
    )
    for source in negative:
        assert not references_publish_rows(source), f"误认：{source!r}"
