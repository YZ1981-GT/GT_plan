"""八项既有引擎 adapter contract 测试 — 验证真实接口形状（design §10.2 #3）。

这些测试导入八项 **真实** 引擎，断言其类/模块函数/ORM 模型的接口形状与冻结清单
``adapter_contract_manifest.json`` 一致。它们的作用是：

1. 证明治理层可以直接委托这些真实接口，而不必复制/分叉引擎（no-fork 的正向证据）。
2. 一旦某引擎的公共接口漂移（重命名方法、删参数、改 ORM 表名），本测试立即失败，
   强制治理层与真实引擎重新对齐，而不是各自演化。

不 mock、不连数据库；只做导入 + 反射。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 1.5
Requirements: R1, R5, R7, R8, R9, R11, R12, R15
"""

from __future__ import annotations

import importlib
import inspect

import pytest

from app.services.evidence_governance import frozen_contracts as fc

MANIFEST = fc.load_engine_contracts()
ENGINES = MANIFEST["engines"]
ENGINE_IDS = [e["name"] for e in ENGINES]


def _signature_param_names(obj) -> set[str]:
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):  # builtins / C-level
        return set()
    return set(sig.parameters.keys())


def _resolve_module(engine: dict):
    return importlib.import_module(engine["module"])


# ---------------------------------------------------------------------------
# 清单自身一致性
# ---------------------------------------------------------------------------


def test_manifest_covers_eight_reused_engines():
    """清单必须覆盖 design §1.2 的八项复用引擎（AiContentLog 拆 service+model）。"""
    names = {e["name"] for e in ENGINES}
    # 八项引擎的标识（ACNR 拆 resolver/events，AiContentLog 拆 service/model）
    expected_core = {
        "AttachmentService",
        "UnifiedOCRService",
        "KnowledgeIndexService",
        "AiContentLogService",
        "AiContentLog",
        "ACNR.resolver",
        "ACNR.events",
        "StalePropagationEngine",
        "DeliverableService",
        "ArchiveOrchestrator",
    }
    assert expected_core.issubset(names), (
        f"清单缺失引擎: {expected_core - names}"
    )


def test_manifest_has_governance_scan_roots():
    roots = MANIFEST.get("governance_scan_roots") or []
    assert roots, "禁止分叉守卫需要 governance_scan_roots"
    assert any("evidence_governance" in r for r in roots)


# ---------------------------------------------------------------------------
# 每个引擎的真实接口形状
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINE_IDS)
def test_engine_module_importable(engine):
    mod = _resolve_module(engine)
    assert mod is not None


@pytest.mark.parametrize(
    "engine",
    [e for e in ENGINES if e["kind"] in ("class", "orm_model")],
    ids=[e["name"] for e in ENGINES if e["kind"] in ("class", "orm_model")],
)
def test_class_symbol_exists(engine):
    mod = _resolve_module(engine)
    symbol = engine["symbol"]
    assert hasattr(mod, symbol), (
        f"{engine['module']}.{symbol} 不存在 — 引擎接口漂移"
    )
    assert inspect.isclass(getattr(mod, symbol))


@pytest.mark.parametrize(
    "engine",
    [e for e in ENGINES if e["kind"] == "class"],
    ids=[e["name"] for e in ENGINES if e["kind"] == "class"],
)
def test_class_required_methods(engine):
    cls = getattr(_resolve_module(engine), engine["symbol"])
    for spec in engine.get("required_methods", []):
        mname = spec["name"]
        assert hasattr(cls, mname), (
            f"{engine['name']}.{mname} 缺失 — 治理层不得据此分叉，请对齐真实接口"
        )
        member = getattr(cls, mname)
        assert callable(member), f"{engine['name']}.{mname} 不可调用"
        required = set(spec.get("params", []))
        if required:
            actual = _signature_param_names(member)
            missing = required - actual
            assert not missing, (
                f"{engine['name']}.{mname} 缺参数 {missing}；实际参数 {sorted(actual)}"
            )


@pytest.mark.parametrize(
    "engine",
    [e for e in ENGINES if e.get("required_attributes")],
    ids=[e["name"] for e in ENGINES if e.get("required_attributes")],
)
def test_class_required_attributes(engine):
    cls = getattr(_resolve_module(engine), engine["symbol"])
    for attr in engine["required_attributes"]:
        assert hasattr(cls, attr), (
            f"{engine['name']}.{attr} 缺失（属性/描述符）"
        )


@pytest.mark.parametrize(
    "engine",
    [e for e in ENGINES if e["kind"] == "module"],
    ids=[e["name"] for e in ENGINES if e["kind"] == "module"],
)
def test_module_required_functions(engine):
    mod = _resolve_module(engine)
    for spec in engine.get("required_functions", []):
        fname = spec["name"]
        assert hasattr(mod, fname), (
            f"{engine['module']}.{fname} 缺失 — 引擎模块函数漂移"
        )
        fn = getattr(mod, fname)
        assert callable(fn), f"{engine['module']}.{fname} 不可调用"
        required = set(spec.get("params", []))
        if required:
            actual = _signature_param_names(fn)
            missing = required - actual
            assert not missing, (
                f"{engine['module']}.{fname} 缺参数 {missing}；"
                f"实际参数 {sorted(actual)}"
            )


@pytest.mark.parametrize(
    "engine",
    [e for e in ENGINES if e["kind"] == "orm_model"],
    ids=[e["name"] for e in ENGINES if e["kind"] == "orm_model"],
)
def test_orm_model_shape(engine):
    model = getattr(_resolve_module(engine), engine["symbol"])
    assert hasattr(model, "__tablename__"), f"{engine['name']} 不是 ORM 模型"
    assert model.__tablename__ == engine["table_name"], (
        f"{engine['name']} 表名漂移: {model.__tablename__} != {engine['table_name']}"
    )
    columns = set(model.__table__.columns.keys())
    required = set(engine.get("required_columns", []))
    missing = required - columns
    assert not missing, (
        f"{engine['name']} 缺列 {missing}；实际列 {sorted(columns)}"
    )
